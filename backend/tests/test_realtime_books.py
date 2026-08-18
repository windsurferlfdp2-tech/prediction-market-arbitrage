from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import Settings
from app.models.domain import Exchange, OrderBook, PriceLevel, Side
from app.services.realtime_books import RealtimeOrderBookService, SequenceGapError


def test_snapshot_delta_and_sequence_consistency() -> None:
    service = RealtimeOrderBookService(Settings(data_mode="test"), [])
    service.apply_snapshot(_book("0.45", "10"), sequence=10)

    updated = service.apply_delta(
        Exchange.POLYMARKET,
        "pm",
        Side.YES,
        asks=[PriceLevel(price=Decimal("0.44"), quantity=Decimal("5"), source_side="ask")],
        sequence=11,
        expected_previous_sequence=10,
    )

    assert [level.price for level in updated.asks] == [Decimal("0.44"), Decimal("0.45")]
    assert service.statuses()[0].last_sequence == 11


def test_sequence_gap_is_rejected() -> None:
    service = RealtimeOrderBookService(Settings(data_mode="test"), [])
    service.apply_snapshot(_book("0.45", "10"), sequence=10)

    with pytest.raises(SequenceGapError):
        service.apply_delta(
            Exchange.POLYMARKET,
            "pm",
            Side.YES,
            asks=[PriceLevel(price=Decimal("0.44"), quantity=Decimal("5"), source_side="ask")],
            sequence=12,
            expected_previous_sequence=9,
        )


def test_stale_books_are_excluded() -> None:
    service = RealtimeOrderBookService(
        Settings(data_mode="test", orderbook_max_age_seconds=1),
        [],
    )
    fetched_at = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)
    service.apply_snapshot(_book("0.45", "10", fetched_at=fetched_at), sequence=1)

    books = service.books(fetched_at + timedelta(seconds=2))
    status = service.statuses(fetched_at + timedelta(seconds=2))[0]

    assert books == []
    assert status.stale is True


def _book(
    price: str,
    quantity: str,
    fetched_at: datetime | None = None,
) -> OrderBook:
    return OrderBook(
        exchange=Exchange.POLYMARKET,
        market_id="pm",
        outcome_id="pm:yes",
        side=Side.YES,
        asks=[PriceLevel(price=Decimal(price), quantity=Decimal(quantity), source_side="ask")],
        fetched_at=fetched_at or datetime.now(UTC),
        raw={"sequence": 1},
    )
