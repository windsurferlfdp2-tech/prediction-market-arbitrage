from decimal import Decimal

import pytest

from app.config import Settings
from app.exchanges.kalshi import KalshiAdapter
from app.exchanges.polymarket import PolymarketAdapter
from app.models.domain import Exchange, Side


@pytest.mark.asyncio
async def test_polymarket_fixture_normalization() -> None:
    adapter = PolymarketAdapter(Settings(use_fixtures=True))

    markets = await adapter.fetch_active_markets()
    books = await adapter.fetch_order_books(markets)

    assert markets[0].exchange == Exchange.POLYMARKET
    assert markets[0].same_market_key == "fed-july-rate-cut"
    assert {outcome.side for outcome in markets[0].outcomes} == {Side.YES, Side.NO}
    assert len(books) == 2
    assert books[0].raw["market"] == "pm-condition-fed-july"


@pytest.mark.asyncio
async def test_kalshi_bid_books_are_explicitly_derived_to_asks() -> None:
    adapter = KalshiAdapter(Settings(use_fixtures=True))

    markets = await adapter.fetch_active_markets()
    books = await adapter.fetch_order_books(markets)
    yes_book = next(book for book in books if book.side == Side.YES)
    no_book = next(book for book in books if book.side == Side.NO)

    assert yes_book.exchange == Exchange.KALSHI
    assert yes_book.asks[0].price == Decimal("0.52")
    assert yes_book.asks[0].source_side == "bid_derived_ask"
    assert no_book.asks[0].price == Decimal("0.45")
    assert no_book.asks[0].source_side == "bid_derived_ask"
