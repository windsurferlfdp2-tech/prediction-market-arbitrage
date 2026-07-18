from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, JSON, Numeric, String
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


class MarketSnapshotRecord(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(32), index=True)
    exchange_market_id: Mapped[str] = mapped_column(String(256), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    raw: Mapped[dict[str, Any]] = mapped_column(JSON)


class OpportunityRecord(Base):
    __tablename__ = "opportunities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    same_market_key: Mapped[str] = mapped_column(String(256), index=True)
    net_profit: Mapped[Decimal] = mapped_column(Numeric)
    roi: Mapped[Decimal] = mapped_column(Numeric)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
