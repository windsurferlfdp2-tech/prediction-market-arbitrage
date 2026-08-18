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
    data_source: Literal["live", "test"] = "live"
    is_live_data: bool = True
    source_timestamp: datetime | None = None
    processed_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    freshness_status: Literal["LIVE", "STALE", "TEST"] = "LIVE"
    paper_execution_eligible: bool = False
    paper_execution_status: str = "NOT ELIGIBLE FOR PAPER EXECUTION"
    paper_execution_reason: str | None = None


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
    data_source: Literal["live", "test"] = "live"
    is_live_data: bool = True

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
    data_source: Literal["live", "test"] = "live"
    is_live_data: bool = True
    source_timestamp: datetime | None = None
    processed_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    freshness_status: Literal["LIVE", "STALE", "TEST"] = "LIVE"

    @computed_field
    def read_only_label(self) -> str:
        return "Estimate only. Read-only scanner; no trading is performed."


class ExchangeHealth(BaseModel):
    exchange: Exchange
    ok: bool
    message: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latency_ms: Decimal | None = None


class PaperLegFill(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})

    exchange: Exchange
    market_id: str
    side: Side
    requested_quantity: Decimal
    filled_quantity: Decimal
    average_price: Decimal
    status: Literal["filled", "partial", "failed"]


class PaperTradeSimulation(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})

    id: str
    opportunity_id: str
    same_market_key: str
    label: str = "LIVE-DATA PAPER TRADE"
    data_source: Literal["live", "test"] = "live"
    is_live_data: bool = True
    execution_mode: Literal["paper"] = "paper"
    uses_live_market_data: bool = True
    created_at: datetime
    latency_ms: int
    requested_quantity: Decimal
    filled_quantity: Decimal
    projected_net_profit: Decimal
    realized_pnl: Decimal
    status: Literal["complete", "partial_fill", "hedge_failed", "disappeared", "skipped"]
    partial_fill: bool
    hedge_failure: bool
    fills: list[PaperLegFill]


class RealtimeBookStatus(BaseModel):
    exchange: Exchange
    market_id: str
    side: Side
    transport: Literal["websocket", "rest_fallback", "test"]
    last_sequence: int | None = None
    stale: bool
    age_seconds: Decimal
    updated_at: datetime


class MarketCategory(StrEnum):
    POLITICS = "politics"
    ECONOMICS = "economics"
    CRYPTO = "crypto"
    SPORTS = "sports"
    TECHNOLOGY = "technology"
    GENERAL = "general"


class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED_FOR_PAPER = "approved_for_paper"
    REJECTED = "rejected"
    RETIRED = "retired"


class PredictionModelSummary(BaseModel):
    id: str
    name: str
    category: MarketCategory
    version: str
    status: ModelStatus
    model_type: str
    training_timestamp: datetime
    training_sample_count: int
    validation_metrics: dict[str, Any]
    calibration_method: str
    calibration_metrics: dict[str, Any]
    artifact_path: str
    feature_schema_version: str
    training_fingerprint: str | None = None
    artifact_hash: str | None = None
    dataset_version: str | None = None
    training_start: datetime | None = None
    training_end: datetime | None = None
    resolved_market_count: int | None = None
    validation_sample_count: int | None = None
    baseline_score: Decimal | None = None
    model_score: Decimal | None = None


class ModelTrainingRequest(BaseModel):
    category: MarketCategory = MarketCategory.GENERAL
    data_mode: Literal["test", "live"] = "live"
    model_type: Literal["ensemble", "logistic", "gradient_boosted", "market_baseline"] = "ensemble"
    seed: int | None = None


class PredictionResult(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})

    id: str
    model_id: str
    market_id: str
    exchange: Exchange
    category: MarketCategory
    market_title: str
    fair_probability: Decimal
    raw_model_probability: Decimal
    calibrated_probability: Decimal
    market_probability: Decimal
    cross_platform_probability: Decimal | None = None
    confidence_score: Decimal
    uncertainty_score: Decimal
    model_version: str
    calibration_version: str
    feature_timestamp: datetime
    prediction_timestamp: datetime
    important_features: list[str]
    no_trade_reasons: list[str]
    label: str = "MODEL PREDICTION"
    data_source: Literal["live", "test"] = "live"
    is_live_data: bool = True
    source_timestamp: datetime | None = None
    processed_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    freshness_status: Literal["LIVE", "STALE", "TEST"] = "LIVE"


class ModelOpportunity(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})

    id: str
    prediction_id: str
    model_id: str
    market_id: str
    exchange: Exchange
    category: MarketCategory
    market_title: str
    direction: Side
    executable_quantity: Decimal
    weighted_average_entry_price: Decimal
    gross_expected_value: Decimal
    fees: Decimal
    expected_slippage: Decimal
    uncertainty_buffer: Decimal
    net_expected_value: Decimal
    expected_roi: Decimal
    confidence_score: Decimal
    uncertainty_score: Decimal
    book_freshness_seconds: Decimal
    detected_at: datetime
    no_trade_reasons: list[str]
    model_version: str = ""
    calibration_version: str = ""
    label: str = "MODEL OPPORTUNITY"
    data_source: Literal["live", "test"] = "live"
    is_live_data: bool = True
    source_timestamp: datetime | None = None
    processed_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    freshness_status: Literal["LIVE", "STALE", "TEST"] = "LIVE"


class ModelPaperTrade(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})

    id: str
    opportunity_id: str
    prediction_id: str
    model_id: str
    market_id: str
    exchange: Exchange
    category: MarketCategory
    direction: Side
    label: str = "LIVE-DATA MODEL PAPER TRADE"
    data_source: Literal["live", "test"] = "live"
    is_live_data: bool = True
    execution_mode: Literal["paper"] = "paper"
    uses_live_market_data: bool = True
    created_at: datetime
    status: Literal["open", "closed", "partial_fill", "cancelled"]
    requested_quantity: Decimal
    filled_quantity: Decimal
    entry_price: Decimal
    position_size: Decimal
    expected_edge: Decimal
    mark_to_market_pnl: Decimal
    realized_pnl: Decimal
    exit_reason: str | None = None
    resolved_outcome: Side | None = None
    resolution_timestamp: datetime | None = None
    last_resolution_check_timestamp: datetime | None = None
    settlement_value: Decimal | None = None
    model_version: str
    calibration_version: str
