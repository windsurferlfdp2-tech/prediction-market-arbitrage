from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.exchanges.fixtures import load_fixture
from app.exchanges.http import RetryingHttpClient
from app.exchanges.raw import PolymarketRawMarket, PolymarketRawOrderBook
from app.models.domain import Exchange, ExchangeHealth, Market, OrderBook, Outcome, PriceLevel, Side


class PolymarketAdapter(ExchangeAdapter):
    name = Exchange.POLYMARKET.value

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = RetryingHttpClient(
            settings.request_timeout_seconds,
            settings.request_retries,
            settings.request_backoff_seconds,
        )

    async def fetch_active_markets(self) -> list[Market]:
        if self.settings.use_fixtures:
            payload = load_fixture("polymarket_markets.json")
            raw_markets = [PolymarketRawMarket.model_validate(item) for item in payload["data"]]
            return [self._normalize_market(item) for item in raw_markets]

        url = f"{self.settings.polymarket_base_url}/sampling-markets"
        payload = await self.client.get_json(str(url), params={"limit": 100})
        raw_markets = [PolymarketRawMarket.model_validate(item) for item in payload.get("data", [])]
        return [self._normalize_market(item) for item in raw_markets if item.active and not item.closed]

    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        books: list[OrderBook] = []
        for market in markets:
            for outcome in market.outcomes:
                if self.settings.use_fixtures:
                    payload = load_fixture(f"polymarket_book_{outcome.id}.json")
                else:
                    payload = await self.client.get_json(
                        f"{self.settings.polymarket_base_url}/book",
                        params={"token_id": outcome.id},
                    )
                raw = PolymarketRawOrderBook.model_validate(payload)
                books.append(self._normalize_order_book(raw, outcome.side))
        return books

    async def health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=Exchange.POLYMARKET, ok=True, message="configured")

    def _normalize_market(self, raw: PolymarketRawMarket) -> Market:
        outcomes = [
            Outcome(
                id=str(token["token_id"]),
                name=str(token["outcome"]),
                side=Side.YES if str(token["outcome"]).lower() == "yes" else Side.NO,
            )
            for token in raw.tokens
            if token.get("token_id") and token.get("outcome")
        ]
        if len(outcomes) != 2:
            raise ValueError(f"Polymarket market {raw.condition_id} is not binary")
        return Market(
            exchange=Exchange.POLYMARKET,
            exchange_market_id=raw.condition_id,
            title=raw.question,
            status="active" if raw.active and not raw.closed else "inactive",
            outcomes=outcomes,
            same_market_key=raw.market_slug,
            raw=raw.model_dump(),
        )

    def _normalize_order_book(self, raw: PolymarketRawOrderBook, side: Side) -> OrderBook:
        fetched_at = _parse_timestamp(raw.timestamp)
        return OrderBook(
            exchange=Exchange.POLYMARKET,
            market_id=raw.market,
            outcome_id=raw.asset_id,
            side=side,
            asks=[_poly_level(item, "ask") for item in raw.asks],
            bids=[_poly_level(item, "bid") for item in raw.bids],
            fetched_at=fetched_at,
            exchange_timestamp=fetched_at,
            raw=raw.model_dump(),
        )


def _poly_level(item: dict[str, Any], source_side: str) -> PriceLevel:
    if "price" not in item or "size" not in item:
        raise ValueError("Polymarket price level missing price or size")
    return PriceLevel(
        price=Decimal(item["price"]),
        quantity=Decimal(item["size"]),
        source_side=source_side,  # type: ignore[arg-type]
        raw=item,
    )


def _parse_timestamp(value: str) -> datetime:
    if value.isdigit():
        numeric = Decimal(value)
        if numeric > Decimal("9999999999"):
            numeric = numeric / Decimal("1000")
        return datetime.fromtimestamp(float(numeric), tz=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
