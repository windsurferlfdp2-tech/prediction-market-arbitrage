from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.arbitrage.detector import ArbitrageDetector
from app.models.domain import Exchange, Market, OrderBook, Outcome, PriceLevel, Side


def test_detector_walks_levels_and_calculates_weighted_profit() -> None:
    now = datetime.now(UTC)
    detector = ArbitrageDetector(
        max_age_seconds=30,
        min_net_profit=Decimal("0.01"),
        min_roi=Decimal("0.001"),
        fee_rate=Decimal("0.01"),
        slippage_rate=Decimal("0.005"),
    )
    markets = [_market(Exchange.POLYMARKET, "pm"), _market(Exchange.KALSHI, "ks")]
    books = [
        _book(Exchange.POLYMARKET, "pm", Side.YES, [("0.49", "100"), ("0.50", "50")], now),
        _book(Exchange.KALSHI, "ks", Side.NO, [("0.45", "80"), ("0.46", "40")], now),
    ]

    opportunities = detector.detect(markets, books)

    assert len(opportunities) == 1
    opportunity = opportunities[0]
    assert opportunity.max_quantity == Decimal("120")
    assert opportunity.yes_avg_price == Decimal("58.80") / Decimal("120")
    assert opportunity.no_avg_price == Decimal("54.00") / Decimal("120")
    assert opportunity.gross_profit == Decimal("7.20")
    assert opportunity.total_fees == Decimal("1.1280")
    assert opportunity.slippage_cost == Decimal("0.5640")
    assert opportunity.net_profit == Decimal("5.5080")
    assert opportunity.roi == opportunity.net_profit / opportunity.gross_cost
    assert len(opportunity.used_levels) == 4


def test_detector_rejects_stale_order_books() -> None:
    now = datetime.now(UTC)
    detector = ArbitrageDetector(
        max_age_seconds=30,
        min_net_profit=Decimal("0.01"),
        min_roi=Decimal("0.001"),
        fee_rate=Decimal("0"),
        slippage_rate=Decimal("0"),
    )
    markets = [_market(Exchange.POLYMARKET, "pm"), _market(Exchange.KALSHI, "ks")]
    books = [
        _book(Exchange.POLYMARKET, "pm", Side.YES, [("0.49", "100")], now - timedelta(seconds=31)),
        _book(Exchange.KALSHI, "ks", Side.NO, [("0.45", "100")], now),
    ]

    assert detector.detect(markets, books) == []


def _market(exchange: Exchange, market_id: str) -> Market:
    return Market(
        exchange=exchange,
        exchange_market_id=market_id,
        title="Same market",
        status="active",
        same_market_key="same",
        outcomes=[
            Outcome(id=f"{market_id}:yes", name="Yes", side=Side.YES),
            Outcome(id=f"{market_id}:no", name="No", side=Side.NO),
        ],
    )


def _book(
    exchange: Exchange,
    market_id: str,
    side: Side,
    asks: list[tuple[str, str]],
    fetched_at: datetime,
) -> OrderBook:
    return OrderBook(
        exchange=exchange,
        market_id=market_id,
        outcome_id=f"{market_id}:{side.value}",
        side=side,
        asks=[
            PriceLevel(price=Decimal(price), quantity=Decimal(quantity), source_side="ask")
            for price, quantity in asks
        ],
        fetched_at=fetched_at,
    )
