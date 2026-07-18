from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlencode

from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.exchanges.fixtures import load_fixture
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

    async def fetch_active_markets(self) -> list[Market]:
        if self.settings.use_fixtures:
            payload = load_fixture("kalshi_markets.json")
        else:
            payload = await self.client.get_json(
                f"{self.settings.kalshi_base_url}/markets",
                params={"status": "open", "limit": 100, "mve_filter": "exclude"},
            )
        raw_markets = [KalshiRawMarket.model_validate(item) for item in payload.get("markets", [])]
        return [self._normalize_market(item) for item in raw_markets if item.market_type == "binary"]

    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        if not markets:
            return []
        tickers = [market.exchange_market_id for market in markets]
        if self.settings.use_fixtures:
            payload = load_fixture("kalshi_orderbooks.json")
        else:
            query = urlencode([("tickers", ticker) for ticker in tickers])
            payload = await self.client.get_json(f"{self.settings.kalshi_base_url}/markets/orderbooks?{query}")
        now = datetime.now(UTC)
        raw_books = [KalshiRawOrderBook.model_validate(item) for item in payload.get("orderbooks", [])]
        return [book for raw in raw_books for book in self._normalize_order_books(raw, now)]

    async def health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=Exchange.KALSHI, ok=True, message="configured")

    def _normalize_market(self, raw: KalshiRawMarket) -> Market:
        return Market(
            exchange=Exchange.KALSHI,
            exchange_market_id=raw.ticker,
            title=raw.title,
            status=raw.status,
            same_market_key=raw.event_ticker or raw.ticker,
            outcomes=[
                Outcome(id=f"{raw.ticker}:yes", name=raw.yes_sub_title or "Yes", side=Side.YES),
                Outcome(id=f"{raw.ticker}:no", name=raw.no_sub_title or "No", side=Side.NO),
            ],
            raw=raw.model_dump(),
        )

    def _normalize_order_books(self, raw: KalshiRawOrderBook, fetched_at: datetime) -> list[OrderBook]:
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
    return PriceLevel(price=Decimal(level[0]), quantity=Decimal(level[1]), source_side="bid", raw={"level": level})


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
