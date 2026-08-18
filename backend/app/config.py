from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_POSTGRES_DATABASE_URL = "postgresql+asyncpg://arb:arb@localhost:5432/arb"
LOCAL_SQLITE_DATABASE_URL = "sqlite+aiosqlite:///./prediction_market_arb.db"
DataMode = Literal["live", "test"]
SwitchableDataMode = Literal["live", "test"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    local_development: bool = False
    log_level: str = "INFO"
    backend_cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost:3001,"
        "http://127.0.0.1:3001"
    )
    data_mode: DataMode = "live"
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    polymarket_gamma_base_url: str = "https://gamma-api.polymarket.com"
    polymarket_base_url: str = "https://clob.polymarket.com"
    kalshi_base_url: str = "https://external-api.kalshi.com/trade-api/v2"
    request_timeout_seconds: float = 10
    request_retries: int = 3
    request_backoff_seconds: float = 0.25
    orderbook_max_age_seconds: int = 30
    realtime_orderbook_enabled: bool = False
    realtime_reconnect_initial_seconds: float = 0.25
    realtime_reconnect_max_seconds: float = 5
    polymarket_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    kalshi_ws_url: str = "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
    kalshi_api_key_id: str | None = None
    kalshi_private_key_path: str | None = None
    live_scan_market_limit: int = 25
    min_net_profit: Decimal = Field(default=Decimal("0.01"))
    min_roi: Decimal = Field(default=Decimal("0.001"))
    fee_rate: Decimal = Field(default=Decimal("0"))
    slippage_rate: Decimal = Field(default=Decimal("0"))
    paper_trading_enabled: bool = True
    paper_latency_ms: int = 250
    paper_max_position: Decimal = Field(default=Decimal("100"))
    model_prediction_enabled: bool = True
    model_registry_dir: str = "./model_artifacts"
    model_training_seed: int = 42
    model_min_general_snapshots: int = 12
    model_min_category_snapshots: int = 20
    model_min_confidence: Decimal = Field(default=Decimal("0.55"))
    model_max_uncertainty: Decimal = Field(default=Decimal("0.45"))
    model_min_expected_edge: Decimal = Field(default=Decimal("0.05"))
    model_min_expected_roi: Decimal = Field(default=Decimal("0.03"))
    model_max_spread: Decimal = Field(default=Decimal("0.20"))
    model_bankroll: Decimal = Field(default=Decimal("10000"))
    model_kelly_fraction: Decimal = Field(default=Decimal("0.025"))
    model_max_bankroll_pct_per_trade: Decimal = Field(default=Decimal("0.0025"))
    model_high_confidence_bankroll_pct: Decimal = Field(default=Decimal("0.005"))
    model_max_event_exposure_pct: Decimal = Field(default=Decimal("0.01"))
    model_max_category_exposure_pct: Decimal = Field(default=Decimal("0.03"))
    model_daily_loss_limit_pct: Decimal = Field(default=Decimal("0.02"))
    model_max_open_positions: int = 25
    model_live_market_limit: int = 5
    model_position_reconciliation_enabled: bool = True
    model_position_reconciliation_interval_seconds: float = 60
    model_paper_trading_enabled: bool = False
    model_paper_trading_freeze_reason: str = (
        "Emergency Phase 3 audit: model paper trading paused after poor observed performance"
    )
    model_paper_trading_freeze_enabled_at: str = "2026-08-03T00:00:00Z"
    model_min_approval_training_markets: int = 100
    model_min_approval_validation_markets: int = 30
    model_min_approval_validation_rows: int = 100
    model_min_approval_final_test_markets: int = 30
    model_min_approval_final_test_rows: int = 100
    model_max_approval_calibration_error: Decimal = Field(default=Decimal("0.05"))
    model_required_brier_improvement: Decimal = Field(default=Decimal("0.01"))
    model_required_log_loss_improvement: Decimal = Field(default=Decimal("0.01"))
    model_max_approval_paper_drawdown: Decimal = Field(default=Decimal("0.05"))
    model_min_approval_paper_trade_sample: int = 100
    model_max_trades_per_day: int = 3
    use_fixtures: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.local_development:
            return LOCAL_SQLITE_DATABASE_URL
        return DEFAULT_POSTGRES_DATABASE_URL

    @property
    def cache_backend(self) -> str:
        return "memory" if self.local_development else "redis"

    @property
    def effective_data_mode(self) -> DataMode:
        if self.data_mode == "test":
            return "test"
        return "live"

    @model_validator(mode="after")
    def validate_live_data_safety(self) -> "Settings":
        if self.app_env == "production" and self.data_mode != "live":
            raise ValueError("production requires DATA_MODE=live")
        if self.app_env == "production" and self.use_fixtures:
            raise ValueError("production cannot enable USE_FIXTURES")
        if self.use_fixtures and self.data_mode != "test":
            raise ValueError("USE_FIXTURES is only allowed when DATA_MODE=test")
        return self


settings = Settings()
