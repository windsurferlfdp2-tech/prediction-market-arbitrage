from app.arbitrage.detector import ArbitrageDetector
from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.models.domain import ArbitrageOpportunity, ExchangeHealth, Market, OrderBook


class ScannerService:
    def __init__(self, settings: Settings, adapters: list[ExchangeAdapter]) -> None:
        self.settings = settings
        self.adapters = adapters
        self.detector = ArbitrageDetector(
            max_age_seconds=settings.orderbook_max_age_seconds,
            min_net_profit=settings.min_net_profit,
            min_roi=settings.min_roi,
            fee_rate=settings.fee_rate,
            slippage_rate=settings.slippage_rate,
        )
        self._markets: list[Market] = []
        self._books: list[OrderBook] = []
        self._opportunities: list[ArbitrageOpportunity] = []

    async def refresh(self) -> list[ArbitrageOpportunity]:
        markets: list[Market] = []
        books: list[OrderBook] = []
        for adapter in self.adapters:
            adapter_markets = await adapter.fetch_active_markets()
            markets.extend(adapter_markets)
            books.extend(await adapter.fetch_order_books(adapter_markets))
        self._markets = markets
        self._books = books
        self._opportunities = self.detector.detect(markets, books)
        return self._opportunities

    async def markets(self) -> list[Market]:
        if not self._markets:
            await self.refresh()
        return self._markets

    async def opportunities(self) -> list[ArbitrageOpportunity]:
        await self.refresh()
        return self._opportunities

    async def opportunity(self, opportunity_id: str) -> ArbitrageOpportunity | None:
        opportunities = await self.opportunities()
        return next((item for item in opportunities if item.id == opportunity_id), None)

    async def health(self) -> list[ExchangeHealth]:
        return [await adapter.health() for adapter in self.adapters]
