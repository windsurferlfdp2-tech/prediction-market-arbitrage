from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from app.models.domain import ArbitrageOpportunity, Market, OrderBook, Side, UsedLevel

ONE = Decimal("1")


class ArbitrageDetector:
    def __init__(
        self,
        max_age_seconds: int,
        min_net_profit: Decimal,
        min_roi: Decimal,
        fee_rate: Decimal,
        slippage_rate: Decimal,
    ) -> None:
        self.max_age_seconds = max_age_seconds
        self.min_net_profit = min_net_profit
        self.min_roi = min_roi
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.last_rejection_counts: Counter[str] = Counter()
        self.last_diagnostics: dict[str, Any] = {}

    def detect(self, markets: list[Market], books: list[OrderBook]) -> list[ArbitrageOpportunity]:
        now = datetime.now(UTC)
        self.last_rejection_counts = Counter()
        self.last_diagnostics = {
            "markets_with_verified_pair": 0,
            "fresh_books": 0,
            "stale_books": 0,
            "pairs_evaluated": 0,
            "raw_pricing_discrepancies": 0,
        }
        markets_by_key = {
            market.same_market_key: market
            for market in markets
            if market.same_market_key is not None
        }
        self.last_diagnostics["markets_with_verified_pair"] = len(markets_by_key)
        if not markets_by_key:
            self.last_rejection_counts["no_verified_pair"] += 1

        books_by_key: dict[str, list[OrderBook]] = {}
        market_key_by_id = {market.exchange_market_id: market.same_market_key for market in markets}
        for book in books:
            if book.is_stale(self.max_age_seconds, now):
                self.last_rejection_counts["stale_order_book"] += 1
                self.last_diagnostics["stale_books"] += 1
                continue
            key = market_key_by_id.get(book.market_id)
            if key is None:
                self.last_rejection_counts["missing_verified_pair"] += 1
                continue
            self.last_diagnostics["fresh_books"] += 1
            books_by_key.setdefault(key, []).append(book)

        for key in markets_by_key:
            if key not in books_by_key:
                self.last_rejection_counts["missing_order_book"] += 1

        opportunities: list[ArbitrageOpportunity] = []
        for key, key_books in books_by_key.items():
            yes_books = [book for book in key_books if book.side == Side.YES and book.asks]
            no_books = [book for book in key_books if book.side == Side.NO and book.asks]
            if not yes_books:
                self.last_rejection_counts["missing_yes_side"] += 1
            if not no_books:
                self.last_rejection_counts["missing_no_side"] += 1
            for yes_book in yes_books:
                for no_book in no_books:
                    if yes_book.market_id == no_book.market_id:
                        continue
                    if yes_book.exchange == no_book.exchange:
                        continue
                    self.last_diagnostics["pairs_evaluated"] += 1
                    opportunity = self._evaluate_pair(
                        key,
                        markets_by_key.get(key),
                        yes_book,
                        no_book,
                        now,
                    )
                    if opportunity:
                        opportunities.append(opportunity)

        return sorted(opportunities, key=lambda item: (item.net_profit, item.roi), reverse=True)

    def _evaluate_pair(
        self,
        same_market_key: str,
        market: Market | None,
        yes_book: OrderBook,
        no_book: OrderBook,
        detected_at: datetime,
    ) -> ArbitrageOpportunity | None:
        yes_index = 0
        no_index = 0
        matched = Decimal("0")
        yes_cost = Decimal("0")
        no_cost = Decimal("0")
        used: list[UsedLevel] = []

        yes_levels = [
            level.model_copy()
            for level in sorted(
                [level for level in yes_book.asks if _is_valid_binary_level(level.price)],
                key=lambda level: level.price,
            )
        ]
        no_levels = [
            level.model_copy()
            for level in sorted(
                [level for level in no_book.asks if _is_valid_binary_level(level.price)],
                key=lambda level: level.price,
            )
        ]
        invalid_yes_levels = len(yes_book.asks) - len(yes_levels)
        invalid_no_levels = len(no_book.asks) - len(no_levels)
        if invalid_yes_levels or invalid_no_levels:
            self.last_rejection_counts["invalid_price"] += invalid_yes_levels + invalid_no_levels
        yes_levels = [level for level in yes_levels if level.quantity > 0]
        no_levels = [level for level in no_levels if level.quantity > 0]
        if not yes_levels:
            self.last_rejection_counts["missing_yes_side"] += 1
            return None
        if not no_levels:
            self.last_rejection_counts["missing_no_side"] += 1
            return None

        while yes_index < len(yes_levels) and no_index < len(no_levels):
            yes_level = yes_levels[yes_index]
            no_level = no_levels[no_index]
            if yes_level.price + no_level.price >= ONE:
                if matched <= 0:
                    self.last_rejection_counts["combined_cost_at_or_above_payout"] += 1
                break
            quantity = min(yes_level.quantity, no_level.quantity)
            if quantity <= 0:
                self.last_rejection_counts["insufficient_liquidity"] += 1
                break
            matched += quantity
            yes_cost += yes_level.price * quantity
            no_cost += no_level.price * quantity
            used.extend(
                [
                    _used_level(yes_book, yes_level.price, quantity, yes_level.source_side),
                    _used_level(no_book, no_level.price, quantity, no_level.source_side),
                ]
            )
            yes_level.quantity -= quantity
            no_level.quantity -= quantity
            if yes_level.quantity == 0:
                yes_index += 1
            if no_level.quantity == 0:
                no_index += 1

        if matched <= 0:
            self.last_rejection_counts["insufficient_liquidity"] += 1
            return None
        self.last_diagnostics["raw_pricing_discrepancies"] += 1

        gross_cost = yes_cost + no_cost
        payout = matched
        gross_profit = payout - gross_cost
        fees = gross_cost * self.fee_rate
        slippage = gross_cost * self.slippage_rate
        net_profit = gross_profit - fees - slippage
        roi = net_profit / gross_cost if gross_cost else Decimal("0")
        if gross_profit > 0 and gross_profit - fees <= 0:
            self.last_rejection_counts["fees_remove_profit"] += 1
            return None
        if gross_profit > 0 and gross_profit - fees - slippage <= 0:
            self.last_rejection_counts["slippage_removes_profit"] += 1
            return None
        if net_profit < self.min_net_profit:
            self.last_rejection_counts["profit_below_minimum"] += 1
            return None
        if roi < self.min_roi:
            self.last_rejection_counts["roi_below_minimum"] += 1
            return None

        freshness = max(yes_book.age_seconds(detected_at), no_book.age_seconds(detected_at))
        confidence = "high" if freshness <= Decimal(self.max_age_seconds / 2) else "medium"
        data_source = "live" if yes_book.is_live_data and no_book.is_live_data else "test"
        raw_id = (
            f"{same_market_key}:{yes_book.exchange}:{yes_book.market_id}:"
            f"{no_book.exchange}:{no_book.market_id}"
        )
        return ArbitrageOpportunity(
            id=sha256(raw_id.encode()).hexdigest()[:16],
            same_market_key=same_market_key,
            title=market.title if market else same_market_key,
            yes_exchange=yes_book.exchange,
            no_exchange=no_book.exchange,
            yes_market_id=yes_book.market_id,
            no_market_id=no_book.market_id,
            yes_avg_price=yes_cost / matched,
            no_avg_price=no_cost / matched,
            gross_cost=gross_cost,
            gross_profit=gross_profit,
            total_fees=fees,
            slippage_cost=slippage,
            net_profit=net_profit,
            roi=roi,
            max_quantity=matched,
            detected_at=detected_at,
            freshness_seconds=freshness,
            confidence=confidence,
            used_levels=used,
            data_source=data_source,
            is_live_data=data_source == "live",
            source_timestamp=max(yes_book.fetched_at, no_book.fetched_at),
            freshness_status="LIVE" if data_source == "live" else "TEST",
        )


def _used_level(book: OrderBook, price: Decimal, quantity: Decimal, source_side: str) -> UsedLevel:
    return UsedLevel(
        exchange=book.exchange,
        market_id=book.market_id,
        outcome_id=book.outcome_id,
        side=book.side,
        price=price,
        quantity=quantity,
        source_side=source_side,
    )


def _is_valid_binary_level(price: Decimal) -> bool:
    return price.is_finite() and Decimal("0") <= price <= ONE
