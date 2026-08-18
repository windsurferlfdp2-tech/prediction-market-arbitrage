from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from statistics import median
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.models.domain import (
    ArbitrageOpportunity,
    OrderBook,
    PaperLegFill,
    PaperTradeSimulation,
    PriceLevel,
)
from app.persistence.database import PaperTradeSimulationRecord


class PaperTradingSimulator:
    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[Any]) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker

    async def simulate(
        self,
        opportunity: ArbitrageOpportunity,
        books_after_latency: list[OrderBook] | None = None,
    ) -> PaperTradeSimulation:
        simulation = self._simulate(opportunity, books_after_latency or [])
        async with self.sessionmaker() as session:
            existing = await session.get(PaperTradeSimulationRecord, simulation.id)
            record = _record_from_simulation(opportunity, simulation)
            if existing is None:
                session.add(record)
            else:
                _update_record(existing, record)
            await session.commit()
        return simulation

    async def latest(self, limit: int = 50) -> list[PaperTradeSimulation]:
        async with self.sessionmaker() as session:
            records = list(
                (
                    await session.execute(
                        select(PaperTradeSimulationRecord)
                        .order_by(PaperTradeSimulationRecord.created_at.desc())
                        .limit(limit)
                    )
                ).scalars()
            )
        return [_simulation_from_record(record) for record in records]

    async def analytics(self) -> dict[str, object]:
        async with self.sessionmaker() as session:
            records = list((await session.execute(select(PaperTradeSimulationRecord))).scalars())
        total = len(records)
        projected_rois = [
            record.projected_net_profit / _cost_from_payload(record.payload)
            for record in records
            if _cost_from_payload(record.payload) > 0
        ]
        executable_rois = [
            record.realized_pnl / _cost_from_payload(record.payload)
            for record in records
            if _cost_from_payload(record.payload) > 0
        ]
        per_day = Counter(record.created_at.date().isoformat() for record in records)
        by_platform = Counter(
            f"{record.yes_exchange}_yes__{record.no_exchange}_no" for record in records
        )
        by_category = Counter(
            str(record.payload.get("category", "uncategorized")) for record in records
        )
        labels = {
            str(record.payload.get("label", "LIVE-DATA PAPER TRADE")) for record in records
        }
        paper_label = labels.pop() if len(labels) == 1 else "LIVE-DATA PAPER TRADE"
        return {
            "paper_label": paper_label,
            "simulated_trade_count": total,
            "simulated_fill_rate": _percentage(
                sum(1 for record in records if record.status == "complete"),
                total,
            ),
            "partial_fill_rate": _percentage(
                sum(1 for record in records if record.partial_fill),
                total,
            ),
            "hedge_failure_rate": _percentage(
                sum(1 for record in records if record.hedge_failure),
                total,
            ),
            "cumulative_simulated_pnl": sum(
                (record.realized_pnl for record in records),
                Decimal("0"),
            ),
            "median_projected_roi": _median_decimal(projected_rois),
            "median_executable_roi": _median_decimal(executable_rois),
            "paper_trades_per_day": dict(sorted(per_day.items())),
            "results_by_platform": dict(sorted(by_platform.items())),
            "results_by_category": dict(sorted(by_category.items())),
        }

    def _simulate(
        self,
        opportunity: ArbitrageOpportunity,
        books_after_latency: list[OrderBook],
    ) -> PaperTradeSimulation:
        requested_quantity = min(opportunity.max_quantity, self.settings.paper_max_position)
        if requested_quantity <= 0:
            return _empty_simulation(opportunity, "skipped", self.settings.paper_latency_ms)

        yes_book = _find_book(
            books_after_latency,
            opportunity.yes_exchange.value,
            opportunity.yes_market_id,
            "yes",
        )
        no_book = _find_book(
            books_after_latency,
            opportunity.no_exchange.value,
            opportunity.no_market_id,
            "no",
        )
        if yes_book is None or no_book is None:
            return _empty_simulation(opportunity, "disappeared", self.settings.paper_latency_ms)

        yes_fill = _fill_leg(yes_book.asks, requested_quantity)
        no_fill = _fill_leg(no_book.asks, requested_quantity)
        filled_quantity = min(yes_fill[0], no_fill[0])
        partial = filled_quantity < requested_quantity and filled_quantity > 0
        hedge_failure = yes_fill[0] > 0 and no_fill[0] == 0 or no_fill[0] > 0 and yes_fill[0] == 0
        status = "complete"
        if hedge_failure:
            status = "hedge_failed"
        elif partial:
            status = "partial_fill"
        elif filled_quantity <= 0:
            status = "disappeared"

        yes_avg = yes_fill[1] / yes_fill[0] if yes_fill[0] else Decimal("0")
        no_avg = no_fill[1] / no_fill[0] if no_fill[0] else Decimal("0")
        executable_cost = (yes_avg + no_avg) * filled_quantity
        realized = filled_quantity - executable_cost
        fills = [
            PaperLegFill(
                exchange=opportunity.yes_exchange,
                market_id=opportunity.yes_market_id,
                side=yes_book.side,
                requested_quantity=requested_quantity,
                filled_quantity=yes_fill[0],
                average_price=yes_avg,
                status=_fill_status(yes_fill[0], requested_quantity),
            ),
            PaperLegFill(
                exchange=opportunity.no_exchange,
                market_id=opportunity.no_market_id,
                side=no_book.side,
                requested_quantity=requested_quantity,
                filled_quantity=no_fill[0],
                average_price=no_avg,
                status=_fill_status(no_fill[0], requested_quantity),
            ),
        ]
        return PaperTradeSimulation(
            id=_simulation_id(opportunity),
            opportunity_id=opportunity.id,
            same_market_key=opportunity.same_market_key,
            label="LIVE-DATA PAPER TRADE" if opportunity.is_live_data else "TEST PAPER TRADE",
            data_source=opportunity.data_source,
            is_live_data=opportunity.is_live_data,
            uses_live_market_data=opportunity.is_live_data,
            created_at=datetime.now(UTC),
            latency_ms=self.settings.paper_latency_ms,
            requested_quantity=requested_quantity,
            filled_quantity=filled_quantity,
            projected_net_profit=opportunity.net_profit,
            realized_pnl=realized,
            status=status,
            partial_fill=partial,
            hedge_failure=hedge_failure,
            fills=fills,
        )


def _find_book(
    books: list[OrderBook],
    exchange: str,
    market_id: str,
    side: str,
) -> OrderBook | None:
    return next(
        (
            book
            for book in books
            if book.exchange.value == exchange
            and book.market_id == market_id
            and book.side.value == side
        ),
        None,
    )


def _fill_leg(levels: list[PriceLevel], requested_quantity: Decimal) -> tuple[Decimal, Decimal]:
    filled = Decimal("0")
    cost = Decimal("0")
    for level in sorted(levels, key=lambda item: item.price):
        if filled >= requested_quantity:
            break
        quantity = min(level.quantity, requested_quantity - filled)
        if quantity <= 0:
            continue
        filled += quantity
        cost += quantity * level.price
    return filled, cost


def _fill_status(filled: Decimal, requested: Decimal) -> str:
    if filled <= 0:
        return "failed"
    if filled < requested:
        return "partial"
    return "filled"


def _simulation_id(opportunity: ArbitrageOpportunity) -> str:
    return sha256(f"paper:{opportunity.id}".encode()).hexdigest()[:16]


def _empty_simulation(
    opportunity: ArbitrageOpportunity,
    status: str,
    latency_ms: int,
) -> PaperTradeSimulation:
    return PaperTradeSimulation(
        id=_simulation_id(opportunity),
        opportunity_id=opportunity.id,
        same_market_key=opportunity.same_market_key,
        label="LIVE-DATA PAPER TRADE" if opportunity.is_live_data else "TEST PAPER TRADE",
        data_source=opportunity.data_source,
        is_live_data=opportunity.is_live_data,
        uses_live_market_data=opportunity.is_live_data,
        created_at=datetime.now(UTC),
        latency_ms=latency_ms,
        requested_quantity=Decimal("0"),
        filled_quantity=Decimal("0"),
        projected_net_profit=opportunity.net_profit,
        realized_pnl=Decimal("0"),
        status=status,
        partial_fill=False,
        hedge_failure=status == "hedge_failed",
        fills=[],
    )


def _record_from_simulation(
    opportunity: ArbitrageOpportunity,
    simulation: PaperTradeSimulation,
) -> PaperTradeSimulationRecord:
    return PaperTradeSimulationRecord(
        id=simulation.id,
        opportunity_id=simulation.opportunity_id,
        same_market_key=simulation.same_market_key,
        created_at=simulation.created_at,
        direction=f"{opportunity.yes_exchange.value}_yes__{opportunity.no_exchange.value}_no",
        yes_exchange=opportunity.yes_exchange.value,
        no_exchange=opportunity.no_exchange.value,
        yes_market_id=opportunity.yes_market_id,
        no_market_id=opportunity.no_market_id,
        requested_quantity=simulation.requested_quantity,
        filled_quantity=simulation.filled_quantity,
        projected_gross_profit=opportunity.gross_profit,
        projected_net_profit=simulation.projected_net_profit,
        realized_pnl=simulation.realized_pnl,
        latency_ms=simulation.latency_ms,
        partial_fill=simulation.partial_fill,
        hedge_failure=simulation.hedge_failure,
        status=simulation.status,
        fills=[fill.model_dump(mode="json") for fill in simulation.fills],
        payload={
            "label": simulation.label,
            "opportunity": opportunity.model_dump(mode="json"),
            "paper_trade": simulation.model_dump(mode="json"),
        },
    )


def _update_record(
    target: PaperTradeSimulationRecord,
    source: PaperTradeSimulationRecord,
) -> None:
    for column in PaperTradeSimulationRecord.__table__.columns:
        if column.name != "id":
            setattr(target, column.name, getattr(source, column.name))


def _simulation_from_record(record: PaperTradeSimulationRecord) -> PaperTradeSimulation:
    payload = record.payload.get("paper_trade", record.payload.get("simulation"))
    return PaperTradeSimulation.model_validate(payload)


def _cost_from_payload(payload: dict[str, Any]) -> Decimal:
    opportunity = payload.get("opportunity")
    if not isinstance(opportunity, dict):
        return Decimal("0")
    return Decimal(str(opportunity.get("gross_cost", "0")))


def _percentage(count: int, total: int) -> Decimal:
    if total == 0:
        return Decimal("0")
    return Decimal(count) / Decimal(total) * Decimal("100")


def _median_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return Decimal(str(median(values)))
