from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.domain import ArbitrageOpportunity, Exchange, UsedLevel
from app.persistence.database import (
    OpportunityHistoryRecord,
    SchemaMigrationRecord,
    SqlAlchemyDatabaseBackend,
)
from app.services.history import OpportunityAnalyticsService, OpportunityHistoryRecorder


@pytest.mark.asyncio
async def test_history_records_updates_and_disappearance(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'history.db'}")
    await backend.init()
    recorder = OpportunityHistoryRecorder(backend.sessionmaker)
    first_seen = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)
    opportunity = _opportunity("opp-1", first_seen)

    await recorder.record_refresh([opportunity], "test", first_seen)
    await recorder.record_refresh([opportunity], "test", first_seen + timedelta(seconds=4))
    await recorder.record_refresh([], "test", first_seen + timedelta(seconds=9))

    async with backend.sessionmaker() as session:
        records = list((await session.execute(select(OpportunityHistoryRecord))).scalars())
        migrations = list((await session.execute(select(SchemaMigrationRecord))).scalars())

    assert [migration.version for migration in migrations] == [
        "0001_opportunity_history",
            "0002_market_pair_reviews",
            "0003_phase_2_paper_and_books",
            "0004_phase_3_prediction_models",
            "0005_model_registry_fingerprint",
            "0006_model_paper_trade_settlement",
        ]
    assert len(records) == 1
    record = records[0]
    assert record.opportunity_id == "opp-1"
    assert record.data_mode == "test"
    assert record.yes_exchange == "polymarket"
    assert record.no_exchange == "kalshi"
    assert record.yes_market_id == "pm-1"
    assert record.no_market_id == "ks-1"
    assert record.market_title == "TEST: test"
    assert record.detected_at == first_seen
    assert record.disappeared_at == first_seen + timedelta(seconds=9)
    assert record.duration_seconds == Decimal("9.0")
    assert record.disappearance_reason == "not_present_in_latest_scan"
    assert record.yes_price == Decimal("0.42")
    assert record.yes_available_size == Decimal("100")
    assert record.no_price == Decimal("0.52")
    assert record.no_available_size == Decimal("100")
    assert record.combined_cost == Decimal("0.94")
    assert record.estimated_fees == Decimal("1")
    assert record.estimated_slippage == Decimal("0.5")
    assert record.net_edge == Decimal("4.5")
    assert record.maximum_executable_quantity == Decimal("100")
    assert record.order_book_age_seconds == Decimal("0.25")
    assert record.is_active is False


@pytest.mark.asyncio
async def test_analytics_summary(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'analytics.db'}")
    await backend.init()
    recorder = OpportunityHistoryRecorder(backend.sessionmaker)
    analytics = OpportunityAnalyticsService(backend.sessionmaker)
    observed_at = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)

    await recorder.record_refresh(
        [
            _opportunity("opp-1", observed_at, net_profit=Decimal("4"), roi=Decimal("0.04")),
            _opportunity("opp-2", observed_at, net_profit=Decimal("8"), roi=Decimal("0.08")),
        ],
        "test",
        observed_at,
    )
    await recorder.record_refresh(
        [_opportunity("opp-2", observed_at, net_profit=Decimal("8"), roi=Decimal("0.08"))],
        "test",
        observed_at + timedelta(seconds=2),
    )
    await recorder.record_refresh([], "test", observed_at + timedelta(seconds=6))

    result = await analytics.overview("test", current_date=observed_at.date())

    assert result["opportunities_detected_per_day"] == {"2026-07-20": 2}
    assert result["median_opportunity_duration_seconds"] == Decimal("4.0")
    assert result["median_net_roi"] == Decimal("0.06")
    assert result["maximum_theoretical_profit"] == Decimal("8")
    assert result["percentage_lasting_over_1_seconds"] == Decimal("100")
    assert result["percentage_lasting_over_3_seconds"] == Decimal("50.0")
    assert result["percentage_lasting_over_5_seconds"] == Decimal("50.0")
    assert result["percentage_lasting_over_10_seconds"] == Decimal("0")
    assert result["total_candidates_recorded"] == 2
    assert result["unique_opportunities"] == 2
    assert result["raw_detections"] == 2
    assert result["duplicate_updates"] == 1


@pytest.mark.asyncio
async def test_analytics_excludes_historical_rows_from_current_day(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'current-day.db'}")
    await backend.init()
    recorder = OpportunityHistoryRecorder(backend.sessionmaker)
    analytics = OpportunityAnalyticsService(backend.sessionmaker)
    yesterday = datetime(2026, 7, 20, 23, 59, 0, tzinfo=UTC)
    today = datetime(2026, 7, 21, 0, 1, 0, tzinfo=UTC)

    await recorder.record_refresh([_opportunity("old-live", yesterday)], "live", yesterday)
    await recorder.record_refresh([_opportunity("today-live", today)], "live", today)

    result = await analytics.overview("live", current_date=today.date())

    assert result["opportunities_detected_per_day"] == {"2026-07-21": 1}
    assert result["total_candidates_recorded"] == 1
    assert result["historical_records_excluded"] == 1
    assert result["latest_opportunity_detected_timestamp"] == today


@pytest.mark.asyncio
async def test_active_duration_uses_last_executable_duration_not_wall_clock(
    tmp_path: Path,
) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'active-duration.db'}")
    await backend.init()
    recorder = OpportunityHistoryRecorder(backend.sessionmaker)
    analytics = OpportunityAnalyticsService(backend.sessionmaker)
    observed_at = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)

    await recorder.record_refresh([_opportunity("active", observed_at)], "test", observed_at)
    await recorder.record_refresh(
        [_opportunity("active", observed_at)],
        "test",
        observed_at + timedelta(seconds=4),
    )

    result = await analytics.overview("test", current_date=observed_at.date())

    assert result["median_opportunity_duration_seconds"] == Decimal("4.0")
    assert result["active_opportunities"] == 1


def _opportunity(
    opportunity_id: str,
    detected_at: datetime,
    net_profit: Decimal = Decimal("4.5"),
    roi: Decimal = Decimal("0.045"),
) -> ArbitrageOpportunity:
    return ArbitrageOpportunity(
        id=opportunity_id,
        same_market_key="TEST:test",
        title="TEST: test",
        yes_exchange=Exchange.POLYMARKET,
        no_exchange=Exchange.KALSHI,
        yes_market_id="pm-1",
        no_market_id="ks-1",
        yes_avg_price=Decimal("0.42"),
        no_avg_price=Decimal("0.52"),
        gross_cost=Decimal("94"),
        gross_profit=Decimal("6"),
        total_fees=Decimal("1"),
        slippage_cost=Decimal("0.5"),
        net_profit=net_profit,
        roi=roi,
        max_quantity=Decimal("100"),
        detected_at=detected_at,
        freshness_seconds=Decimal("0.25"),
        confidence="high",
        used_levels=[
            UsedLevel(
                exchange=Exchange.POLYMARKET,
                market_id="pm-1",
                outcome_id="pm-1:yes",
                side="yes",
                price=Decimal("0.42"),
                quantity=Decimal("100"),
                source_side="ask",
            ),
            UsedLevel(
                exchange=Exchange.KALSHI,
                market_id="ks-1",
                outcome_id="ks-1:no",
                side="no",
                price=Decimal("0.52"),
                quantity=Decimal("100"),
                source_side="ask",
            ),
        ],
    )
