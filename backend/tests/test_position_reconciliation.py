from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from app.config import Settings
from app.models.domain import Exchange, MarketCategory, ModelPaperTrade, Side
from app.persistence.database import ModelPaperTradeRecord, SqlAlchemyDatabaseBackend
from app.services.position_reconciliation import (
    MARKET_RESOLVED,
    MARKET_VOIDED,
    MarketResolution,
    PositionReconciliationService,
)


@pytest.mark.asyncio
async def test_yes_position_resolves_yes(tmp_path: Path) -> None:
    result, record = await _settle(tmp_path, Side.YES, Side.YES)

    assert result.proposed_status == "closed"
    assert result.proposed_exit_reason == MARKET_RESOLVED
    assert result.proposed_realized_pnl == Decimal("75.00")
    assert record.status == "closed"
    assert record.realized_pnl == Decimal("75.00")
    assert record.mark_to_market_pnl == Decimal("0")
    assert record.resolved_outcome == "yes"


@pytest.mark.asyncio
async def test_yes_position_resolves_no(tmp_path: Path) -> None:
    result, record = await _settle(tmp_path, Side.YES, Side.NO)

    assert result.proposed_realized_pnl == Decimal("-25.00")
    assert record.realized_pnl == Decimal("-25.00")
    assert record.resolved_outcome == "no"


@pytest.mark.asyncio
async def test_no_position_resolves_no(tmp_path: Path) -> None:
    result, record = await _settle(tmp_path, Side.NO, Side.NO)

    assert result.proposed_realized_pnl == Decimal("75.00")
    assert record.realized_pnl == Decimal("75.00")
    assert record.resolved_outcome == "no"


@pytest.mark.asyncio
async def test_no_position_resolves_yes(tmp_path: Path) -> None:
    result, record = await _settle(tmp_path, Side.NO, Side.YES)

    assert result.proposed_realized_pnl == Decimal("-25.00")
    assert record.realized_pnl == Decimal("-25.00")
    assert record.resolved_outcome == "yes"


@pytest.mark.asyncio
async def test_partial_fill_settlement_uses_filled_quantity(tmp_path: Path) -> None:
    result, record = await _settle(
        tmp_path,
        Side.YES,
        Side.YES,
        filled_quantity=Decimal("40"),
        entry_price=Decimal("0.25"),
    )

    assert result.settlement_value == Decimal("40")
    assert result.proposed_realized_pnl == Decimal("30.00")
    assert record.realized_pnl == Decimal("30.00")


@pytest.mark.asyncio
async def test_repeated_reconciliation_is_idempotent(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = FakeResolutionService(
        Settings(data_mode="test"),
        backend.sessionmaker,
        _resolution(Side.YES),
    )
    await _insert_trade(backend, _trade(Side.YES))

    first = await service.reconcile(apply=True)
    second = await service.reconcile(apply=True)

    assert len(first) == 1
    assert second == []
    async with backend.sessionmaker() as session:
        record = await session.get(ModelPaperTradeRecord, "trade-yes")
    assert record is not None
    assert record.realized_pnl == Decimal("75.00")


@pytest.mark.asyncio
async def test_voided_market_refunds_entry_cost(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = FakeResolutionService(
        Settings(data_mode="test"),
        backend.sessionmaker,
        MarketResolution(
            Exchange.KALSHI,
            "MKT",
            "voided",
            "finalized",
            None,
            datetime(2026, 7, 31, tzinfo=UTC),
            Decimal("1"),
            datetime(2026, 7, 31, tzinfo=UTC),
            None,
            {},
        ),
    )
    await _insert_trade(backend, _trade(Side.YES))

    result = (await service.reconcile(apply=True))[0]
    async with backend.sessionmaker() as session:
        record = await session.get(ModelPaperTradeRecord, "trade-yes")

    assert record is not None
    assert result.proposed_exit_reason == MARKET_VOIDED
    assert result.proposed_realized_pnl == Decimal("0")
    assert record.realized_pnl == Decimal("0")
    assert record.settlement_value == Decimal("25.00")


@pytest.mark.asyncio
async def test_postponed_or_pending_market_remains_open(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = FakeResolutionService(
        Settings(data_mode="test"),
        backend.sessionmaker,
        MarketResolution(
            Exchange.KALSHI,
            "MKT",
            "pending",
            "closed",
            None,
            None,
            None,
            datetime(2026, 7, 31, tzinfo=UTC),
            "market status closed is not finalized with yes/no result",
            {},
        ),
    )
    await _insert_trade(backend, _trade(Side.YES))

    result = (await service.reconcile(apply=True))[0]
    async with backend.sessionmaker() as session:
        record = await session.get(ModelPaperTradeRecord, "trade-yes")

    assert result.skipped is True
    assert record is not None
    assert record.status == "open"


@pytest.mark.asyncio
async def test_no_settlement_based_solely_on_last_price(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = FakeResolutionService(
        Settings(data_mode="test"),
        backend.sessionmaker,
        MarketResolution(
            Exchange.KALSHI,
            "MKT",
            "pending",
            "active",
            None,
            None,
            None,
            datetime(2026, 7, 31, tzinfo=UTC),
            "market status active is not finalized with yes/no result",
            {"last_price_dollars": "0.9900"},
        ),
    )
    await _insert_trade(backend, _trade(Side.YES))

    result = (await service.reconcile(apply=True))[0]

    assert result.skipped is True
    assert result.proposed_status == "open"


@pytest.mark.asyncio
async def test_live_reconciliation_skips_test_data_source(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = CountingResolutionService(
        Settings(data_mode="test"),
        backend.sessionmaker,
        _resolution(Side.YES),
    )
    await _insert_trade(backend, _trade(Side.YES, data_source="test"))

    result = (await service.reconcile(data_mode="live", apply=True))[0]
    async with backend.sessionmaker() as session:
        record = await session.get(ModelPaperTradeRecord, "trade-yes")

    assert result.skipped is True
    assert "outside live mode" in (result.skip_reason or "")
    assert service.fetch_count == 0
    assert record is not None
    assert record.status == "open"


@pytest.mark.asyncio
async def test_kalshi_finalized_raw_response_maps_yes_outcome(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = PositionReconciliationService(Settings(data_mode="test"), backend.sessionmaker)
    cast(Any, service).http = FakeHttpClient(
        {
            "market": {
                "ticker": "KXFINAL",
                "status": "finalized",
                "result": "yes",
                "settlement_ts": "2026-07-31T04:27:40.954912Z",
                "last_price_dollars": "0.9900",
            }
        }
    )

    resolution = await service.fetch_resolution(Exchange.KALSHI, "KXFINAL")

    assert resolution.state == "resolved"
    assert resolution.exchange_status == "finalized"
    assert resolution.resolved_outcome == Side.YES
    assert resolution.resolution_timestamp == datetime(
        2026, 7, 31, 4, 27, 40, 954912, tzinfo=UTC
    )
    assert resolution.raw["last_price_dollars"] == "0.9900"


@pytest.mark.asyncio
async def test_kalshi_closed_without_result_remains_pending(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = PositionReconciliationService(Settings(data_mode="test"), backend.sessionmaker)
    cast(Any, service).http = FakeHttpClient(
        {
            "market": {
                "ticker": "KXPENDING",
                "status": "closed",
                "last_price_dollars": "1.0000",
            }
        }
    )

    resolution = await service.fetch_resolution(Exchange.KALSHI, "KXPENDING")

    assert resolution.state == "pending"
    assert resolution.resolved_outcome is None
    assert "not finalized" in (resolution.skip_reason or "")


@pytest.mark.asyncio
async def test_polymarket_closed_token_winner_maps_yes_outcome(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = PositionReconciliationService(Settings(data_mode="test"), backend.sessionmaker)
    cast(Any, service).http = FakeHttpClient(
        [
            {
                "conditionId": "0xabc",
                "closed": True,
                "active": False,
                "updatedAt": "2026-07-31T01:02:03Z",
                "tokens": [
                    {"outcome": "Yes", "winner": True},
                    {"outcome": "No", "winner": False},
                ],
            }
        ]
    )

    resolution = await service.fetch_resolution(Exchange.POLYMARKET, "0xabc")

    assert resolution.state == "resolved"
    assert resolution.exchange_status == "closed"
    assert resolution.resolved_outcome == Side.YES
    assert resolution.resolution_timestamp == datetime(2026, 7, 31, 1, 2, 3, tzinfo=UTC)


@pytest.mark.asyncio
async def test_polymarket_closed_without_winner_remains_pending(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = PositionReconciliationService(Settings(data_mode="test"), backend.sessionmaker)
    cast(Any, service).http = FakeHttpClient(
        [
            {
                "conditionId": "0xabc",
                "closed": True,
                "active": False,
                "lastTradePrice": "0.99",
                "tokens": [
                    {"outcome": "Yes"},
                    {"outcome": "No"},
                ],
            }
        ]
    )

    resolution = await service.fetch_resolution(Exchange.POLYMARKET, "0xabc")

    assert resolution.state == "pending"
    assert resolution.resolved_outcome is None
    assert "no final winning YES/NO outcome" in (resolution.skip_reason or "")


@pytest.mark.asyncio
async def test_polymarket_voided_raw_response_maps_voided(tmp_path: Path) -> None:
    backend = await _backend(tmp_path)
    service = PositionReconciliationService(Settings(data_mode="test"), backend.sessionmaker)
    cast(Any, service).http = FakeHttpClient(
        [
            {
                "conditionId": "0xvoid",
                "closed": True,
                "active": False,
                "status": "voided",
                "updatedAt": "2026-07-31T01:02:03Z",
            }
        ]
    )

    resolution = await service.fetch_resolution(Exchange.POLYMARKET, "0xvoid")

    assert resolution.state == "voided"
    assert resolution.exchange_status == "voided"
    assert resolution.resolution_timestamp == datetime(2026, 7, 31, 1, 2, 3, tzinfo=UTC)


class FakeResolutionService(PositionReconciliationService):
    def __init__(
        self,
        settings: Settings,
        sessionmaker: Any,
        resolution: MarketResolution,
    ) -> None:
        super().__init__(settings, sessionmaker)
        self.resolution = resolution

    async def fetch_resolution(self, exchange: Exchange, market_id: str) -> MarketResolution:
        return self.resolution


class CountingResolutionService(FakeResolutionService):
    def __init__(
        self,
        settings: Settings,
        sessionmaker: Any,
        resolution: MarketResolution,
    ) -> None:
        super().__init__(settings, sessionmaker, resolution)
        self.fetch_count = 0

    async def fetch_resolution(self, exchange: Exchange, market_id: str) -> MarketResolution:
        self.fetch_count += 1
        return await super().fetch_resolution(exchange, market_id)


class FakeHttpClient:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((url, params))
        return self.payload


async def _settle(
    tmp_path: Path,
    direction: Side,
    resolved: Side,
    filled_quantity: Decimal = Decimal("100"),
    entry_price: Decimal = Decimal("0.25"),
) -> tuple[Any, ModelPaperTradeRecord]:
    backend = await _backend(tmp_path)
    trade = _trade(direction, filled_quantity=filled_quantity, entry_price=entry_price)
    await _insert_trade(backend, trade)
    service = FakeResolutionService(
        Settings(data_mode="test"),
        backend.sessionmaker,
        _resolution(resolved),
    )
    result = (await service.reconcile(apply=True))[0]
    async with backend.sessionmaker() as session:
        record = await session.get(ModelPaperTradeRecord, trade.id)
    assert record is not None
    return result, record


async def _backend(tmp_path: Path) -> SqlAlchemyDatabaseBackend:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'settlement.db'}")
    await backend.init()
    return backend


async def _insert_trade(
    backend: SqlAlchemyDatabaseBackend,
    trade: ModelPaperTrade,
) -> None:
    async with backend.sessionmaker() as session:
        session.add(
            ModelPaperTradeRecord(
                id=trade.id,
                opportunity_id=trade.opportunity_id,
                prediction_id=trade.prediction_id,
                model_id=trade.model_id,
                market_id=trade.market_id,
                exchange=trade.exchange.value,
                category=trade.category.value,
                direction=trade.direction.value,
                created_at=trade.created_at,
                status=trade.status,
                label=trade.label,
                requested_quantity=trade.requested_quantity,
                filled_quantity=trade.filled_quantity,
                entry_price=trade.entry_price,
                position_size=trade.position_size,
                expected_edge=trade.expected_edge,
                mark_to_market_pnl=trade.mark_to_market_pnl,
                realized_pnl=trade.realized_pnl,
                exit_reason=trade.exit_reason,
                payload=trade.model_dump(mode="json"),
            )
        )
        await session.commit()


def _trade(
    direction: Side,
    filled_quantity: Decimal = Decimal("100"),
    entry_price: Decimal = Decimal("0.25"),
    data_source: Literal["live", "test"] = "live",
) -> ModelPaperTrade:
    return ModelPaperTrade(
        id=f"trade-{direction.value}",
        opportunity_id="opp",
        prediction_id="pred",
        model_id="model",
        market_id="MKT",
        exchange=Exchange.KALSHI,
        category=MarketCategory.GENERAL,
        direction=direction,
        created_at=datetime(2026, 7, 31, tzinfo=UTC),
        status="open",
        requested_quantity=filled_quantity,
        filled_quantity=filled_quantity,
        entry_price=entry_price,
        position_size=filled_quantity * entry_price,
        expected_edge=Decimal("1"),
        mark_to_market_pnl=Decimal("5"),
        realized_pnl=Decimal("0"),
        exit_reason=None,
        model_version="v1",
        calibration_version="c1",
        data_source=data_source,
        is_live_data=data_source == "live",
        uses_live_market_data=data_source == "live",
    )


def _resolution(outcome: Side) -> MarketResolution:
    return MarketResolution(
        Exchange.KALSHI,
        "MKT",
        "resolved",
        "finalized",
        outcome,
        datetime(2026, 7, 31, tzinfo=UTC),
        Decimal("1"),
        datetime(2026, 7, 31, tzinfo=UTC),
        None,
        {},
    )
