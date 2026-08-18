from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.arbitrage.detector import ArbitrageDetector
from app.models.domain import (
    ArbitrageOpportunity,
    Exchange,
    Market,
    OrderBook,
    Outcome,
    PriceLevel,
    Side,
)


@dataclass(frozen=True)
class ExpectedEconomics:
    quantity: Decimal
    total_cost: Decimal
    payout: Decimal
    gross_profit: Decimal
    fees: Decimal
    slippage: Decimal
    net_profit: Decimal
    roi: Decimal


ZERO_ECONOMICS = ExpectedEconomics(
    quantity=Decimal("0"),
    total_cost=Decimal("0"),
    payout=Decimal("0"),
    gross_profit=Decimal("0"),
    fees=Decimal("0"),
    slippage=Decimal("0"),
    net_profit=Decimal("0"),
    roi=Decimal("0"),
)


def test_yes_ask_plus_no_ask_below_one_creates_arbitrage() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("10"),
        total_cost=Decimal("9.50"),
        payout=Decimal("10"),
        gross_profit=Decimal("0.50"),
        fees=Decimal("0.00"),
        slippage=Decimal("0.00"),
        net_profit=Decimal("0.50"),
        roi=Decimal("0.50") / Decimal("9.50"),
    )

    opportunity = _single_opportunity(yes_asks=[("0.45", "10")], no_asks=[("0.50", "10")])

    _assert_economics(opportunity, expected)


def test_kalshi_yes_plus_polymarket_no_below_one_creates_arbitrage() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("10"),
        total_cost=Decimal("9.40"),
        payout=Decimal("10"),
        gross_profit=Decimal("0.60"),
        fees=Decimal("0.00"),
        slippage=Decimal("0.00"),
        net_profit=Decimal("0.60"),
        roi=Decimal("0.60") / Decimal("9.40"),
    )
    now = datetime.now(UTC)
    detector = _detector()

    opportunities = detector.detect(
        [_market(Exchange.POLYMARKET, "pm"), _market(Exchange.KALSHI, "ks")],
        [
            _book(Exchange.KALSHI, "ks", Side.YES, [("0.44", "10")], now),
            _book(Exchange.POLYMARKET, "pm", Side.NO, [("0.50", "10")], now),
        ],
    )

    assert len(opportunities) == 1
    _assert_economics(opportunities[0], expected)
    assert opportunities[0].yes_exchange == Exchange.KALSHI
    assert opportunities[0].no_exchange == Exchange.POLYMARKET


def test_same_exchange_books_do_not_create_cross_platform_arbitrage() -> None:
    now = datetime.now(UTC)
    detector = _detector()

    opportunities = detector.detect(
        [_market(Exchange.KALSHI, "ks-yes"), _market(Exchange.KALSHI, "ks-no")],
        [
            _book(Exchange.KALSHI, "ks-yes", Side.YES, [("0.48", "500")], now),
            _book(Exchange.KALSHI, "ks-no", Side.NO, [("0.24", "500")], now),
        ],
    )

    assert opportunities == []


def test_combined_price_exactly_one_is_not_arbitrage() -> None:
    expected = ZERO_ECONOMICS

    opportunities = _detect(yes_asks=[("0.50", "10")], no_asks=[("0.50", "10")])

    assert opportunities == []
    assert expected.quantity == Decimal("0")
    assert expected.total_cost == Decimal("0")
    assert expected.payout == Decimal("0")
    assert expected.gross_profit == Decimal("0")
    assert expected.fees == Decimal("0")
    assert expected.net_profit == Decimal("0")
    assert expected.roi == Decimal("0")
    detector = _detector()
    now = datetime.now(UTC)
    assert detector.detect(
        [_market(Exchange.POLYMARKET, "pm"), _market(Exchange.KALSHI, "ks")],
        [
            _book(Exchange.POLYMARKET, "pm", Side.YES, [("0.50", "10")], now),
            _book(Exchange.KALSHI, "ks", Side.NO, [("0.50", "10")], now),
        ],
    ) == []
    assert detector.last_rejection_counts["combined_cost_at_or_above_payout"] == 1


def test_combined_price_above_one_is_not_arbitrage() -> None:
    expected = ZERO_ECONOMICS

    opportunities = _detect(yes_asks=[("0.51", "10")], no_asks=[("0.50", "10")])

    assert opportunities == []
    assert expected.quantity == Decimal("0")
    assert expected.total_cost == Decimal("0")
    assert expected.payout == Decimal("0")
    assert expected.gross_profit == Decimal("0")
    assert expected.fees == Decimal("0")
    assert expected.net_profit == Decimal("0")
    assert expected.roi == Decimal("0")


def test_multiple_order_book_levels_use_weighted_prices() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("120"),
        total_cost=Decimal("113.40"),
        payout=Decimal("120"),
        gross_profit=Decimal("6.60"),
        fees=Decimal("0.00"),
        slippage=Decimal("0.00"),
        net_profit=Decimal("6.60"),
        roi=Decimal("6.60") / Decimal("113.40"),
    )

    opportunity = _single_opportunity(
        yes_asks=[("0.49", "100"), ("0.50", "50")],
        no_asks=[("0.45", "80"), ("0.46", "40")],
    )

    _assert_economics(opportunity, expected)
    assert len(opportunity.used_levels) == 6


def test_unequal_yes_and_no_liquidity_matches_smaller_side() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("25"),
        total_cost=Decimal("22.50"),
        payout=Decimal("25"),
        gross_profit=Decimal("2.50"),
        fees=Decimal("0.00"),
        slippage=Decimal("0.00"),
        net_profit=Decimal("2.50"),
        roi=Decimal("2.50") / Decimal("22.50"),
    )

    opportunity = _single_opportunity(
        yes_asks=[("0.40", "25")],
        no_asks=[("0.50", "100")],
    )

    _assert_economics(opportunity, expected)


def test_fees_can_eliminate_profit() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("100"),
        total_cost=Decimal("99.00"),
        payout=Decimal("100"),
        gross_profit=Decimal("1.00"),
        fees=Decimal("1.9800"),
        slippage=Decimal("0.00"),
        net_profit=Decimal("-0.9800"),
        roi=Decimal("-0.9800") / Decimal("99.00"),
    )

    opportunities = _detect(
        yes_asks=[("0.49", "100")],
        no_asks=[("0.50", "100")],
        fee_rate=Decimal("0.02"),
    )

    assert opportunities == []
    assert expected.quantity == Decimal("100")
    assert expected.total_cost == Decimal("99.00")
    assert expected.payout == Decimal("100")
    assert expected.gross_profit == Decimal("1.00")
    assert expected.fees == Decimal("1.9800")
    assert expected.net_profit == Decimal("-0.9800")
    assert expected.roi == Decimal("-0.9800") / Decimal("99.00")


def test_slippage_can_eliminate_profit() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("100"),
        total_cost=Decimal("99.00"),
        payout=Decimal("100"),
        gross_profit=Decimal("1.00"),
        fees=Decimal("0.00"),
        slippage=Decimal("1.9800"),
        net_profit=Decimal("-0.9800"),
        roi=Decimal("-0.9800") / Decimal("99.00"),
    )

    opportunities = _detect(
        yes_asks=[("0.49", "100")],
        no_asks=[("0.50", "100")],
        slippage_rate=Decimal("0.02"),
    )

    assert opportunities == []
    assert expected.quantity == Decimal("100")
    assert expected.total_cost == Decimal("99.00")
    assert expected.payout == Decimal("100")
    assert expected.gross_profit == Decimal("1.00")
    assert expected.slippage == Decimal("1.9800")
    assert expected.net_profit == Decimal("-0.9800")
    assert expected.roi == Decimal("-0.9800") / Decimal("99.00")


def test_stale_order_books_are_ignored() -> None:
    expected = ZERO_ECONOMICS
    now = datetime.now(UTC)

    opportunities = _detect(
        yes_asks=[("0.40", "10")],
        no_asks=[("0.50", "10")],
        yes_fetched_at=now - timedelta(seconds=31),
        now=now,
    )

    assert opportunities == []
    assert expected.quantity == Decimal("0")
    assert expected.total_cost == Decimal("0")
    assert expected.payout == Decimal("0")
    assert expected.gross_profit == Decimal("0")
    assert expected.fees == Decimal("0")
    assert expected.net_profit == Decimal("0")
    assert expected.roi == Decimal("0")
    detector = _detector()
    assert detector.detect(
        [_market(Exchange.POLYMARKET, "pm"), _market(Exchange.KALSHI, "ks")],
        [
            _book(
                Exchange.POLYMARKET,
                "pm",
                Side.YES,
                [("0.40", "10")],
                now - timedelta(seconds=31),
            ),
            _book(Exchange.KALSHI, "ks", Side.NO, [("0.50", "10")], now),
        ],
    ) == []
    assert detector.last_rejection_counts["stale_order_book"] == 1


def test_empty_order_books_are_ignored() -> None:
    expected = ZERO_ECONOMICS

    opportunities = _detect(yes_asks=[], no_asks=[("0.50", "10")])

    assert opportunities == []
    assert expected.quantity == Decimal("0")
    assert expected.total_cost == Decimal("0")
    assert expected.payout == Decimal("0")
    assert expected.gross_profit == Decimal("0")
    assert expected.fees == Decimal("0")
    assert expected.net_profit == Decimal("0")
    assert expected.roi == Decimal("0")


def test_malformed_prices_are_skipped_before_evaluation() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("10"),
        total_cost=Decimal("9.00"),
        payout=Decimal("10"),
        gross_profit=Decimal("1.00"),
        fees=Decimal("0.00"),
        slippage=Decimal("0.00"),
        net_profit=Decimal("1.00"),
        roi=Decimal("1.00") / Decimal("9.00"),
    )
    yes_levels = [
        _level(Decimal("NaN"), Decimal("10")),
        _level(Decimal("-0.01"), Decimal("10")),
        _level(Decimal("1.01"), Decimal("10")),
        _level(Decimal("0.40"), Decimal("10")),
    ]

    opportunity = _single_opportunity_from_levels(
        yes_levels=yes_levels,
        no_levels=[_level(Decimal("0.50"), Decimal("10"))],
    )

    _assert_economics(opportunity, expected)


def test_partial_executable_quantity_stops_when_next_level_is_unprofitable() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("50"),
        total_cost=Decimal("45.50"),
        payout=Decimal("50"),
        gross_profit=Decimal("4.50"),
        fees=Decimal("0.00"),
        slippage=Decimal("0.00"),
        net_profit=Decimal("4.50"),
        roi=Decimal("4.50") / Decimal("45.50"),
    )

    opportunity = _single_opportunity(
        yes_asks=[("0.40", "100")],
        no_asks=[("0.50", "40"), ("0.55", "10"), ("0.61", "50")],
    )

    _assert_economics(opportunity, expected)
    assert opportunity.used_levels[-1].price == Decimal("0.55")


def test_decimal_precision_is_preserved() -> None:
    expected = ExpectedEconomics(
        quantity=Decimal("3"),
        total_cost=Decimal("2.999999999999999997"),
        payout=Decimal("3"),
        gross_profit=Decimal("0.000000000000000003"),
        fees=Decimal("0.00"),
        slippage=Decimal("0.00"),
        net_profit=Decimal("0.000000000000000003"),
        roi=Decimal("0.000000000000000003") / Decimal("2.999999999999999997"),
    )

    opportunity = _single_opportunity(
        yes_asks=[("0.333333333333333333", "3")],
        no_asks=[("0.666666666666666666", "3")],
        min_net_profit=Decimal("0.0000000000000000001"),
        min_roi=Decimal("0"),
    )

    _assert_economics(opportunity, expected)


def test_missing_verified_pair_is_reported() -> None:
    detector = _detector()
    now = datetime.now(UTC)
    markets = [
        _market(Exchange.POLYMARKET, "pm").model_copy(update={"same_market_key": None}),
        _market(Exchange.KALSHI, "ks").model_copy(update={"same_market_key": None}),
    ]

    opportunities = detector.detect(
        markets,
        [
            _book(Exchange.POLYMARKET, "pm", Side.YES, [("0.40", "10")], now),
            _book(Exchange.KALSHI, "ks", Side.NO, [("0.50", "10")], now),
        ],
    )

    assert opportunities == []
    assert detector.last_rejection_counts["no_verified_pair"] == 1
    assert detector.last_rejection_counts["missing_verified_pair"] == 2


def test_rejection_counter_reports_profit_filter() -> None:
    detector = _detector(min_net_profit=Decimal("2"))
    now = datetime.now(UTC)

    opportunities = detector.detect(
        [_market(Exchange.POLYMARKET, "pm"), _market(Exchange.KALSHI, "ks")],
        [
            _book(Exchange.POLYMARKET, "pm", Side.YES, [("0.49", "100")], now),
            _book(Exchange.KALSHI, "ks", Side.NO, [("0.50", "100")], now),
        ],
    )

    assert opportunities == []
    assert detector.last_diagnostics["raw_pricing_discrepancies"] == 1
    assert detector.last_rejection_counts["profit_below_minimum"] == 1


def _single_opportunity(
    yes_asks: list[tuple[str, str]],
    no_asks: list[tuple[str, str]],
    fee_rate: Decimal = Decimal("0"),
    slippage_rate: Decimal = Decimal("0"),
    min_net_profit: Decimal = Decimal("0.01"),
    min_roi: Decimal = Decimal("0.001"),
) -> ArbitrageOpportunity:
    opportunities = _detect(
        yes_asks=yes_asks,
        no_asks=no_asks,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        min_net_profit=min_net_profit,
        min_roi=min_roi,
    )
    assert len(opportunities) == 1
    return opportunities[0]


def _single_opportunity_from_levels(
    yes_levels: list[PriceLevel],
    no_levels: list[PriceLevel],
) -> ArbitrageOpportunity:
    now = datetime.now(UTC)
    detector = _detector()
    opportunities = detector.detect(
        [_market(Exchange.POLYMARKET, "pm"), _market(Exchange.KALSHI, "ks")],
        [
            _book_from_levels(Exchange.POLYMARKET, "pm", Side.YES, yes_levels, now),
            _book_from_levels(Exchange.KALSHI, "ks", Side.NO, no_levels, now),
        ],
    )
    assert len(opportunities) == 1
    return opportunities[0]


def _detect(
    yes_asks: list[tuple[str, str]],
    no_asks: list[tuple[str, str]],
    fee_rate: Decimal = Decimal("0"),
    slippage_rate: Decimal = Decimal("0"),
    min_net_profit: Decimal = Decimal("0.01"),
    min_roi: Decimal = Decimal("0.001"),
    yes_fetched_at: datetime | None = None,
    no_fetched_at: datetime | None = None,
    now: datetime | None = None,
) -> list[ArbitrageOpportunity]:
    fetched_at = now or datetime.now(UTC)
    detector = _detector(
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        min_net_profit=min_net_profit,
        min_roi=min_roi,
    )
    return detector.detect(
        [_market(Exchange.POLYMARKET, "pm"), _market(Exchange.KALSHI, "ks")],
        [
            _book(Exchange.POLYMARKET, "pm", Side.YES, yes_asks, yes_fetched_at or fetched_at),
            _book(Exchange.KALSHI, "ks", Side.NO, no_asks, no_fetched_at or fetched_at),
        ],
    )


def _detector(
    fee_rate: Decimal = Decimal("0"),
    slippage_rate: Decimal = Decimal("0"),
    min_net_profit: Decimal = Decimal("0.01"),
    min_roi: Decimal = Decimal("0.001"),
) -> ArbitrageDetector:
    return ArbitrageDetector(
        max_age_seconds=30,
        min_net_profit=min_net_profit,
        min_roi=min_roi,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )


def _assert_economics(opportunity: ArbitrageOpportunity, expected: ExpectedEconomics) -> None:
    assert opportunity.max_quantity == expected.quantity
    assert opportunity.gross_cost == expected.total_cost
    assert opportunity.max_quantity == expected.payout
    assert opportunity.gross_profit == expected.gross_profit
    assert opportunity.total_fees == expected.fees
    assert opportunity.slippage_cost == expected.slippage
    assert opportunity.net_profit == expected.net_profit
    assert opportunity.roi == expected.roi


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
    return _book_from_levels(
        exchange,
        market_id,
        side,
        [_level(Decimal(price), Decimal(quantity)) for price, quantity in asks],
        fetched_at,
    )


def _book_from_levels(
    exchange: Exchange,
    market_id: str,
    side: Side,
    asks: list[PriceLevel],
    fetched_at: datetime,
) -> OrderBook:
    return OrderBook(
        exchange=exchange,
        market_id=market_id,
        outcome_id=f"{market_id}:{side.value}",
        side=side,
        asks=asks,
        fetched_at=fetched_at,
    )


def _level(price: Decimal, quantity: Decimal) -> PriceLevel:
    return PriceLevel.model_construct(
        price=price,
        quantity=quantity,
        source_side="ask",
        raw={},
    )
