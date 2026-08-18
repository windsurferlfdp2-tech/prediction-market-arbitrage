from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import JSON, Boolean, DateTime, Integer, Numeric, String, Text, text
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from app.config import Settings, settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


class DecimalValue(TypeDecorator[Decimal]):
    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(80))
        return dialect.type_descriptor(Numeric(38, 18))

    def process_bind_param(
        self,
        value: Decimal | int | float | str | None,
        dialect: Any,
    ) -> str | Decimal | None:
        if value is None:
            return None
        decimal_value = Decimal(str(value))
        if dialect.name == "sqlite":
            return format(decimal_value, "f")
        return decimal_value

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))


class UtcDateTimeValue(TypeDecorator[datetime]):
    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(40))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(
        self,
        value: datetime | None,
        dialect: Any,
    ) -> str | datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        value = value.astimezone(UTC)
        if dialect.name == "sqlite":
            return value.isoformat().replace("+00:00", "Z")
        return value

    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


DECIMAL_VALUE = DecimalValue()
UTC_DATETIME = UtcDateTimeValue()


class MarketSnapshotRecord(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    exchange_market_id: Mapped[str] = mapped_column(String(256), index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        UTC_DATETIME, default=lambda: datetime.now(UTC)
    )
    raw: Mapped[dict[str, Any]] = mapped_column(JSON)


class OpportunityRecord(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    same_market_key: Mapped[str] = mapped_column(String(256), index=True)
    net_profit: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    roi: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    detected_at: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class OpportunityHistoryRecord(Base):
    __tablename__ = "opportunity_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), index=True)
    data_mode: Mapped[str] = mapped_column(String(32), index=True)
    same_market_key: Mapped[str] = mapped_column(String(256), index=True)
    yes_exchange: Mapped[str] = mapped_column(String(32))
    no_exchange: Mapped[str] = mapped_column(String(32))
    yes_market_id: Mapped[str] = mapped_column(String(256), index=True)
    no_market_id: Mapped[str] = mapped_column(String(256), index=True)
    market_title: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    disappeared_at: Mapped[datetime | None] = mapped_column(UTC_DATETIME, nullable=True)
    duration_seconds: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    disappearance_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    yes_price: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    yes_available_size: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    no_price: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    no_available_size: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    combined_cost: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    estimated_fees: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    estimated_slippage: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    net_edge: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    net_roi: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    maximum_executable_quantity: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    order_book_age_seconds: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class SchemaMigrationRecord(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[str] = mapped_column(String(128), primary_key=True)


class MarketPairReviewRecord(Base):
    __tablename__ = "market_pair_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    polymarket_market_id: Mapped[str] = mapped_column(String(256), index=True)
    kalshi_market_id: Mapped[str] = mapped_column(String(256), index=True)
    polymarket_title: Mapped[str] = mapped_column(Text)
    kalshi_title: Mapped[str] = mapped_column(Text)
    polymarket_resolution_criteria: Mapped[str] = mapped_column(Text)
    kalshi_resolution_criteria: Mapped[str] = mapped_column(Text)
    polymarket_close_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kalshi_close_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    polymarket_settlement_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kalshi_settlement_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    polymarket_resolution_sources: Mapped[list[str]] = mapped_column(JSON)
    kalshi_resolution_sources: Mapped[list[str]] = mapped_column(JSON)
    polymarket_entities: Mapped[list[str]] = mapped_column(JSON)
    kalshi_entities: Mapped[list[str]] = mapped_column(JSON)
    polymarket_numbers: Mapped[list[str]] = mapped_column(JSON)
    kalshi_numbers: Mapped[list[str]] = mapped_column(JSON)
    similarity_score: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    mismatches: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(UTC_DATETIME)
    updated_at: Mapped[datetime] = mapped_column(UTC_DATETIME)


class OrderBookSnapshotRecord(Base):
    __tablename__ = "order_book_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    market_id: Mapped[str] = mapped_column(String(256), index=True)
    outcome_id: Mapped[str] = mapped_column(String(256))
    side: Mapped[str] = mapped_column(String(16), index=True)
    observed_at: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    exchange_timestamp: Mapped[datetime | None] = mapped_column(
        UTC_DATETIME,
        nullable=True,
    )
    age_seconds: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    stale: Mapped[bool] = mapped_column(Boolean, index=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transport: Mapped[str] = mapped_column(String(32))
    asks: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    bids: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON)


class PaperTradeSimulationRecord(Base):
    __tablename__ = "paper_trade_simulations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), index=True)
    same_market_key: Mapped[str] = mapped_column(String(256), index=True)
    created_at: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    direction: Mapped[str] = mapped_column(String(64), index=True)
    yes_exchange: Mapped[str] = mapped_column(String(32))
    no_exchange: Mapped[str] = mapped_column(String(32))
    yes_market_id: Mapped[str] = mapped_column(String(256), index=True)
    no_market_id: Mapped[str] = mapped_column(String(256), index=True)
    requested_quantity: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    filled_quantity: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    projected_gross_profit: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    projected_net_profit: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    latency_ms: Mapped[int] = mapped_column(Integer)
    partial_fill: Mapped[bool] = mapped_column(Boolean, index=True)
    hedge_failure: Mapped[bool] = mapped_column(Boolean, index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    fills: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class HistoricalTrainingSnapshotRecord(Base):
    __tablename__ = "historical_training_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    market_id: Mapped[str] = mapped_column(String(256), index=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    prediction_timestamp: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    market_close_timestamp: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    feature_timestamp: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    resolution_outcome: Mapped[int] = mapped_column(Integer)
    feature_schema_version: Mapped[str] = mapped_column(String(64))
    features: Mapped[dict[str, Any]] = mapped_column(JSON)
    missing_indicators: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class PredictionModelRecord(Base):
    __tablename__ = "prediction_models"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    model_type: Mapped[str] = mapped_column(String(64))
    training_timestamp: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    training_start: Mapped[datetime] = mapped_column(UTC_DATETIME)
    training_end: Mapped[datetime] = mapped_column(UTC_DATETIME)
    feature_schema_version: Mapped[str] = mapped_column(String(64))
    training_sample_count: Mapped[int] = mapped_column(Integer)
    validation_metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    calibration_method: Mapped[str] = mapped_column(String(64))
    calibration_metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    artifact_path: Mapped[str] = mapped_column(Text)
    source_identifier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    training_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    artifact_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_market_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validation_sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_score: Mapped[Decimal | None] = mapped_column(DECIMAL_VALUE, nullable=True)
    model_score: Mapped[Decimal | None] = mapped_column(DECIMAL_VALUE, nullable=True)
    metadata_payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ModelPredictionRecord(Base):
    __tablename__ = "model_predictions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    market_id: Mapped[str] = mapped_column(String(256), index=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    prediction_timestamp: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    fair_probability: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    market_probability: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    confidence_score: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    uncertainty_score: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    no_trade_reasons: Mapped[list[str]] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ModelOpportunityRecord(Base):
    __tablename__ = "model_opportunities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    prediction_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    market_id: Mapped[str] = mapped_column(String(256), index=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    detected_at: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    net_expected_value: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    expected_roi: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    executable_quantity: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    label: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ModelPaperTradeRecord(Base):
    __tablename__ = "model_paper_trades"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), index=True)
    prediction_id: Mapped[str] = mapped_column(String(64), index=True)
    model_id: Mapped[str] = mapped_column(String(64), index=True)
    market_id: Mapped[str] = mapped_column(String(256), index=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(UTC_DATETIME, index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(64))
    requested_quantity: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    filled_quantity: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    entry_price: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    position_size: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    expected_edge: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    mark_to_market_pnl: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    realized_pnl: Mapped[Decimal] = mapped_column(DECIMAL_VALUE)
    exit_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolved_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolution_timestamp: Mapped[datetime | None] = mapped_column(UTC_DATETIME, nullable=True)
    last_resolution_check_timestamp: Mapped[datetime | None] = mapped_column(
        UTC_DATETIME,
        nullable=True,
    )
    settlement_value: Mapped[Decimal | None] = mapped_column(DECIMAL_VALUE, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DatabaseBackend(Protocol):
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[Any]

    async def init(self) -> None: ...


class SqlAlchemyDatabaseBackend:
    def __init__(self, database_url: str) -> None:
        engine_kwargs: dict[str, Any] = {"pool_pre_ping": not database_url.startswith("sqlite")}
        if database_url == "sqlite+aiosqlite:///:memory:":
            engine_kwargs["poolclass"] = StaticPool
        self.engine = create_async_engine(
            database_url,
            **engine_kwargs,
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_ensure_prediction_model_columns)
            await conn.run_sync(_ensure_model_paper_trade_columns)
        async with self.sessionmaker() as session:
            for migration in sorted(_migration_versions()):
                existing = await session.get(SchemaMigrationRecord, migration)
                if existing is None:
                    session.add(SchemaMigrationRecord(version=migration))
            await session.commit()


def create_database_backend(app_settings: Settings) -> DatabaseBackend:
    return SqlAlchemyDatabaseBackend(app_settings.effective_database_url)


database_backend = create_database_backend(settings)
engine = database_backend.engine
AsyncSessionLocal = database_backend.sessionmaker


async def init_db() -> None:
    await database_backend.init()


def _migration_versions() -> list[str]:
    migration_root = Path(__file__).resolve().parents[2] / "migrations"
    if not migration_root.exists():
        return []
    return [path.stem for path in migration_root.glob("*.sql")]


def _ensure_prediction_model_columns(sync_conn: Any) -> None:
    if sync_conn.dialect.name != "sqlite":
        return
    existing = {
        row[1]
        for row in sync_conn.exec_driver_sql("PRAGMA table_info(prediction_models)").fetchall()
    }
    columns = {
        "training_fingerprint": "VARCHAR(128)",
        "artifact_hash": "VARCHAR(128)",
        "dataset_version": "VARCHAR(128)",
        "resolved_market_count": "INTEGER",
        "validation_sample_count": "INTEGER",
        "baseline_score": "VARCHAR(80)",
        "model_score": "VARCHAR(80)",
    }
    for column, column_type in columns.items():
        if column not in existing:
            sync_conn.execute(
                text(f"ALTER TABLE prediction_models ADD COLUMN {column} {column_type}")
            )
    sync_conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_prediction_models_training_fingerprint "
            "ON prediction_models (training_fingerprint)"
        )
    )


def _ensure_model_paper_trade_columns(sync_conn: Any) -> None:
    if sync_conn.dialect.name != "sqlite":
        return
    existing = {
        row[1]
        for row in sync_conn.exec_driver_sql("PRAGMA table_info(model_paper_trades)").fetchall()
    }
    columns = {
        "resolved_outcome": "VARCHAR(16)",
        "resolution_timestamp": "TIMESTAMP",
        "last_resolution_check_timestamp": "TIMESTAMP",
        "settlement_value": "VARCHAR(80)",
    }
    for column, column_type in columns.items():
        if column not in existing:
            sync_conn.execute(
                text(f"ALTER TABLE model_paper_trades ADD COLUMN {column} {column_type}")
            )
