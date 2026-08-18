from decimal import Decimal

import pytest

from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.models.domain import Exchange, ExchangeHealth, Market, OrderBook
from app.services.scanner import ScannerService


class RaisingAdapter(ExchangeAdapter):
    name = "raising"

    async def fetch_active_markets(self) -> list[Market]:
        raise AssertionError("test mode must not call exchange adapters")

    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        raise AssertionError("test mode must not call exchange adapters")

    async def health(self) -> ExchangeHealth:
        raise AssertionError("test mode must not call exchange adapters")


class EmptyAdapter(ExchangeAdapter):
    name = "empty"

    def __init__(self) -> None:
        self.called = False

    async def fetch_active_markets(self) -> list[Market]:
        self.called = True
        return []

    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        return []

    async def health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=Exchange.POLYMARKET, ok=True, message="test")


class ManyMarketsAdapter(ExchangeAdapter):
    name = "many"

    def __init__(self) -> None:
        self.order_book_market_count = 0

    async def fetch_active_markets(self) -> list[Market]:
        return [
            Market(
                exchange=Exchange.POLYMARKET,
                exchange_market_id=f"PM-{index}",
                title=f"Market {index}",
                status="active",
                outcomes=[],
                same_market_key=f"market-{index}",
            )
            for index in range(10)
        ]

    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        self.order_book_market_count = len(markets)
        return []

    async def health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=Exchange.POLYMARKET, ok=True, message="test")


@pytest.mark.asyncio
async def test_test_mode_returns_three_labeled_opportunities_without_adapters() -> None:
    scanner = ScannerService(
        Settings(
            data_mode="test",
            use_fixtures=False,
            min_net_profit=Decimal("0.01"),
            min_roi=Decimal("0.001"),
        ),
        [RaisingAdapter()],
    )

    opportunities = await scanner.opportunities()
    markets = await scanner.markets()
    health = await scanner.health()

    assert len(opportunities) == 3
    assert all(item.title.startswith("TEST:") for item in opportunities)
    assert all(item.same_market_key.startswith("TEST:") for item in opportunities)
    assert all(level.source_side == "ask" for item in opportunities for level in item.used_levels)
    assert {market.status for market in markets} == {"test"}
    assert health == []


@pytest.mark.asyncio
async def test_live_mode_uses_adapters_and_returns_no_simulated_opportunities() -> None:
    adapter = EmptyAdapter()
    scanner = ScannerService(Settings(data_mode="live", use_fixtures=False), [adapter])

    opportunities = await scanner.opportunities()

    assert adapter.called is True
    assert opportunities == []


@pytest.mark.asyncio
async def test_live_mode_limits_markets_before_fetching_order_books() -> None:
    adapter = ManyMarketsAdapter()
    scanner = ScannerService(
        Settings(data_mode="live", use_fixtures=False, live_scan_market_limit=3),
        [adapter],
    )

    await scanner.opportunities()

    assert adapter.order_book_market_count == 3


def test_production_defaults_do_not_enable_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATA_MODE", raising=False)
    settings = Settings(_env_file=None, app_env="production", use_fixtures=False)

    assert settings.effective_data_mode == "live"


def test_live_mode_rejects_fixture_loading() -> None:
    with pytest.raises(ValueError, match="USE_FIXTURES is only allowed"):
        Settings(data_mode="live", use_fixtures=True)


def test_production_rejects_test_mode() -> None:
    with pytest.raises(ValueError, match="production requires DATA_MODE=live"):
        Settings(app_env="production", data_mode="test", use_fixtures=False)
