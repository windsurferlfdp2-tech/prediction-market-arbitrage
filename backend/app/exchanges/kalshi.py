from datetime import UTC, datetime
from decimal import Decimal

from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.exchanges.http import RetryingHttpClient
from app.exchanges.raw import KalshiRawMarket, KalshiRawOrderBook
from app.models.domain import Exchange, ExchangeHealth, Market, OrderBook, Outcome, PriceLevel, Side

ONE = Decimal("1")


class KalshiAdapter(ExchangeAdapter):
    name = Exchange.KALSHI.value

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

            payload = load_fixture("kalshi_markets.json")
            fixture_markets = [
                KalshiRawMarket.model_validate(item) for item in payload.get("markets", [])
            ]
            markets = self._normalize_markets(fixture_markets)
            self._record_market_fetch(len(fixture_markets), len(markets))
            return markets

        live_markets: list[KalshiRawMarket] = []
        parse_rejections: list[dict[str, str]] = []
        cursor: str | None = None
        max_markets = self.settings.live_scan_market_limit
        while True:
            limit = 1000 if max_markets <= 0 else min(1000, max_markets)
            params = {"status": "open", "limit": limit, "mve_filter": "exclude"}
            if cursor:
                params["cursor"] = cursor
            payload = await self.client.get_json(f"{self.settings.kalshi_base_url}/markets", params)
            if not isinstance(payload, dict):
                raise ValueError("Kalshi markets endpoint returned non-object payload")
            for item in payload.get("markets", []):
                try:
                    live_markets.append(KalshiRawMarket.model_validate(item))
                except Exception as exc:
                    parse_rejections.append(
                        {"ticker": "", "title": "", "reason": f"invalid payload: {exc}"}
                    )
            if max_markets > 0 and len(live_markets) >= max_markets:
                live_markets = live_markets[:max_markets]
                break
            cursor = payload.get("cursor")
            if not cursor:
                break
        markets = self._normalize_markets(live_markets)
        self.last_rejections.extend(parse_rejections)
        self._record_market_fetch(len(live_markets), len(markets))
        return markets

    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        if not markets:
            return []
        now = datetime.now(UTC)
        self.last_order_books_requested = len(markets)
        self.last_order_books_returned = 0
        self.last_order_book_errors = []
        if self.settings.effective_data_mode == "test":
            from app.exchanges.fixtures import load_fixture

            payload = load_fixture("kalshi_orderbooks.json")
            raw_books = [
                KalshiRawOrderBook.model_validate(item) for item in payload.get("orderbooks", [])
            ]
        else:
            raw_books = []
            for market in markets:
                try:
                    payload = await self.client.get_json(
                        f"{self.settings.kalshi_base_url}/markets/{market.exchange_market_id}/orderbook"
                    )
                    if not isinstance(payload, dict):
                        raise ValueError("Kalshi orderbook endpoint returned non-object payload")
                    raw_books.append(
                        KalshiRawOrderBook.model_validate(
                            {
                                "ticker": market.exchange_market_id,
                                "orderbook_fp": _orderbook_fp(payload),
                            }
                        )
                    )
                except Exception as exc:
                    self.last_order_book_errors.append(
                        {"market_id": market.exchange_market_id, "reason": str(exc)}
                    )
        books: list[OrderBook] = []
        for raw in raw_books:
            try:
                books.extend(self._normalize_order_books(raw, now))
            except Exception as exc:
                self.last_order_book_errors.append({"market_id": raw.ticker, "reason": str(exc)})
        self.last_order_books_returned = len(books)
        return books

    async def health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=Exchange.KALSHI, ok=True, message="configured")

    def _normalize_markets(self, raw_markets: list[KalshiRawMarket]) -> list[Market]:
        markets: list[Market] = []
        self.last_rejections = []
        for raw in raw_markets:
            try:
                markets.append(self._normalize_market(raw))
            except ValueError as exc:
                self.last_rejections.append(
                    {"ticker": raw.ticker, "title": _market_title(raw), "reason": str(exc)}
                )
        return markets

    def _record_market_fetch(self, raw_count: int, normalized_count: int) -> None:
        self.last_fetch_timestamp = datetime.now(UTC)
        self.last_raw_market_count = raw_count
        self.last_normalized_market_count = normalized_count

    def _normalize_market(self, raw: KalshiRawMarket) -> Market:
        if raw.market_type != "binary":
            raise ValueError(f"unsupported market_type: {raw.market_type}")
        if raw.status != "active":
            raise ValueError(f"market status is not active: {raw.status}")
        return Market(
            exchange=Exchange.KALSHI,
            exchange_market_id=raw.ticker,
            title=_market_title(raw),
            status=raw.status,
            same_market_key=raw.event_ticker or raw.ticker,
            outcomes=[
                Outcome(id=f"{raw.ticker}:yes", name=raw.yes_sub_title or "Yes", side=Side.YES),
                Outcome(id=f"{raw.ticker}:no", name=raw.no_sub_title or "No", side=Side.NO),
            ],
            raw=raw.model_dump(),
        )

    def _normalize_order_books(
        self, raw: KalshiRawOrderBook, fetched_at: datetime
    ) -> list[OrderBook]:
        yes_bids = raw.orderbook_fp.get("yes_dollars")
        no_bids = raw.orderbook_fp.get("no_dollars")
        if yes_bids is None or no_bids is None:
            raise ValueError(f"Kalshi orderbook {raw.ticker} missing yes_dollars or no_dollars")

        yes_asks = [_derived_ask(level) for level in no_bids]
        no_asks = [_derived_ask(level) for level in yes_bids]
        return [
            OrderBook(
                exchange=Exchange.KALSHI,
                market_id=raw.ticker,
                outcome_id=f"{raw.ticker}:yes",
                side=Side.YES,
                asks=sorted(yes_asks, key=lambda level: level.price),
                bids=[_bid_level(level) for level in yes_bids],
                fetched_at=fetched_at,
                raw=raw.model_dump(),
            ),
            OrderBook(
                exchange=Exchange.KALSHI,
                market_id=raw.ticker,
                outcome_id=f"{raw.ticker}:no",
                side=Side.NO,
                asks=sorted(no_asks, key=lambda level: level.price),
                bids=[_bid_level(level) for level in no_bids],
                fetched_at=fetched_at,
                raw=raw.model_dump(),
            ),
        ]


def _bid_level(level: list[str]) -> PriceLevel:
    if len(level) < 2:
        raise ValueError("Kalshi price level missing price or quantity")
    return PriceLevel(
        price=Decimal(level[0]), quantity=Decimal(level[1]), source_side="bid", raw={"level": level}
    )


def _market_title(raw: KalshiRawMarket) -> str:
    return raw.title or raw.subtitle or raw.yes_sub_title or raw.ticker


def _orderbook_fp(payload: dict[str, object]) -> object:
    orderbook = payload.get("orderbook")
    if isinstance(orderbook, dict) and "orderbook_fp" in orderbook:
        return orderbook["orderbook_fp"]
    return payload.get("orderbook_fp")


def _derived_ask(level: list[str]) -> PriceLevel:
    if len(level) < 2:
        raise ValueError("Kalshi price level missing price or quantity")
    bid_price = Decimal(level[0])
    return PriceLevel(
        price=ONE - bid_price,
        quantity=Decimal(level[1]),
        source_side="bid_derived_ask",
        raw={"source_bid": level, "derivation": "opposite outcome ask = 1 - bid"},
    )
