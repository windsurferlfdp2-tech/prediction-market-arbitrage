from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.config import Settings
from app.models.domain import ArbitrageOpportunity, Exchange, OrderBook, PriceLevel, Side, UsedLevel
from app.persistence.database import SqlAlchemyDatabaseBackend
from app.services.paper_trading import PaperTradingSimulator


@pytest.mark.asyncio
async def test_paper_trade_complete_fill_records_realized_pnl(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'paper.db'}")
    await backend.init()
    simulator = PaperTradingSimulator(Settings(data_mode="test"), backend.sessionmaker)

    result = await simulator.simulate(
        _opportunity(quantity=Decimal("10")),
        [
            _book(Exchange.POLYMARKET, "pm", Side.YES, "0.40", "10"),
            _book(Exchange.KALSHI, "ks", Side.NO, "0.50", "10"),
        ],
    )

    assert result.label == "LIVE-DATA PAPER TRADE"
    assert result.status == "complete"
    assert result.filled_quantity == Decimal("10")
    assert result.realized_pnl == Decimal("1.00")
    assert (await simulator.analytics())["simulated_fill_rate"] == Decimal("100")


@pytest.mark.asyncio
async def test_paper_trade_partial_fill(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'partial.db'}")
    await backend.init()
    simulator = PaperTradingSimulator(Settings(data_mode="test"), backend.sessionmaker)

    result = await simulator.simulate(
        _opportunity(quantity=Decimal("10")),
        [
            _book(Exchange.POLYMARKET, "pm", Side.YES, "0.40", "4"),
            _book(Exchange.KALSHI, "ks", Side.NO, "0.50", "10"),
        ],
    )

    assert result.status == "partial_fill"
    assert result.partial_fill is True
    assert result.filled_quantity == Decimal("4")


@pytest.mark.asyncio
async def test_paper_trade_hedge_failure(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'hedge.db'}")
    await backend.init()
    simulator = PaperTradingSimulator(Settings(data_mode="test"), backend.sessionmaker)

    result = await simulator.simulate(
        _opportunity(quantity=Decimal("10")),
        [
            _book(Exchange.POLYMARKET, "pm", Side.YES, "0.40", "10"),
            _book(Exchange.KALSHI, "ks", Side.NO, "0.50", "0"),
        ],
    )

    assert result.status == "hedge_failed"
    assert result.hedge_failure is True


@pytest.mark.asyncio
async def test_paper_trade_respects_max_position_and_prevents_duplicates(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'max.db'}")
    await backend.init()
    simulator = PaperTradingSimulator(
        Settings(data_mode="test", paper_max_position=Decimal("3")),
        backend.sessionmaker,
    )
    opportunity = _opportunity(quantity=Decimal("10"))
    books = [
        _book(Exchange.POLYMARKET, "pm", Side.YES, "0.40", "10"),
        _book(Exchange.KALSHI, "ks", Side.NO, "0.50", "10"),
    ]

    first = await simulator.simulate(opportunity, books)
    second = await simulator.simulate(opportunity, books)

    assert first.requested_quantity == Decimal("3")
    assert second.id == first.id
    assert len(await simulator.latest()) == 1


def _opportunity(quantity: Decimal) -> ArbitrageOpportunity:
    return ArbitrageOpportunity(
        id="opp",
        same_market_key="verified:pair",
        title="Verified pair",
        yes_exchange=Exchange.POLYMARKET,
        no_exchange=Exchange.KALSHI,
        yes_market_id="pm",
        no_market_id="ks",
        yes_avg_price=Decimal("0.40"),
        no_avg_price=Decimal("0.50"),
        gross_cost=quantity * Decimal("0.90"),
        gross_profit=quantity * Decimal("0.10"),
        total_fees=Decimal("0"),
        slippage_cost=Decimal("0"),
        net_profit=quantity * Decimal("0.10"),
        roi=Decimal("0.10") / Decimal("0.90"),
        max_quantity=quantity,
        detected_at=datetime.now(UTC),
        freshness_seconds=Decimal("0"),
        confidence="high",
        used_levels=[
            UsedLevel(
                exchange=Exchange.POLYMARKET,
                market_id="pm",
                outcome_id="pm:yes",
                side=Side.YES,
                price=Decimal("0.40"),
                quantity=quantity,
                source_side="ask",
            )
        ],
    )


def _book(
    exchange: Exchange,
    market_id: str,
    side: Side,
    price: str,
    quantity: str,
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
            )
        ],
        fetched_at=datetime.now(UTC),
    )
