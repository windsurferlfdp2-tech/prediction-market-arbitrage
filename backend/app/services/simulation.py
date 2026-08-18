from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.models.domain import Exchange, Market, OrderBook, Outcome, PriceLevel, Side

TEST_PREFIX = "TEST"


@dataclass(frozen=True)
class SimulationScenario:
    key: str
    title: str
    yes_asks: list[tuple[str, str]]
    no_asks: list[tuple[str, str]]


def simulated_markets_and_books(
    now: datetime | None = None,
) -> tuple[list[Market], list[OrderBook]]:
    fetched_at = now or datetime.now(UTC)
    scenarios = [
        SimulationScenario(
            key="simulation-fed-rate-cut",
            title="Fed cuts rates at next meeting",
            yes_asks=[("0.42", "120"), ("0.44", "80")],
            no_asks=[("0.52", "100"), ("0.54", "100")],
        ),
        SimulationScenario(
            key="simulation-election-turnout",
            title="Election turnout above threshold",
            yes_asks=[("0.31", "60"), ("0.33", "40")],
            no_asks=[("0.62", "70"), ("0.64", "30")],
        ),
        SimulationScenario(
            key="simulation-inflation-print",
            title="Inflation print below consensus",
            yes_asks=[("0.58", "50"), ("0.60", "50")],
            no_asks=[("0.34", "40"), ("0.36", "60")],
        ),
    ]
    markets: list[Market] = []
    books: list[OrderBook] = []
    for index, scenario in enumerate(scenarios, start=1):
        same_market_key = f"{TEST_PREFIX}:{scenario.key}"
        poly_market_id = f"SIM-POLY-{index}"
        kalshi_market_id = f"SIM-KALSHI-{index}"
        title = f"{TEST_PREFIX}: {scenario.title}"
        markets.extend(
            [
                _market(Exchange.POLYMARKET, poly_market_id, title, same_market_key, fetched_at),
                _market(Exchange.KALSHI, kalshi_market_id, title, same_market_key, fetched_at),
            ]
        )
        books.extend(
            [
                _book(
                    Exchange.POLYMARKET,
                    poly_market_id,
                    Side.YES,
                    scenario.yes_asks,
                    fetched_at,
                ),
                _book(
                    Exchange.KALSHI,
                    kalshi_market_id,
                    Side.NO,
                    scenario.no_asks,
                    fetched_at,
                ),
            ]
        )
    return markets, books


def _market(
    exchange: Exchange,
    market_id: str,
    title: str,
    same_market_key: str,
    fetched_at: datetime,
) -> Market:
    return Market(
        exchange=exchange,
        exchange_market_id=market_id,
        title=title,
        status="test",
        same_market_key=same_market_key,
        fetched_at=fetched_at,
        outcomes=[
            Outcome(id=f"{market_id}:yes", name="Yes", side=Side.YES),
            Outcome(id=f"{market_id}:no", name="No", side=Side.NO),
        ],
        raw={"mode": TEST_PREFIX},
        data_source="test",
        is_live_data=False,
        source_timestamp=fetched_at,
        freshness_status="TEST",
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
            PriceLevel(
                price=Decimal(price),
                quantity=Decimal(quantity),
                source_side="ask",
                raw={"mode": TEST_PREFIX},
            )
            for price, quantity in asks
        ],
        fetched_at=fetched_at,
        exchange_timestamp=fetched_at,
        raw={"mode": TEST_PREFIX},
        data_source="test",
        is_live_data=False,
    )
