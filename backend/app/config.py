from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    backend_cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+asyncpg://arb:arb@localhost:5432/arb"
    redis_url: str = "redis://localhost:6379/0"
    polymarket_base_url: str = "https://clob.polymarket.com"
    kalshi_base_url: str = "https://external-api.kalshi.com/trade-api/v2"
    request_timeout_seconds: float = 10
    request_retries: int = 3
    request_backoff_seconds: float = 0.25
    orderbook_max_age_seconds: int = 30
    min_net_profit: Decimal = Field(default=Decimal("0.01"))
    min_roi: Decimal = Field(default=Decimal("0.001"))
    fee_rate: Decimal = Field(default=Decimal("0"))
    slippage_rate: Decimal = Field(default=Decimal("0"))
    use_fixtures: bool = True

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


settings = Settings()
