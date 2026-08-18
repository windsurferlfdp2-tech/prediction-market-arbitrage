from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import structlog

from app.arbitrage.detector import ArbitrageDetector
from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.models.domain import ArbitrageOpportunity, ExchangeHealth, Market, OrderBook
from app.services.history import OpportunityHistoryRecorder
from app.services.market_matching import MarketMatchingService, apply_verified_market_pairs
from app.services.paper_trading import PaperTradingSimulator
from app.services.realtime_books import (
    OrderBookSnapshotRecorder,
    RealtimeOrderBookService,
    Transport,
)

log = structlog.get_logger()


class ScannerService:
    def __init__(
        self,
        settings: Settings,
        adapters: list[ExchangeAdapter],
        history_recorder: OpportunityHistoryRecorder | None = None,
        market_matching_service: MarketMatchingService | None = None,
        realtime_books: RealtimeOrderBookService | None = None,
        paper_trading: PaperTradingSimulator | None = None,
        book_snapshot_recorder: OrderBookSnapshotRecorder | None = None,
    ) -> None:
        self.settings = settings
        self.adapters = adapters
        self.history_recorder = history_recorder
        self.market_matching_service = market_matching_service
        self.realtime_books = realtime_books
        self.paper_trading = paper_trading
        self.book_snapshot_recorder = book_snapshot_recorder
        self.detector = ArbitrageDetector(
            max_age_seconds=settings.orderbook_max_age_seconds,
            min_net_profit=settings.min_net_profit,
            min_roi=settings.min_roi,
            fee_rate=settings.fee_rate,
            slippage_rate=settings.slippage_rate,
        )
        self._markets: list[Market] = []
        self._books: list[OrderBook] = []
        self._opportunities: list[ArbitrageOpportunity] = []
        self._last_status: dict[str, Any] = {
            "running": False,
            "last_started_at": None,
            "last_completed_at": None,
            "last_error": None,
            "markets_checked": 0,
            "books_checked": 0,
            "verified_pairs_checked": 0,
            "opportunities_found": 0,
            "scan_duration_seconds": None,
            "diagnostics": {},
        }

    async def refresh(self) -> list[ArbitrageOpportunity]:
        started = datetime.now(UTC)
        started_perf = perf_counter()
        self._last_status.update(
            {
                "running": True,
                "last_started_at": started,
                "last_error": None,
            }
        )
        log.info("scanner_scan_start", data_mode=self.settings.effective_data_mode)
        if self.settings.effective_data_mode == "test":
            from app.services.simulation import simulated_markets_and_books

            try:
                self._markets, self._books = simulated_markets_and_books()
                if self.realtime_books is not None:
                    for book in self._books:
                        self.realtime_books.apply_snapshot(book, transport="test")
                self._opportunities = self.detector.detect(self._markets, self._books)
                await self._record_book_snapshots("test")
                await self._simulate_paper_trades()
                await self._record_history()
                self._complete_scan(
                    started_perf,
                    verified_pairs_checked=0,
                    diagnostics=self._build_diagnostics(
                        verified_pairs_total=0,
                        verified_active_pairs=0,
                        executable_markets=0,
                    ),
                )
                return self._opportunities
            except Exception as exc:
                self._fail_scan(started_perf, exc)
                raise

        try:
            markets: list[Market] = []
            books: list[OrderBook] = []
            for adapter in self.adapters:
                adapter_markets = await adapter.fetch_active_markets()
                if (
                    self.settings.effective_data_mode == "live"
                    and self.settings.live_scan_market_limit > 0
                ):
                    adapter_markets = adapter_markets[: self.settings.live_scan_market_limit]
                markets.extend(adapter_markets)
            verified_pairs_checked = 0
            verified_active_pairs = 0
            if self.market_matching_service is not None:
                verified_keys = await self.market_matching_service.verified_same_market_keys()
                verified_pairs_checked = len(set(verified_keys.values()))
                markets = apply_verified_market_pairs(markets, verified_keys)
                verified_active_pairs = _same_market_keys_with_both_exchanges(markets)
            executable_markets = (
                [market for market in markets if market.same_market_key is not None]
                if self.market_matching_service is not None
                else markets
            )
            if self.realtime_books is not None:
                books = await self.realtime_books.refresh_rest_snapshot(executable_markets)
            else:
                for adapter in self.adapters:
                    adapter_markets = _markets_for_adapter(adapter, executable_markets)
                    books.extend(await adapter.fetch_order_books(adapter_markets))
            self._markets = markets
            self._books = books
            self._opportunities = self.detector.detect(markets, books)
            await self._record_book_snapshots("rest_fallback")
            await self._simulate_paper_trades()
            await self._record_history()
            self._complete_scan(
                started_perf,
                verified_pairs_checked=verified_pairs_checked,
                diagnostics=self._build_diagnostics(
                    verified_pairs_total=verified_pairs_checked,
                    verified_active_pairs=verified_active_pairs,
                    executable_markets=len(executable_markets),
                ),
            )
            return self._opportunities
        except Exception as exc:
            self._fail_scan(started_perf, exc)
            raise

    async def candidate_markets(self) -> list[Market]:
        if self.settings.effective_data_mode == "test":
            from app.services.simulation import simulated_markets_and_books

            self._markets, self._books = simulated_markets_and_books()
            return self._markets

        markets: list[Market] = []
        for adapter in self.adapters:
            adapter_markets = await adapter.fetch_active_markets()
            if (
                self.settings.effective_data_mode == "live"
                and self.settings.live_scan_market_limit > 0
            ):
                adapter_markets = adapter_markets[: self.settings.live_scan_market_limit]
            markets.extend(adapter_markets)
        self._markets = markets
        return markets

    async def markets(self) -> list[Market]:
        if not self._markets:
            await self.candidate_markets()
        return self._markets

    async def opportunities(self) -> list[ArbitrageOpportunity]:
        await self.refresh()
        return self._opportunities

    async def opportunity(self, opportunity_id: str) -> ArbitrageOpportunity | None:
        opportunities = await self.opportunities()
        return next((item for item in opportunities if item.id == opportunity_id), None)

    async def health(self) -> list[ExchangeHealth]:
        if self.settings.effective_data_mode == "test":
            return []
        return [await adapter.health() for adapter in self.adapters]

    def status(self) -> dict[str, Any]:
        return {
            **self._last_status,
            "data_mode": self.settings.effective_data_mode,
            "latest_market_fetch_timestamp": max(
                (market.fetched_at for market in self._markets),
                default=None,
            ),
            "latest_order_book_update_timestamp": max(
                (book.fetched_at for book in self._books),
                default=None,
            ),
            "latest_opportunity_detected_timestamp": max(
                (opportunity.detected_at for opportunity in self._opportunities),
                default=None,
            ),
            "order_book_ages_seconds": [
                {
                    "exchange": book.exchange.value,
                    "market_id": book.market_id,
                    "side": book.side.value,
                    "age_seconds": book.age_seconds(),
                }
                for book in self._books
            ],
            "diagnostics": self._last_status.get("diagnostics", {}),
        }

    async def _record_history(self) -> None:
        if self.history_recorder is None:
            return
        await self.history_recorder.record_refresh(
            self._opportunities,
            self.settings.effective_data_mode,
        )

    async def _record_book_snapshots(self, transport: Transport) -> None:
        if self.book_snapshot_recorder is None:
            return
        await self.book_snapshot_recorder.record(self._books, transport)

    async def _simulate_paper_trades(self) -> None:
        if self.paper_trading is None or not self.settings.paper_trading_enabled:
            return
        for opportunity in self._opportunities:
            await self.paper_trading.simulate(opportunity, self._books)

    def _complete_scan(
        self,
        started_perf: float,
        verified_pairs_checked: int,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        duration = perf_counter() - started_perf
        completed_at = datetime.now(UTC)
        diagnostics = diagnostics or {}
        self._last_status.update(
            {
                "running": False,
                "last_completed_at": completed_at,
                "markets_checked": len(self._markets),
                "books_checked": len(self._books),
                "verified_pairs_checked": verified_pairs_checked,
                "opportunities_found": len(self._opportunities),
                "scan_duration_seconds": duration,
                "diagnostics": diagnostics,
                "last_error": None,
            }
        )
        log.info(
            "scanner_scan_complete",
            data_mode=self.settings.effective_data_mode,
            markets_checked=len(self._markets),
            books_checked=len(self._books),
            verified_pairs_checked=verified_pairs_checked,
            opportunities_found=len(self._opportunities),
            scan_duration_seconds=duration,
            rejection_counts=diagnostics.get("rejection_counts", {}),
            raw_pricing_discrepancies=diagnostics.get("funnel", {}).get(
                "raw_pricing_discrepancies",
                0,
            ),
        )

    def _fail_scan(self, started_perf: float, exc: Exception) -> None:
        duration = perf_counter() - started_perf
        self._last_status.update(
            {
                "running": False,
                "last_error": str(exc),
                "scan_duration_seconds": duration,
            }
        )
        log.exception(
            "scanner_scan_error",
            data_mode=self.settings.effective_data_mode,
            scan_duration_seconds=duration,
            error=str(exc),
        )

    def _build_diagnostics(
        self,
        verified_pairs_total: int,
        verified_active_pairs: int,
        executable_markets: int,
    ) -> dict[str, Any]:
        detector_diagnostics = self.detector.last_diagnostics
        raw_discrepancies = int(detector_diagnostics.get("raw_pricing_discrepancies", 0))
        final_opportunities = len(self._opportunities)
        first_zero_stage = None
        funnel = {
            "markets_fetched": len(self._markets),
            "markets_normalized": len(self._markets),
            "verified_pairs_total": verified_pairs_total,
            "verified_pairs_active_on_both_exchanges": verified_active_pairs,
            "executable_markets_from_verified_pairs": executable_markets,
            "usable_order_books_loaded": len(self._books),
            "verified_pairs_with_fresh_books": int(detector_diagnostics.get("pairs_evaluated", 0)),
            "raw_pricing_discrepancies": raw_discrepancies,
            "after_fees": raw_discrepancies
            - int(self.detector.last_rejection_counts.get("fees_remove_profit", 0)),
            "after_slippage": raw_discrepancies
            - int(self.detector.last_rejection_counts.get("fees_remove_profit", 0))
            - int(self.detector.last_rejection_counts.get("slippage_removes_profit", 0)),
            "after_liquidity_checks": raw_discrepancies
            - int(self.detector.last_rejection_counts.get("insufficient_liquidity", 0)),
            "after_freshness_checks": raw_discrepancies,
            "final_opportunities_persisted": final_opportunities,
            "final_opportunities_returned_by_api": final_opportunities,
        }
        for stage, count in funnel.items():
            if first_zero_stage is None and count == 0:
                first_zero_stage = stage
        return {
            "funnel": funnel,
            "first_zero_stage": first_zero_stage,
            "rejection_counts": dict(self.detector.last_rejection_counts),
            "exchange_status": [_adapter_diagnostics(adapter) for adapter in self.adapters],
            "thresholds": {
                "minimum_net_profit": str(self.settings.min_net_profit),
                "minimum_roi": str(self.settings.min_roi),
                "maximum_order_book_age_seconds": self.settings.orderbook_max_age_seconds,
                "fee_rate": str(self.settings.fee_rate),
                "slippage_rate": str(self.settings.slippage_rate),
                "live_scan_market_limit": self.settings.live_scan_market_limit,
                "paper_max_position": str(self.settings.paper_max_position),
            },
            "strategies_active": {
                "cross_platform_verified_pairs": True,
                "polymarket_yes_plus_polymarket_no": False,
                "kalshi_yes_plus_kalshi_no": False,
                "multi_outcome_complete_set": False,
            },
            "healthy_zero_message": (
                "Live scanner is running normally. No qualifying arbitrage opportunities "
                "are currently available."
            ),
        }


def _markets_for_adapter(adapter: ExchangeAdapter, markets: list[Market]) -> list[Market]:
    exchange_names = {market.exchange.value for market in markets}
    if adapter.name in exchange_names:
        return [market for market in markets if market.exchange.value == adapter.name]
    return markets


def _same_market_keys_with_both_exchanges(markets: list[Market]) -> int:
    exchanges_by_key: dict[str, set[str]] = {}
    for market in markets:
        if market.same_market_key is None:
            continue
        exchanges_by_key.setdefault(market.same_market_key, set()).add(market.exchange.value)
    return sum(1 for exchanges in exchanges_by_key.values() if len(exchanges) >= 2)


def _adapter_diagnostics(adapter: ExchangeAdapter) -> dict[str, Any]:
    return {
        "exchange": adapter.name,
        "latest_successful_fetch_timestamp": getattr(adapter, "last_fetch_timestamp", None),
        "active_markets_received": getattr(adapter, "last_raw_market_count", 0),
        "markets_normalized": getattr(adapter, "last_normalized_market_count", 0),
        "markets_rejected": len(getattr(adapter, "last_rejections", [])),
        "top_rejection_reasons": _top_rejection_reasons(getattr(adapter, "last_rejections", [])),
        "order_books_requested": getattr(adapter, "last_order_books_requested", 0),
        "usable_order_books": getattr(adapter, "last_order_books_returned", 0),
        "order_book_errors": getattr(adapter, "last_order_book_errors", []),
        "authentication_status": "not_required_for_configured_market_data",
        "rate_limit_errors": 0,
        "timeout_errors": 0,
        "parsing_errors": len(getattr(adapter, "last_order_book_errors", [])),
    }


def _top_rejection_reasons(rejections: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for rejection in rejections:
        reason = rejection.get("reason", "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5])
