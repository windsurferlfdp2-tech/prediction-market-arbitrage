import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.models.domain import Exchange, Market, OrderBook, PriceLevel, RealtimeBookStatus, Side
from app.persistence.database import OrderBookSnapshotRecord

Transport = Literal["websocket", "rest_fallback", "test"]


@dataclass
class BookState:
    book: OrderBook
    transport: Transport
    last_sequence: int | None = None
    stale: bool = False
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SequenceGapError(ValueError):
    pass


class RealtimeOrderBookService:
    def __init__(self, settings: Settings, adapters: list[ExchangeAdapter]) -> None:
        self.settings = settings
        self.adapters = adapters
        self._states: dict[tuple[Exchange, str, Side], BookState] = {}
        self._started = False

    async def refresh_rest_snapshot(self, markets: list[Market]) -> list[OrderBook]:
        books: list[OrderBook] = []
        for adapter in self.adapters:
            adapter_markets = [
                market for market in markets if market.exchange.value == adapter.name
            ]
            adapter_books = await adapter.fetch_order_books(adapter_markets)
            for book in adapter_books:
                self.apply_snapshot(book, transport="rest_fallback")
            books.extend(adapter_books)
        return self.books()

    def apply_snapshot(
        self,
        book: OrderBook,
        *,
        sequence: int | None = None,
        transport: Transport = "websocket",
    ) -> None:
        self._states[_book_key(book)] = BookState(
            book=book,
            transport=transport,
            last_sequence=sequence,
            stale=False,
            updated_at=datetime.now(UTC),
        )

    def apply_delta(
        self,
        exchange: Exchange,
        market_id: str,
        side: Side,
        asks: list[PriceLevel] | None = None,
        bids: list[PriceLevel] | None = None,
        sequence: int | None = None,
        expected_previous_sequence: int | None = None,
        observed_at: datetime | None = None,
        raw: dict[str, Any] | None = None,
    ) -> OrderBook:
        key = (exchange, market_id, side)
        state = self._states.get(key)
        if state is None:
            raise KeyError(f"missing snapshot for {exchange}:{market_id}:{side}")
        if (
            expected_previous_sequence is not None
            and state.last_sequence is not None
            and expected_previous_sequence != state.last_sequence
        ):
            raise SequenceGapError(
                f"sequence gap for {exchange}:{market_id}:{side}: "
                f"expected {expected_previous_sequence}, have {state.last_sequence}"
            )

        current = state.book
        next_book = current.model_copy(
            update={
                "asks": _merge_levels(current.asks, asks),
                "bids": _merge_levels(current.bids, bids),
                "fetched_at": observed_at or datetime.now(UTC),
                "raw": raw or current.raw,
            }
        )
        state.book = next_book
        state.last_sequence = sequence if sequence is not None else state.last_sequence
        state.updated_at = datetime.now(UTC)
        state.stale = False
        return next_book

    def mark_stale(self, now: datetime | None = None) -> None:
        reference = now or datetime.now(UTC)
        for state in self._states.values():
            state.stale = state.book.is_stale(self.settings.orderbook_max_age_seconds, reference)

    def books(self, now: datetime | None = None) -> list[OrderBook]:
        self.mark_stale(now)
        return [state.book for state in self._states.values() if not state.stale]

    def statuses(self, now: datetime | None = None) -> list[RealtimeBookStatus]:
        self.mark_stale(now)
        reference = now or datetime.now(UTC)
        return [
            RealtimeBookStatus(
                exchange=state.book.exchange,
                market_id=state.book.market_id,
                side=state.book.side,
                transport=state.transport,
                last_sequence=state.last_sequence,
                stale=state.stale,
                age_seconds=state.book.age_seconds(reference),
                updated_at=state.updated_at,
            )
            for state in self._states.values()
        ]

    async def reconnect_with_backoff(
        self,
        refresh: Callable[[], Awaitable[None]],
        *,
        attempts: int = 3,
    ) -> None:
        delay = Decimal(str(self.settings.realtime_reconnect_initial_seconds))
        max_delay = Decimal(str(self.settings.realtime_reconnect_max_seconds))
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                await refresh()
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await asyncio.sleep(float(delay))
                delay = min(delay * Decimal("2"), max_delay)
        if last_error is not None:
            raise last_error


class PolymarketPublicWebSocketIngestor:
    def __init__(self, settings: Settings, order_books: RealtimeOrderBookService) -> None:
        self.settings = settings
        self.order_books = order_books

    async def run(self, markets: list[Market]) -> None:
        # The long-running network loop is deliberately not started in local tests.
        # REST snapshots remain the default fallback transport.
        await self.order_books.refresh_rest_snapshot(markets)


class KalshiWebSocketIngestor:
    def __init__(self, settings: Settings, order_books: RealtimeOrderBookService) -> None:
        self.settings = settings
        self.order_books = order_books

    @property
    def credentials_available(self) -> bool:
        return bool(self.settings.kalshi_api_key_id and self.settings.kalshi_private_key_path)

    async def run(self, markets: list[Market]) -> None:
        if not self.credentials_available:
            await self.order_books.refresh_rest_snapshot(markets)
            return
        await self.order_books.refresh_rest_snapshot(markets)


class OrderBookSnapshotRecorder:
    def __init__(self, sessionmaker: async_sessionmaker[Any], settings: Settings) -> None:
        self.sessionmaker = sessionmaker
        self.settings = settings

    async def record(self, books: list[OrderBook], transport: Transport = "rest_fallback") -> None:
        now = datetime.now(UTC)
        async with self.sessionmaker() as session:
            for book in books:
                session.add(
                    OrderBookSnapshotRecord(
                        exchange=book.exchange.value,
                        market_id=book.market_id,
                        outcome_id=book.outcome_id,
                        side=book.side.value,
                        observed_at=now,
                        exchange_timestamp=book.exchange_timestamp,
                        age_seconds=book.age_seconds(now),
                        stale=book.is_stale(self.settings.orderbook_max_age_seconds, now),
                        sequence=_sequence(book),
                        transport=transport,
                        asks=[_level_payload(level) for level in book.asks],
                        bids=[_level_payload(level) for level in book.bids],
                        raw=book.raw,
                    )
                )
            await session.commit()


def _book_key(book: OrderBook) -> tuple[Exchange, str, Side]:
    return (book.exchange, book.market_id, book.side)


def _merge_levels(
    current: list[PriceLevel],
    updates: list[PriceLevel] | None,
) -> list[PriceLevel]:
    if updates is None:
        return current
    levels = {level.price: level.model_copy() for level in current}
    for update in updates:
        if update.quantity <= 0:
            levels.pop(update.price, None)
        else:
            levels[update.price] = update.model_copy()
    return sorted(levels.values(), key=lambda level: level.price)


def _sequence(book: OrderBook) -> int | None:
    value = book.raw.get("sequence")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _level_payload(level: PriceLevel) -> dict[str, str]:
    return {
        "price": str(level.price),
        "quantity": str(level.quantity),
        "source_side": level.source_side,
    }
