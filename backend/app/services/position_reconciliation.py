from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Any, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import DataMode, Settings
from app.exchanges.http import RetryingHttpClient
from app.models.domain import Exchange, ModelPaperTrade, Side
from app.persistence.database import ModelPaperTradeRecord

log = structlog.get_logger()

ResolutionState = Literal["resolved", "voided", "pending", "unavailable"]
MARKET_RESOLVED = "MARKET_RESOLVED"
MARKET_VOIDED = "MARKET_VOIDED"


@dataclass(frozen=True)
class MarketResolution:
    exchange: Exchange
    market_id: str
    state: ResolutionState
    exchange_status: str | None
    resolved_outcome: Side | None
    resolution_timestamp: datetime | None
    settlement_value: Decimal | None
    last_resolution_check_timestamp: datetime
    skip_reason: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class PositionReconciliationResult:
    position_id: str
    opportunity_id: str
    prediction_id: str
    exchange: str
    market_id: str
    position_side: str
    entry_price: Decimal
    quantity: Decimal
    previous_status: str
    proposed_status: str
    exchange_status: str | None
    resolved_outcome: str | None
    resolution_timestamp: datetime | None
    last_resolution_check_timestamp: datetime
    settlement_value: Decimal | None
    previous_realized_pnl: Decimal
    proposed_realized_pnl: Decimal
    previous_mark_to_market_pnl: Decimal
    proposed_mark_to_market_pnl: Decimal
    previous_exit_reason: str | None
    proposed_exit_reason: str | None
    applied: bool
    skipped: bool
    skip_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "opportunity_id": self.opportunity_id,
            "prediction_id": self.prediction_id,
            "exchange": self.exchange,
            "market_id": self.market_id,
            "position_side": self.position_side,
            "entry_price": str(self.entry_price),
            "quantity": str(self.quantity),
            "previous_status": self.previous_status,
            "proposed_status": self.proposed_status,
            "exchange_status": self.exchange_status,
            "resolved_outcome": self.resolved_outcome,
            "resolution_timestamp": (
                self.resolution_timestamp.isoformat() if self.resolution_timestamp else None
            ),
            "last_resolution_check_timestamp": self.last_resolution_check_timestamp.isoformat(),
            "settlement_value": str(self.settlement_value)
            if self.settlement_value is not None
            else None,
            "previous_realized_pnl": str(self.previous_realized_pnl),
            "proposed_realized_pnl": str(self.proposed_realized_pnl),
            "previous_mark_to_market_pnl": str(self.previous_mark_to_market_pnl),
            "proposed_mark_to_market_pnl": str(self.proposed_mark_to_market_pnl),
            "previous_exit_reason": self.previous_exit_reason,
            "proposed_exit_reason": self.proposed_exit_reason,
            "applied": self.applied,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


class PositionReconciliationService:
    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[Any]) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.http = RetryingHttpClient(
            settings.request_timeout_seconds,
            settings.request_retries,
            settings.request_backoff_seconds,
        )

    async def reconcile(
        self,
        *,
        position_id: str | None = None,
        market_id: str | None = None,
        data_mode: DataMode | None = None,
        apply: bool = False,
    ) -> list[PositionReconciliationResult]:
        started = perf_counter()
        log.info(
            "position_resolution_check_start",
            position_id=position_id,
            market_id=market_id,
            apply=apply,
        )
        async with self.sessionmaker() as session:
            statement = select(ModelPaperTradeRecord).where(ModelPaperTradeRecord.status == "open")
            if position_id:
                statement = statement.where(ModelPaperTradeRecord.id == position_id)
            if market_id:
                statement = statement.where(ModelPaperTradeRecord.market_id == market_id)
            records = list((await session.execute(statement)).scalars())
            results: list[PositionReconciliationResult] = []
            resolution_cache: dict[tuple[str, str], MarketResolution] = {}
            for record in records:
                trade = ModelPaperTrade.model_validate(record.payload)
                if data_mode is not None and trade.data_source != data_mode:
                    reason = (
                        f"position data_source {trade.data_source} is outside {data_mode} mode"
                    )
                    results.append(
                        _skipped_result(
                            record,
                            trade,
                            _local_skip_resolution(
                                Exchange(record.exchange),
                                record.market_id,
                                reason,
                            ),
                            reason,
                            apply,
                        )
                    )
                    continue
                key = (record.exchange, record.market_id)
                resolution = resolution_cache.get(key)
                if resolution is None:
                    resolution = await self.fetch_resolution(
                        Exchange(record.exchange),
                        record.market_id,
                    )
                    resolution_cache[key] = resolution
                result = self._result_for(record, trade, resolution, apply=apply)
                results.append(result)
                if apply and not result.skipped:
                    _apply_settlement(record, trade, result)
            if apply:
                await session.commit()
        log.info(
            "position_resolution_check_complete",
            exchange_markets_checked=len({(item.exchange, item.market_id) for item in results}),
            open_positions_checked=len(results),
            resolved_markets_found=sum(1 for item in results if item.resolved_outcome),
            positions_closed=sum(1 for item in results if item.applied and not item.skipped),
            positions_skipped=sum(1 for item in results if item.skipped),
            duration_seconds=perf_counter() - started,
        )
        return results

    async def fetch_resolution(self, exchange: Exchange, market_id: str) -> MarketResolution:
        if exchange == Exchange.KALSHI:
            return await self._fetch_kalshi_resolution(market_id)
        if exchange == Exchange.POLYMARKET:
            return await self._fetch_polymarket_resolution(market_id)
        now = datetime.now(UTC)
        return MarketResolution(
            exchange=exchange,
            market_id=market_id,
            state="unavailable",
            exchange_status=None,
            resolved_outcome=None,
            resolution_timestamp=None,
            settlement_value=None,
            last_resolution_check_timestamp=now,
            skip_reason="unsupported exchange",
            raw={},
        )

    async def _fetch_kalshi_resolution(self, market_id: str) -> MarketResolution:
        checked_at = datetime.now(UTC)
        try:
            payload = await self.http.get_json(
                f"{self.settings.kalshi_base_url}/markets/{market_id}"
            )
        except Exception as exc:
            return _unavailable(Exchange.KALSHI, market_id, checked_at, str(exc))
        market = payload.get("market") if isinstance(payload, dict) else None
        if not isinstance(market, dict):
            return _unavailable(Exchange.KALSHI, market_id, checked_at, "missing market object")
        status = _lower_string_or_none(market.get("status"))
        result = _lower_string_or_none(market.get("result"))
        settlement_ts = _parse_datetime(_string_or_none(market.get("settlement_ts")))
        if _is_voided_status(status, result):
            return MarketResolution(
                Exchange.KALSHI,
                market_id,
                "voided",
                status,
                None,
                settlement_ts or _parse_datetime(_string_or_none(market.get("updated_time"))),
                Decimal("1"),
                checked_at,
                None,
                market,
            )
        if status in {"finalized", "settled"} and result in {"yes", "no"}:
            return MarketResolution(
                Exchange.KALSHI,
                market_id,
                "resolved",
                status,
                Side.YES if result == "yes" else Side.NO,
                settlement_ts or _parse_datetime(_string_or_none(market.get("updated_time"))),
                Decimal("1"),
                checked_at,
                None,
                market,
            )
        return MarketResolution(
            Exchange.KALSHI,
            market_id,
            "pending",
            status,
            None,
            None,
            None,
            checked_at,
            f"market status {status or 'unknown'} is not finalized with yes/no result",
            market,
        )

    async def _fetch_polymarket_resolution(self, market_id: str) -> MarketResolution:
        checked_at = datetime.now(UTC)
        try:
            payload = await self.http.get_json(
                f"{self.settings.polymarket_gamma_base_url}/markets",
                params={"condition_ids": market_id, "limit": 1},
            )
        except Exception as exc:
            return _unavailable(Exchange.POLYMARKET, market_id, checked_at, str(exc))
        market = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(market, dict):
            return _unavailable(Exchange.POLYMARKET, market_id, checked_at, "missing market object")
        closed = bool(market.get("closed"))
        active = bool(market.get("active", True))
        status = _lower_string_or_none(market.get("status")) or ("closed" if closed else "active")
        if _is_voided_status(status, _lower_string_or_none(market.get("resolutionStatus"))):
            return MarketResolution(
                Exchange.POLYMARKET,
                market_id,
                "voided",
                status,
                None,
                _polymarket_resolution_timestamp(market),
                Decimal("1"),
                checked_at,
                None,
                market,
            )
        winner = _polymarket_winning_outcome(market)
        if closed and not active and winner is not None:
            return MarketResolution(
                Exchange.POLYMARKET,
                market_id,
                "resolved",
                status,
                winner,
                _polymarket_resolution_timestamp(market),
                Decimal("1"),
                checked_at,
                None,
                market,
            )
        return MarketResolution(
            Exchange.POLYMARKET,
            market_id,
            "pending",
            status,
            None,
            None,
            None,
            checked_at,
            "Polymarket market has no final winning YES/NO outcome field",
            market,
        )

    def _result_for(
        self,
        record: ModelPaperTradeRecord,
        trade: ModelPaperTrade,
        resolution: MarketResolution,
        *,
        apply: bool,
    ) -> PositionReconciliationResult:
        if record.status != "open" or trade.status != "open":
            return _skipped_result(record, trade, resolution, "position is not open", apply)
        if resolution.state == "pending":
            return _skipped_result(record, trade, resolution, resolution.skip_reason, apply)
        if resolution.state == "unavailable":
            return _skipped_result(record, trade, resolution, resolution.skip_reason, apply)

        quantity = trade.filled_quantity
        entry_cost = quantity * trade.entry_price
        if resolution.state == "voided":
            settlement_value = entry_cost
            realized = Decimal("0")
            exit_reason = MARKET_VOIDED
            resolved_outcome = None
        else:
            resolved_outcome = resolution.resolved_outcome
            winning_contract = resolved_outcome == trade.direction
            settlement_value = quantity if winning_contract else Decimal("0")
            realized = settlement_value - entry_cost
            exit_reason = MARKET_RESOLVED

        return PositionReconciliationResult(
            position_id=record.id,
            opportunity_id=record.opportunity_id,
            prediction_id=record.prediction_id,
            exchange=record.exchange,
            market_id=record.market_id,
            position_side=record.direction,
            entry_price=trade.entry_price,
            quantity=quantity,
            previous_status=record.status,
            proposed_status="closed",
            exchange_status=resolution.exchange_status,
            resolved_outcome=resolved_outcome.value if resolved_outcome else None,
            resolution_timestamp=resolution.resolution_timestamp,
            last_resolution_check_timestamp=resolution.last_resolution_check_timestamp,
            settlement_value=settlement_value,
            previous_realized_pnl=trade.realized_pnl,
            proposed_realized_pnl=realized,
            previous_mark_to_market_pnl=trade.mark_to_market_pnl,
            proposed_mark_to_market_pnl=Decimal("0"),
            previous_exit_reason=trade.exit_reason,
            proposed_exit_reason=exit_reason,
            applied=apply,
            skipped=False,
            skip_reason=None,
        )


def _apply_settlement(
    record: ModelPaperTradeRecord,
    trade: ModelPaperTrade,
    result: PositionReconciliationResult,
) -> None:
    record.status = result.proposed_status
    record.mark_to_market_pnl = result.proposed_mark_to_market_pnl
    record.realized_pnl = result.proposed_realized_pnl
    record.exit_reason = result.proposed_exit_reason
    record.resolved_outcome = result.resolved_outcome
    record.resolution_timestamp = result.resolution_timestamp
    record.last_resolution_check_timestamp = result.last_resolution_check_timestamp
    record.settlement_value = result.settlement_value
    trade.status = "closed"
    trade.mark_to_market_pnl = result.proposed_mark_to_market_pnl
    trade.realized_pnl = result.proposed_realized_pnl
    trade.exit_reason = result.proposed_exit_reason
    trade.resolved_outcome = Side(result.resolved_outcome) if result.resolved_outcome else None
    trade.resolution_timestamp = result.resolution_timestamp
    trade.last_resolution_check_timestamp = result.last_resolution_check_timestamp
    trade.settlement_value = result.settlement_value
    record.payload = trade.model_dump(mode="json")


def _skipped_result(
    record: ModelPaperTradeRecord,
    trade: ModelPaperTrade,
    resolution: MarketResolution,
    reason: str | None,
    apply: bool,
) -> PositionReconciliationResult:
    return PositionReconciliationResult(
        position_id=record.id,
        opportunity_id=record.opportunity_id,
        prediction_id=record.prediction_id,
        exchange=record.exchange,
        market_id=record.market_id,
        position_side=record.direction,
        entry_price=trade.entry_price,
        quantity=trade.filled_quantity,
        previous_status=record.status,
        proposed_status=record.status,
        exchange_status=resolution.exchange_status,
        resolved_outcome=resolution.resolved_outcome.value if resolution.resolved_outcome else None,
        resolution_timestamp=resolution.resolution_timestamp,
        last_resolution_check_timestamp=resolution.last_resolution_check_timestamp,
        settlement_value=resolution.settlement_value,
        previous_realized_pnl=trade.realized_pnl,
        proposed_realized_pnl=trade.realized_pnl,
        previous_mark_to_market_pnl=trade.mark_to_market_pnl,
        proposed_mark_to_market_pnl=trade.mark_to_market_pnl,
        previous_exit_reason=trade.exit_reason,
        proposed_exit_reason=trade.exit_reason,
        applied=False,
        skipped=True,
        skip_reason=reason or "position not eligible for settlement",
    )


def _unavailable(
    exchange: Exchange,
    market_id: str,
    checked_at: datetime,
    reason: str,
) -> MarketResolution:
    return MarketResolution(
        exchange,
        market_id,
        "unavailable",
        None,
        None,
        None,
        None,
        checked_at,
        reason,
        {},
    )


def _local_skip_resolution(
    exchange: Exchange,
    market_id: str,
    reason: str,
) -> MarketResolution:
    now = datetime.now(UTC)
    return MarketResolution(
        exchange,
        market_id,
        "pending",
        None,
        None,
        None,
        None,
        now,
        reason,
        {},
    )


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def _lower_string_or_none(value: object) -> str | None:
    text = _string_or_none(value)
    return text.lower() if text else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_voided_status(status: str | None, result: str | None) -> bool:
    values = {status, result}
    return bool(values & {"void", "voided", "cancelled", "canceled", "refunded"})


def _polymarket_winning_outcome(market: dict[str, Any]) -> Side | None:
    for key in ("outcome", "winningOutcome", "winner", "winning_outcome"):
        value = _lower_string_or_none(market.get(key))
        if value == "yes":
            return Side.YES
        if value == "no":
            return Side.NO
    tokens = market.get("tokens")
    if isinstance(tokens, list):
        for token in tokens:
            if not isinstance(token, dict):
                continue
            outcome = _lower_string_or_none(token.get("outcome"))
            winner = token.get("winner") or token.get("winning")
            if winner is True and outcome == "yes":
                return Side.YES
            if winner is True and outcome == "no":
                return Side.NO
    return None


def _polymarket_resolution_timestamp(market: dict[str, Any]) -> datetime | None:
    for key in ("resolutionTime", "resolvedTime", "closedTime", "updatedAt", "resolutionDate"):
        parsed = _parse_datetime(_string_or_none(market.get(key)))
        if parsed:
            return parsed
    return None
