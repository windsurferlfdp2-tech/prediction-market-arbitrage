from abc import ABC, abstractmethod

from app.models.domain import ExchangeHealth, Market, OrderBook


class ExchangeAdapter(ABC):
    name: str

    @abstractmethod
    async def fetch_active_markets(self) -> list[Market]:
        raise NotImplementedError

    @abstractmethod
    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> ExchangeHealth:
        raise NotImplementedError
