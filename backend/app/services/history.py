from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.domain import ArbitrageOpportunity
from app.persistence.database import OpportunityHistoryRecord


class OpportunityHistoryRecorder:
    def __init__(self, sessionmaker: async_sessionmaker[Any]) -> None:
        self.sessionmaker = sessionmaker

    async def record_refresh(
        self,
        opportunities: list[ArbitrageOpportunity],
        data_mode: str,
        observed_at: datetime | None = None,
    ) -> None:
        now = observed_at or datetime.now(UTC)
        current_ids = {opportunity.id for opportunity in opportunities}

        async with self.sessionmaker() as session:
            active_records = (
                await session.execute(
                    select(OpportunityHistoryRecord).where(
                        OpportunityHistoryRecord.data_mode == data_mode,
                        OpportunityHistoryRecord.is_active.is_(True),
                    )
                )
            ).scalars()
            active_by_id = {record.opportunity_id: record for record in active_records}

            for opportunity in opportunities:
                duration = _duration_seconds(opportunity.detected_at, now)
                existing = active_by_id.get(opportunity.id)
                if existing is None:
                    session.add(_history_record(opportunity, data_mode, now, duration))
                else:
                    _update_active_record(existing, opportunity, now, duration)

            for opportunity_id, record in active_by_id.items():
                if opportunity_id not in current_ids:
                    record.is_active = False
                    record.disappeared_at = now
                    record.duration_seconds = _duration_seconds(record.detected_at, now)
                    record.disappearance_reason = "not_present_in_latest_scan"

            await session.commit()


class OpportunityAnalyticsService:
    def __init__(self, sessionmaker: async_sessionmaker[Any]) -> None:
        self.sessionmaker = sessionmaker

    async def overview(
        self,
        data_mode: str | None = None,
        current_date: date | None = None,
    ) -> dict[str, object]:
        today = current_date or datetime.now(UTC).date()
        async with self.sessionmaker() as session:
            statement = select(OpportunityHistoryRecord)
            effective_mode = data_mode or "live"
            statement = statement.where(OpportunityHistoryRecord.data_mode == effective_mode)
            all_records = list((await session.execute(statement)).scalars())

        records = [record for record in all_records if _as_utc(record.detected_at).date() == today]
        non_live_excluded = 0
        if effective_mode == "live":
            async with self.sessionmaker() as session:
                non_live_excluded = len(
                    list(
                        (
                            await session.execute(
                                select(OpportunityHistoryRecord).where(
                                    OpportunityHistoryRecord.data_mode != "live"
                                )
                            )
                        ).scalars()
                    )
                )
        historical_excluded = len(all_records) - len(records)

        durations = [_record_duration(record) for record in records]
        rois = [record.net_roi for record in records]
        profit_values = [record.net_edge for record in records]
        per_day = Counter(_as_utc(record.detected_at).date().isoformat() for record in records)
        total = len(records)
        active = [record for record in records if record.is_active]
        duplicate_updates = sum(
            1
            for record in records
            if _as_utc(record.last_seen_at) > _as_utc(record.detected_at)
        )
        max_last_seen = max((_as_utc(record.last_seen_at) for record in all_records), default=None)
        max_detected = max((_as_utc(record.detected_at) for record in all_records), default=None)

        return {
            "analytics_data_type": effective_mode,
            "analytics_scope": "current_utc_day",
            "server_time_utc": datetime.now(UTC),
            "latest_scan_timestamp": max_last_seen,
            "latest_record_seen_timestamp": max_last_seen,
            "latest_opportunity_detected_timestamp": max_detected,
            "opportunities_detected_per_day": dict(sorted(per_day.items())),
            "median_opportunity_duration_seconds": _median_decimal(durations),
            "median_net_roi": _median_decimal(rois),
            "maximum_theoretical_profit": max(profit_values, default=Decimal("0")),
            "percentage_lasting_over_1_seconds": _percentage_over(durations, Decimal("1"), total),
            "percentage_lasting_over_3_seconds": _percentage_over(durations, Decimal("3"), total),
            "percentage_lasting_over_5_seconds": _percentage_over(durations, Decimal("5"), total),
            "percentage_lasting_over_10_seconds": _percentage_over(durations, Decimal("10"), total),
            "total_candidates_recorded": total,
            "unique_opportunities": len({record.opportunity_id for record in records}),
            "raw_detections": total,
            "duplicate_updates": duplicate_updates,
            "active_opportunities": len(active),
            "historical_records_excluded": historical_excluded,
            "simulated_records_excluded": non_live_excluded,
            "non_live_records_excluded": non_live_excluded,
        }


def _history_record(
    opportunity: ArbitrageOpportunity,
    data_mode: str,
    observed_at: datetime,
    duration_seconds: Decimal,
) -> OpportunityHistoryRecord:
    return OpportunityHistoryRecord(
        opportunity_id=opportunity.id,
        data_mode=data_mode,
        same_market_key=opportunity.same_market_key,
        yes_exchange=opportunity.yes_exchange.value,
        no_exchange=opportunity.no_exchange.value,
        yes_market_id=opportunity.yes_market_id,
        no_market_id=opportunity.no_market_id,
        market_title=opportunity.title,
        detected_at=opportunity.detected_at,
        last_seen_at=observed_at,
        disappeared_at=None,
        duration_seconds=duration_seconds,
        disappearance_reason=None,
        yes_price=opportunity.yes_avg_price,
        yes_available_size=opportunity.max_quantity,
        no_price=opportunity.no_avg_price,
        no_available_size=opportunity.max_quantity,
        combined_cost=opportunity.yes_avg_price + opportunity.no_avg_price,
        estimated_fees=opportunity.total_fees,
        estimated_slippage=opportunity.slippage_cost,
        net_edge=opportunity.net_profit,
        net_roi=opportunity.roi,
        maximum_executable_quantity=opportunity.max_quantity,
        order_book_age_seconds=opportunity.freshness_seconds,
        is_active=True,
        payload=opportunity.model_dump(mode="json"),
    )


def _update_active_record(
    record: OpportunityHistoryRecord,
    opportunity: ArbitrageOpportunity,
    observed_at: datetime,
    duration_seconds: Decimal,
) -> None:
    record.last_seen_at = observed_at
    record.duration_seconds = duration_seconds
    record.yes_price = opportunity.yes_avg_price
    record.yes_available_size = opportunity.max_quantity
    record.no_price = opportunity.no_avg_price
    record.no_available_size = opportunity.max_quantity
    record.combined_cost = opportunity.yes_avg_price + opportunity.no_avg_price
    record.estimated_fees = opportunity.total_fees
    record.estimated_slippage = opportunity.slippage_cost
    record.net_edge = opportunity.net_profit
    record.net_roi = opportunity.roi
    record.maximum_executable_quantity = opportunity.max_quantity
    record.order_book_age_seconds = opportunity.freshness_seconds
    record.payload = opportunity.model_dump(mode="json")


def _duration_seconds(start: datetime, end: datetime) -> Decimal:
    start = _as_utc(start)
    end = _as_utc(end)
    return Decimal(str(max((end - start).total_seconds(), 0)))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _record_duration(record: OpportunityHistoryRecord) -> Decimal:
    if record.disappeared_at is None:
        return record.duration_seconds
    return record.duration_seconds


def _median_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return Decimal(str(median(values)))


def _percentage_over(values: list[Decimal], threshold: Decimal, total: int) -> Decimal:
    if total == 0:
        return Decimal("0")
    count = sum(1 for value in values if value > threshold)
    return Decimal(count) / Decimal(total) * Decimal("100")
