from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.models.domain import Exchange, ExchangeHealth, Market, OrderBook, Outcome, PriceLevel, Side
from app.persistence.database import (
    MarketPairReviewRecord,
    OpportunityHistoryRecord,
    SqlAlchemyDatabaseBackend,
)
from app.services.history import OpportunityHistoryRecorder
from app.services.market_matching import MarketMatchingService, ReviewStatus
from app.services.scanner import ScannerService


@pytest.mark.asyncio
async def test_generates_pending_review_candidates_with_mismatch_details(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'matches.db'}")
    await backend.init()
    service = MarketMatchingService(backend.sessionmaker)

    reviews = await service.generate_candidates([_pm_market(), _kalshi_market()])

    assert len(reviews) == 1
    review = reviews[0]
    assert review.status == "pending_review"
    assert review.polymarket_title == "Will CPI be above 3% on July 20?"
    assert review.kalshi_title == "Will CPI be over 4% on July 20?"
    assert review.polymarket_resolution_criteria == "Official CPI release above 3%"
    assert review.kalshi_resolution_criteria == "Official CPI release over 4%"
    assert review.polymarket_close_date == "2026-07-20T12:00:00Z"
    assert review.kalshi_close_date == "2026-07-20T12:00:00Z"
    assert review.polymarket_resolution_sources == ["BLS"]
    assert review.kalshi_resolution_sources == ["BLS"]
    assert "CPI" in review.polymarket_entities
    assert "CPI" in review.kalshi_entities
    assert "3%" in review.polymarket_numbers
    assert "4%" in review.kalshi_numbers
    assert review.similarity_score > Decimal("0")
    assert any("number/date mismatch" in mismatch for mismatch in review.mismatches)


@pytest.mark.asyncio
async def test_manual_approval_required_before_scanner_uses_pair(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'approval.db'}")
    await backend.init()
    matching = MarketMatchingService(backend.sessionmaker)
    adapter = StaticAdapter([_pm_market(), _kalshi_market()])
    scanner = ScannerService(
        Settings(data_mode="live"),
        [adapter],
        market_matching_service=matching,
    )

    await matching.generate_candidates([_pm_market(), _kalshi_market()])
    assert await scanner.opportunities() == []

    review = (await matching.list_reviews())[0]
    await matching.update_status(review.id, "verified_equivalent")
    opportunities = await scanner.opportunities()

    assert len(opportunities) == 1
    assert opportunities[0].same_market_key == f"verified:{review.id}"
    status = scanner.status()
    diagnostics = status["diagnostics"]
    assert diagnostics["funnel"]["verified_pairs_active_on_both_exchanges"] == 1
    assert diagnostics["funnel"]["raw_pricing_discrepancies"] == 1
    assert diagnostics["funnel"]["final_opportunities_returned_by_api"] == 1


@pytest.mark.asyncio
async def test_verified_fixture_pair_persists_through_history_recorder(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'pipeline.db'}")
    await backend.init()
    matching = MarketMatchingService(backend.sessionmaker)
    recorder = OpportunityHistoryRecorder(backend.sessionmaker)
    adapter = StaticAdapter([_pm_market(), _kalshi_market()])
    scanner = ScannerService(
        Settings(data_mode="live"),
        [adapter],
        history_recorder=recorder,
        market_matching_service=matching,
    )

    await matching.generate_candidates([_pm_market(), _kalshi_market()])
    review = (await matching.list_reviews())[0]
    await matching.update_status(review.id, "verified_equivalent")
    opportunities = await scanner.opportunities()

    assert len(opportunities) == 1
    async with backend.sessionmaker() as session:
        records = list((await session.execute(select(OpportunityHistoryRecord))).scalars())
    assert len(records) == 1
    assert records[0].same_market_key == f"verified:{review.id}"
    assert records[0].data_mode == "live"


@pytest.mark.asyncio
async def test_non_equivalent_statuses_do_not_enable_scanner_pair(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'rejected.db'}")
    await backend.init()
    matching = MarketMatchingService(backend.sessionmaker)
    adapter = StaticAdapter([_pm_market(), _kalshi_market()])
    scanner = ScannerService(
        Settings(data_mode="live"),
        [adapter],
        market_matching_service=matching,
    )

    await matching.generate_candidates([_pm_market(), _kalshi_market()])
    review = (await matching.list_reviews())[0]
    statuses: list[ReviewStatus] = ["related_not_equivalent", "rejected"]
    for status in statuses:
        await matching.update_status(review.id, status)
        assert await scanner.opportunities() == []


@pytest.mark.asyncio
async def test_generation_returns_only_current_candidate_set(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'sets.db'}")
    await backend.init()
    service = MarketMatchingService(backend.sessionmaker)

    first = await service.generate_candidates([_pm_market(), _kalshi_market()])
    second = await service.generate_candidates(
        [
            _pm_market().model_copy(
                update={
                    "exchange_market_id": "pm-fed",
                    "title": "Will Fed cut rates in July?",
                }
            ),
            _kalshi_market().model_copy(
                update={
                    "exchange_market_id": "KXFED",
                    "title": "Will Fed cut rates in July?",
                }
            ),
        ]
    )

    assert len(first) == 1
    assert len(second) == 1
    assert first[0].id != second[0].id
    assert second[0].polymarket_market_id == "pm-fed"


@pytest.mark.asyncio
async def test_review_mismatches_include_direction_threshold_timezone_and_source(
    tmp_path: Path,
) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'mismatches.db'}")
    await backend.init()
    service = MarketMatchingService(backend.sessionmaker)

    polymarket = _pm_market().model_copy(
        update={
            "title": "Will CPI be at least 3% by July 20 5pm ET?",
            "raw": {
                "description": "CPI at least 3%",
                "resolutionSource": "BLS",
                "endDate": "2026-07-20T21:00:00Z",
            },
        }
    )
    kalshi = _kalshi_market().model_copy(
        update={
            "title": "Will CPI be below 3% by July 20 5pm PT?",
            "raw": {
                "rules_primary": "CPI below 3%",
                "source": "Federal Reserve",
                "close_time": "2026-07-21T00:00:00Z",
            },
        }
    )

    review = (await service.generate_candidates([polymarket, kalshi]))[0]

    assert any("outcome direction mismatch" in mismatch for mismatch in review.mismatches)
    assert any(
        "inclusive/exclusive threshold mismatch" in mismatch for mismatch in review.mismatches
    )
    assert any("timezone mismatch" in mismatch for mismatch in review.mismatches)
    assert any("resolution source mismatch" in mismatch for mismatch in review.mismatches)


@pytest.mark.asyncio
async def test_non_live_reviews_are_excluded_from_runtime_lists_and_verified_pairs(
    tmp_path: Path,
) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'non-live.db'}")
    await backend.init()
    service = MarketMatchingService(backend.sessionmaker)
    now = datetime.now(UTC)
    async with backend.sessionmaker() as session:
        session.add(
            MarketPairReviewRecord(
                id="simulation-review",
                polymarket_market_id="SIM-POLY-1",
                kalshi_market_id="SIM-KALSHI-1",
                polymarket_title="SIMULATION: Fed cuts rates",
                kalshi_title="SIMULATION: Fed cuts rates",
                polymarket_resolution_criteria="SIMULATION: Fed cuts rates",
                kalshi_resolution_criteria="SIMULATION: Fed cuts rates",
                polymarket_close_date=None,
                kalshi_close_date=None,
                polymarket_settlement_date=None,
                kalshi_settlement_date=None,
                polymarket_resolution_sources=[],
                kalshi_resolution_sources=[],
                polymarket_entities=["SIMULATION Fed"],
                kalshi_entities=["SIMULATION Fed"],
                polymarket_numbers=[],
                kalshi_numbers=[],
                similarity_score=Decimal("1"),
                mismatches=[],
                status="verified_equivalent",
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    assert await service.list_reviews() == []
    assert await service.verified_same_market_keys() == {}


class StaticAdapter(ExchangeAdapter):
    name = "static"

    def __init__(self, markets: list[Market]) -> None:
        self._markets = markets

    async def fetch_active_markets(self) -> list[Market]:
        return self._markets

    async def fetch_order_books(self, markets: list[Market]) -> list[OrderBook]:
        now = datetime.now(UTC)
        books: list[OrderBook] = []
        for market in markets:
            if market.exchange == Exchange.POLYMARKET:
                books.append(
                    _book(market.exchange, market.exchange_market_id, Side.YES, "0.40", now)
                )
            if market.exchange == Exchange.KALSHI:
                books.append(
                    _book(market.exchange, market.exchange_market_id, Side.NO, "0.50", now)
                )
        return books

    async def health(self) -> ExchangeHealth:
        return ExchangeHealth(exchange=Exchange.POLYMARKET, ok=True, message="test")


def _pm_market() -> Market:
    return Market(
        exchange=Exchange.POLYMARKET,
        exchange_market_id="pm-cpi",
        title="Will CPI be above 3% on July 20?",
        status="active",
        same_market_key="auto-cpi",
        outcomes=[
            Outcome(id="pm-cpi:yes", name="Yes", side=Side.YES),
            Outcome(id="pm-cpi:no", name="No", side=Side.NO),
        ],
        raw={
            "description": "Official CPI release above 3%",
            "resolutionSource": "BLS",
            "endDate": "2026-07-20T12:00:00Z",
            "resolutionDate": "2026-07-21T12:00:00Z",
        },
    )


def _kalshi_market() -> Market:
    return Market(
        exchange=Exchange.KALSHI,
        exchange_market_id="KXCPI",
        title="Will CPI be over 4% on July 20?",
        status="active",
        same_market_key="auto-cpi",
        outcomes=[
            Outcome(id="KXCPI:yes", name="Yes", side=Side.YES),
            Outcome(id="KXCPI:no", name="No", side=Side.NO),
        ],
        raw={
            "rules_primary": "Official CPI release over 4%",
            "source": "BLS",
            "close_time": "2026-07-20T12:00:00Z",
            "settlement_time": "2026-07-21T12:00:00Z",
        },
    )


def _book(
    exchange: Exchange,
    market_id: str,
    side: Side,
    price: str,
    fetched_at: datetime,
) -> OrderBook:
    return OrderBook(
        exchange=exchange,
        market_id=market_id,
        outcome_id=f"{market_id}:{side.value}",
        side=side,
        asks=[PriceLevel(price=Decimal(price), quantity=Decimal("10"), source_side="ask")],
        fetched_at=fetched_at,
    )
