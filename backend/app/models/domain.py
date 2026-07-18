from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


class Exchange(StrEnum):
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"


class Side(StrEnum):
    YES = "yes"
    NO = "no"


class PriceLevel(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})

    price: Decimal
    quantity: Decimal
    source_side: Literal["ask", "bid", "bid_derived_ask"]
    raw: dict[str, Any] = Field(default_factory=dict)


class Outcome(BaseModel):
    id: str
    name: str
    side: Side


class Market(BaseModel):
    exchange: Exchange
    exchange_market_id: str
    title: str
    status: str
    outcomes: list[Outcome]
    same_market_key: str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw: dict[str, Any] = Field(default_factory=dict)


class OrderBook(BaseModel):
    exchange: Exchange
    market_id: str
    outcome_id: str
    side: Side
    asks: list[PriceLevel]
    bids: list[PriceLevel] = Field(default_factory=list)
    fetched_at: datetime
    exchange_timestamp: datetime | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def age_seconds(self, now: datetime | None = None) -> Decimal:
        reference = now or datetime.now(UTC)
        return Decimal(str((reference - self.fetched_at).total_seconds()))

    def is_stale(self, max_age_seconds: int, now: datetime | None = None) -> bool:
        return self.age_seconds(now) > Decimal(max_age_seconds)


class UsedLevel(BaseModel):
    exchange: Exchange
    market_id: str
    outcome_id: str
    side: Side
    price: Decimal
    quantity: Decimal
    source_side: str


class ArbitrageOpportunity(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})

    id: str
    same_market_key: str
    title: str
    yes_exchange: Exchange
    no_exchange: Exchange
    yes_market_id: str
    no_market_id: str
    yes_avg_price: Decimal
    no_avg_price: Decimal
    gross_cost: Decimal
    gross_profit: Decimal
    total_fees: Decimal
    slippage_cost: Decimal
    net_profit: Decimal
    roi: Decimal
    max_quantity: Decimal
    detected_at: datetime
    freshness_seconds: Decimal
    confidence: Literal["high", "medium", "low"]
    used_levels: list[UsedLevel]

    @computed_field
    @property
    def read_only_label(self) -> str:
        return "Estimate only. Read-only scanner; no trading is performed."


class ExchangeHealth(BaseModel):
    exchange: Exchange
    ok: bool
    message: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latency_ms: Decimal | None = None
