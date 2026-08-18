from datetime import UTC, datetime
from decimal import Decimal

from pytest import MonkeyPatch
from sqlalchemy import text

from app.config import Settings
from app.persistence.database import (
    ModelOpportunityRecord,
    SqlAlchemyDatabaseBackend,
    create_database_backend,
)
from app.services.cache import InMemoryCache, RedisCache, create_cache_backend


def test_local_development_uses_sqlite_and_memory_cache(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app_settings = Settings(local_development=True)

    cache = create_cache_backend(app_settings)
    database = create_database_backend(app_settings)

    assert app_settings.effective_database_url == "sqlite+aiosqlite:///./prediction_market_arb.db"
    assert app_settings.cache_backend == "memory"
    assert isinstance(cache, InMemoryCache)
    assert isinstance(database, SqlAlchemyDatabaseBackend)
    assert str(database.engine.url).startswith("sqlite+aiosqlite:///")


def test_database_url_overrides_local_development_default() -> None:
    app_settings = Settings(
        local_development=True,
        database_url="sqlite+aiosqlite:///:memory:",
    )

    assert app_settings.effective_database_url == "sqlite+aiosqlite:///:memory:"


def test_non_local_development_preserves_postgres_and_redis() -> None:
    app_settings = Settings(
        local_development=False,
        database_url="postgresql+asyncpg://arb:arb@postgres:5432/arb",
        redis_url="redis://redis:6379/0",
    )

    cache = create_cache_backend(app_settings)
    database = create_database_backend(app_settings)

    assert app_settings.effective_database_url == "postgresql+asyncpg://arb:arb@postgres:5432/arb"
    assert app_settings.cache_backend == "redis"
    assert isinstance(cache, RedisCache)
    assert isinstance(database, SqlAlchemyDatabaseBackend)
    assert str(database.engine.url).startswith("postgresql+asyncpg://")


async def test_sqlite_preserves_decimal_precision_and_utc_timestamps() -> None:
    backend = SqlAlchemyDatabaseBackend("sqlite+aiosqlite:///:memory:")
    await backend.init()
    timestamp = datetime(2026, 7, 21, 23, 30, tzinfo=UTC)

    async with backend.sessionmaker() as session:
        session.add(
            ModelOpportunityRecord(
                id="precision-test",
                prediction_id="prediction",
                model_id="model",
                market_id="market",
                exchange="polymarket",
                category="general",
                direction="yes",
                detected_at=timestamp,
                net_expected_value=Decimal("1.123456789123456789"),
                expected_roi=Decimal("0.012345678912345678"),
                executable_quantity=Decimal("3.000000000000000001"),
                label="MODEL OPPORTUNITY",
                payload={},
            )
        )
        await session.commit()
        raw = (
            await session.execute(
                text(
                    "select net_expected_value, typeof(net_expected_value), "
                    "detected_at, typeof(detected_at) "
                    "from model_opportunities where id='precision-test'"
                )
            )
        ).one()
        record = await session.get(ModelOpportunityRecord, "precision-test")

    assert raw[0] == "1.123456789123456789"
    assert raw[1] == "text"
    assert raw[3] == "text"
    assert record is not None
    assert record.net_expected_value == Decimal("1.123456789123456789")
    assert record.detected_at == timestamp
    assert record.detected_at.tzinfo is not None
