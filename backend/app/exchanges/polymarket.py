import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.exchanges.base import ExchangeAdapter
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
        self.last_rejections: list[dict[str, str]] = []
        self.last_fetch_timestamp: datetime | None = None
        self.last_raw_market_count = 0
        self.last_normalized_market_count = 0
        self.last_order_books_requested = 0
        self.last_order_books_returned = 0
        self.last_order_book_errors: list[dict[str, str]] = []

    async def fetch_active_markets(self) -> list[Market]:
        if self.settings.effective_data_mode == "test":
            from app.exchanges.fixtures import load_fixture

            payload = load_fixture("polymarket_markets.json")
            fixture_markets = [PolymarketRawMarket.model_validate(item) for item in payload["data"]]
            markets = self._normalize_markets(fixture_markets)
            self._record_market_fetch(len(fixture_markets), len(markets))
            return markets

        live_markets: list[PolymarketRawMarket] = []
        parse_rejections: list[dict[str, str]] = []
        max_markets = self.settings.live_scan_market_limit
        limit = 100 if max_markets <= 0 else min(100, max_markets)
        offset = 0
        max_offset = 2000
        while offset <= max_offset:
            payload = await self.client.get_json(
                f"{self.settings.polymarket_gamma_base_url}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                    "offset": offset,
                },
            )
            if not isinstance(payload, list):
                raise ValueError("Polymarket markets endpoint returned non-list payload")
            if not payload:
                break
            for item in payload:
                try:
                    live_markets.append(PolymarketRawMarket.model_validate(item))
                except Exception as exc:
                    parse_rejections.append(
                        {"condition_id": "", "question": "", "reason": f"invalid payload: {exc}"}
                    )
            if max_markets > 0 and len(live_markets) >= max_markets:
                live_markets = live_markets[:max_markets]
                break
            if len(payload) < limit:
                break
            offset += limit
        markets = self._normalize_markets(live_markets)
        self.last_rejections.extend(parse_rejections)
        self._record_market_fetch(len(live_markets), len(markets))
        return markets

    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        books: list[OrderBook] = []
        self.last_order_books_requested = sum(len(market.outcomes) for market in markets)
        self.last_order_books_returned = 0
        self.last_order_book_errors = []
        for market in markets:
            for outcome in market.outcomes:
                try:
                    if self.settings.effective_data_mode == "test":
                        from app.exchanges.fixtures import load_fixture

                        payload = load_fixture(f"polymarket_book_{outcome.id}.json")
                    else:
                        payload = await self.client.get_json(
                            f"{self.settings.polymarket_base_url}/book",
                            params={"token_id": outcome.id},
                        )
                    raw = PolymarketRawOrderBook.model_validate(payload)
                    books.append(self._normalize_order_book(raw, outcome.side))
                except Exception as exc:
                    self.last_order_book_errors.append(
                        {
                            "market_id": market.exchange_market_id,
                            "outcome_id": outcome.id,
                            "reason": str(exc),
                        }
                    )
        self.last_order_books_returned = len(books)
        return books

    async def health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=Exchange.POLYMARKET, ok=True, message="configured")

    def _normalize_markets(self, raw_markets: list[PolymarketRawMarket]) -> list[Market]:
        markets: list[Market] = []
        self.last_rejections = []
        for raw in raw_markets:
            try:
                markets.append(self._normalize_market(raw))
            except ValueError as exc:
                self.last_rejections.append(
                    {
                        "condition_id": raw.condition_id,
                        "question": raw.question,
                        "reason": str(exc),
                    }
                )
        return markets

    def _record_market_fetch(self, raw_count: int, normalized_count: int) -> None:
        self.last_fetch_timestamp = datetime.now(UTC)
        self.last_raw_market_count = raw_count
        self.last_normalized_market_count = normalized_count

    def _normalize_market(self, raw: PolymarketRawMarket) -> Market:
        if not raw.active or raw.closed:
            raise ValueError("market is not active")
        if not raw.enable_order_book:
            raise ValueError("market does not have CLOB order book enabled")

        token_ids, outcome_names = _market_tokens_and_outcomes(raw)
        outcomes = []
        for token_id, outcome_name in zip(token_ids, outcome_names, strict=True):
            normalized_name = outcome_name.lower()
            if normalized_name not in {"yes", "no"}:
                raise ValueError(f"unsupported binary outcome name: {outcome_name}")
            outcomes.append(
                Outcome(
                    id=token_id,
                    name=outcome_name,
                    side=Side.YES if normalized_name == "yes" else Side.NO,
                )
            )
        if len(outcomes) != 2:
            raise ValueError(f"Polymarket market {raw.condition_id} is not binary")
        if {outcome.side for outcome in outcomes} != {Side.YES, Side.NO}:
            raise ValueError(f"Polymarket market {raw.condition_id} must have YES and NO outcomes")
        return Market(
            exchange=Exchange.POLYMARKET,
            exchange_market_id=raw.condition_id,
            title=raw.question,
            status="active" if raw.active and not raw.closed else "inactive",
            outcomes=outcomes,
            same_market_key=raw.market_slug or raw.condition_id,
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
        source_side=source_side,
        raw=item,
    )


def _market_tokens_and_outcomes(raw: PolymarketRawMarket) -> tuple[list[str], list[str]]:
    if raw.tokens:
        tokens = [
            (str(token["token_id"]), str(token["outcome"]))
            for token in raw.tokens
            if token.get("token_id") and token.get("outcome")
        ]
        return [token_id for token_id, _ in tokens], [outcome for _, outcome in tokens]

    token_ids = _json_array(raw.clob_token_ids, "clobTokenIds")
    outcome_names = _json_array(raw.outcomes, "outcomes")
    if len(token_ids) != len(outcome_names):
        raise ValueError("clobTokenIds and outcomes lengths do not match")
    return token_ids, outcome_names


def _json_array(value: str | list[str] | None, field_name: str) -> list[str]:
    if value is None:
        raise ValueError(f"missing {field_name}")
    if isinstance(value, list):
        return [str(item) for item in value]
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError(f"{field_name} is not a JSON array")
    return [str(item) for item in parsed]


def _parse_timestamp(value: str) -> datetime:
    if value.isdigit():
        numeric = Decimal(value)
        if numeric > Decimal("9999999999"):
            numeric = numeric / Decimal("1000")
        return datetime.fromtimestamp(float(numeric), tz=UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
