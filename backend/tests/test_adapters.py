from decimal import Decimal

import pytest

from app.config import Settings
from app.exchanges.kalshi import KalshiAdapter, _bid_level, _derived_ask
from app.exchanges.polymarket import PolymarketAdapter
from app.models.domain import Exchange, Side


@pytest.mark.asyncio
async def test_polymarket_fixture_normalization() -> None:
    adapter = PolymarketAdapter(Settings(data_mode="test", use_fixtures=True))

    markets = await adapter.fetch_active_markets()
    books = await adapter.fetch_order_books(markets)

    assert markets[0].exchange == Exchange.POLYMARKET
    assert markets[0].same_market_key == "fed-july-rate-cut"
    assert markets[0].outcomes[0].id == "pm-fed-yes"
    assert markets[0].outcomes[1].id == "pm-fed-no"
    assert {outcome.side for outcome in markets[0].outcomes} == {Side.YES, Side.NO}
    assert adapter.last_rejections == [
        {
            "condition_id": "pm-condition-non-binary",
            "question": "Which team will win?",
            "reason": "unsupported binary outcome name: Team A",
        }
    ]
    assert len(books) == 2
    assert books[0].raw["market"] == "pm-condition-fed-july"


@pytest.mark.asyncio
async def test_kalshi_bid_books_are_explicitly_derived_to_asks() -> None:
    adapter = KalshiAdapter(Settings(data_mode="test", use_fixtures=True))

    markets = await adapter.fetch_active_markets()
    books = await adapter.fetch_order_books(markets)
    yes_book = next(book for book in books if book.side == Side.YES)
    no_book = next(book for book in books if book.side == Side.NO)

    assert yes_book.exchange == Exchange.KALSHI
    assert len(markets) == 1
    assert markets[0].exchange_market_id == "KXFEDCUT-26JUL"
    assert adapter.last_rejections == [
        {
            "ticker": "KXMULTI-26JUL",
            "title": "Non-binary fixture market",
            "reason": "unsupported market_type: multivariate",
        },
        {
            "ticker": "KXPAUSED-26JUL",
            "title": "Inactive fixture market",
            "reason": "market status is not active: inactive",
        },
    ]
    assert yes_book.asks[0].price == Decimal("0.52")
    assert yes_book.asks[0].source_side == "bid_derived_ask"
    assert yes_book.asks[0].raw["derivation"] == "opposite outcome ask = 1 - bid"
    assert no_book.asks[0].price == Decimal("0.45")
    assert no_book.asks[0].source_side == "bid_derived_ask"


def test_kalshi_bid_to_ask_conversion_uses_decimal_dollars_once() -> None:
    yes_bid = _bid_level(["0.47", "125"])
    yes_ask_from_no_bid = _derived_ask(["0.53", "125"])

    assert yes_bid.price == Decimal("0.47")
    assert yes_bid.quantity == Decimal("125")
    assert yes_ask_from_no_bid.price == Decimal("0.47")
    assert yes_ask_from_no_bid.quantity == Decimal("125")
    assert yes_ask_from_no_bid.source_side == "bid_derived_ask"


def test_kalshi_complementary_ask_is_not_inverted_or_divided_twice() -> None:
    no_bid_cents_already_decimal = ["0.99", "10"]
    yes_ask = _derived_ask(no_bid_cents_already_decimal)

    assert yes_ask.price == Decimal("0.01")
    assert yes_ask.price != Decimal("0.9999")
    assert yes_ask.price != Decimal("99")
