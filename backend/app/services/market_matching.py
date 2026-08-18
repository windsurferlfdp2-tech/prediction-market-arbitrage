import re
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.domain import Exchange, Market
from app.persistence.database import MarketPairReviewRecord

ReviewStatus = Literal[
    "pending_review",
    "verified_equivalent",
    "related_not_equivalent",
    "rejected",
]

APPROVED_STATUS: ReviewStatus = "verified_equivalent"
PENDING_STATUS: ReviewStatus = "pending_review"
VALID_STATUSES: set[str] = {
    "pending_review",
    "verified_equivalent",
    "related_not_equivalent",
    "rejected",
}
LEGACY_STATUS_MAP = {
    "Pending review": "pending_review",
    "Verified equivalent": "verified_equivalent",
    "Related but not equivalent": "related_not_equivalent",
    "Rejected": "rejected",
}

STOP_WORDS = {
    "will",
    "the",
    "this",
    "that",
    "market",
    "before",
    "after",
    "above",
    "below",
    "over",
    "under",
    "yes",
    "no",
}
OPPOSITE_DIRECTIONS = {
    "above": "below",
    "over": "under",
    "greater than": "less than",
    "before": "after",
    "yes": "no",
}
INCLUSIVE_WORDS = {"at least", "at or above", "no less than", "minimum"}
EXCLUSIVE_WORDS = {"more than", "greater than", "above", "over"}
MONTH_WORDS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
}


class MarketPairReview(BaseModel):
    model_config = ConfigDict(json_encoders={Decimal: str})

    id: str
    polymarket_market_id: str
    kalshi_market_id: str
    polymarket_title: str
    kalshi_title: str
    polymarket_resolution_criteria: str
    kalshi_resolution_criteria: str
    polymarket_close_date: str | None
    kalshi_close_date: str | None
    polymarket_settlement_date: str | None
    kalshi_settlement_date: str | None
    polymarket_resolution_sources: list[str]
    kalshi_resolution_sources: list[str]
    polymarket_entities: list[str]
    kalshi_entities: list[str]
    polymarket_numbers: list[str]
    kalshi_numbers: list[str]
    similarity_score: Decimal
    mismatches: list[str]
    status: ReviewStatus
    created_at: datetime
    updated_at: datetime


class MarketPairStatusUpdate(BaseModel):
    status: ReviewStatus


class MarketMatchingService:
    def __init__(self, sessionmaker: async_sessionmaker[Any]) -> None:
        self.sessionmaker = sessionmaker

    async def generate_candidates(self, markets: list[Market]) -> list[MarketPairReview]:
        polymarket_markets = [
            market for market in markets if market.exchange == Exchange.POLYMARKET
        ]
        kalshi_markets = [market for market in markets if market.exchange == Exchange.KALSHI]
        generated = [
            _candidate(pm_market, kalshi_market)
            for pm_market in polymarket_markets
            for kalshi_market in kalshi_markets
        ]
        candidates = [
            candidate
            for candidate in generated
            if candidate.similarity_score >= Decimal("0.15")
            or bool(set(candidate.polymarket_entities) & set(candidate.kalshi_entities))
            or bool(set(candidate.polymarket_numbers) & set(candidate.kalshi_numbers))
        ]
        candidates.sort(key=lambda item: item.similarity_score, reverse=True)

        async with self.sessionmaker() as session:
            for candidate in candidates:
                existing = await session.get(MarketPairReviewRecord, candidate.id)
                if existing is None:
                    session.add(_record_from_model(candidate))
                else:
                    _update_generated_fields(existing, candidate)
            await session.commit()

        return await self._list_reviews_by_ids([candidate.id for candidate in candidates])

    async def list_reviews(
        self,
        status: str | None = None,
        *,
        include_non_live: bool = False,
    ) -> list[MarketPairReview]:
        async with self.sessionmaker() as session:
            statement = select(MarketPairReviewRecord)
            if status:
                statement = statement.where(MarketPairReviewRecord.status == status)
            records = list((await session.execute(statement)).scalars())
        return [
            _model_from_record(record)
            for record in records
            if include_non_live or not _record_is_non_live(record)
        ]

    async def update_status(self, review_id: str, status: ReviewStatus) -> MarketPairReview | None:
        if status not in VALID_STATUSES:
            raise ValueError(f"unsupported market pair status: {status}")
        async with self.sessionmaker() as session:
            record = await session.get(MarketPairReviewRecord, review_id)
            if record is None:
                return None
            record.status = status
            record.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(record)
        return _model_from_record(record)

    async def _list_reviews_by_ids(self, review_ids: list[str]) -> list[MarketPairReview]:
        if not review_ids:
            return []
        async with self.sessionmaker() as session:
            records = list(
                (
                    await session.execute(
                        select(MarketPairReviewRecord).where(
                            MarketPairReviewRecord.id.in_(review_ids)
                        )
                    )
                ).scalars()
            )
        records_by_id = {record.id: record for record in records}
        return [
            _model_from_record(records_by_id[review_id])
            for review_id in review_ids
            if review_id in records_by_id
        ]

    async def verified_same_market_keys(self) -> dict[tuple[str, str], str]:
        async with self.sessionmaker() as session:
            records = list(
                (
                    await session.execute(
                        select(MarketPairReviewRecord).where(
                            MarketPairReviewRecord.status.in_(
                                [APPROVED_STATUS, "Verified equivalent"]
                            )
                        )
                    )
                ).scalars()
            )
        mapping: dict[tuple[str, str], str] = {}
        for record in records:
            if _record_is_non_live(record):
                continue
            same_market_key = f"verified:{record.id}"
            mapping[("polymarket", record.polymarket_market_id)] = same_market_key
            mapping[("kalshi", record.kalshi_market_id)] = same_market_key
        return mapping


def apply_verified_market_pairs(
    markets: list[Market],
    verified_keys: dict[tuple[str, str], str],
) -> list[Market]:
    result: list[Market] = []
    for market in markets:
        key = verified_keys.get((market.exchange.value, market.exchange_market_id))
        result.append(market.model_copy(update={"same_market_key": key}))
    return result


def _candidate(polymarket: Market, kalshi: Market) -> MarketPairReview:
    pm_features = _features(polymarket)
    kalshi_features = _features(kalshi)
    similarity = _similarity(pm_features["tokens"], kalshi_features["tokens"])
    pm_sources = _sources(polymarket)
    kalshi_sources = _sources(kalshi)
    mismatches = _mismatches(pm_features, kalshi_features)
    mismatches.extend(_source_mismatches(pm_sources, kalshi_sources))
    now = datetime.now(UTC)
    review_id = sha256(
        f"{polymarket.exchange_market_id}:{kalshi.exchange_market_id}".encode()
    ).hexdigest()[:16]
    return MarketPairReview(
        id=review_id,
        polymarket_market_id=polymarket.exchange_market_id,
        kalshi_market_id=kalshi.exchange_market_id,
        polymarket_title=polymarket.title,
        kalshi_title=kalshi.title,
        polymarket_resolution_criteria=_resolution_criteria(polymarket),
        kalshi_resolution_criteria=_resolution_criteria(kalshi),
        polymarket_close_date=_date_field(polymarket.raw, ["endDate", "end_date", "close_time"]),
        kalshi_close_date=_date_field(kalshi.raw, ["close_time", "expiration_time", "closeTime"]),
        polymarket_settlement_date=_date_field(
            polymarket.raw,
            ["resolutionDate", "resolution_date"],
        ),
        kalshi_settlement_date=_date_field(
            kalshi.raw,
            ["settlement_timer_seconds", "settlement_time"],
        ),
        polymarket_resolution_sources=pm_sources,
        kalshi_resolution_sources=kalshi_sources,
        polymarket_entities=pm_features["entities"],
        kalshi_entities=kalshi_features["entities"],
        polymarket_numbers=pm_features["numbers"],
        kalshi_numbers=kalshi_features["numbers"],
        similarity_score=similarity,
        mismatches=mismatches,
        status=PENDING_STATUS,
        created_at=now,
        updated_at=now,
    )


def _record_is_non_live(record: MarketPairReviewRecord) -> bool:
    values = [
        record.polymarket_market_id,
        record.kalshi_market_id,
        record.polymarket_title,
        record.kalshi_title,
        record.polymarket_resolution_criteria,
        record.kalshi_resolution_criteria,
    ]
    normalized = " ".join(value.lower() for value in values if value)
    markers = ("simulation", "fixture", "mock", "demo", "synthetic", "test:")
    return (
        record.polymarket_market_id.startswith("SIM-")
        or record.kalshi_market_id.startswith("SIM-")
        or any(marker in normalized for marker in markers)
    )


def _features(market: Market) -> dict[str, list[str]]:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", market.title.lower())
        if token not in STOP_WORDS and len(token) > 1
    ]
    entities = _entities(market.title)
    numbers = re.findall(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w.])", market.title)
    dates = re.findall(
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b|\b\d{4}-\d{2}-\d{2}\b",
        market.title.lower(),
    )
    lowered = market.title.lower()
    return {
        "tokens": sorted(set(tokens)),
        "entities": entities,
        "numbers": sorted(set(numbers + dates)),
        "directions": sorted(_directions(lowered)),
        "threshold_modes": sorted(_threshold_modes(lowered)),
        "timezones": sorted(set(re.findall(r"\b(?:utc|et|est|edt|pt|pst|pdt)\b", lowered))),
    }


def _entities(title: str) -> list[str]:
    entities: list[str] = []
    current: list[str] = []
    ignored = STOP_WORDS | MONTH_WORDS
    for word in re.findall(r"\b[A-Z][A-Za-z0-9]*\b", title):
        if word.lower() in ignored:
            if current:
                entities.append(" ".join(current))
                current = []
            continue
        current.append(word)
    if current:
        entities.append(" ".join(current))
    return sorted(set(entities))


def _similarity(left: list[str], right: list[str]) -> Decimal:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return Decimal("0")
    return Decimal(len(left_set & right_set)) / Decimal(len(left_set | right_set))


def _mismatches(left: dict[str, list[str]], right: dict[str, list[str]]) -> list[str]:
    mismatches: list[str] = []
    left_entities = set(left["entities"])
    right_entities = set(right["entities"])
    left_numbers = set(left["numbers"])
    right_numbers = set(right["numbers"])
    if left_entities != right_entities:
        mismatches.append(
            "entity mismatch: "
            f"Polymarket {sorted(left_entities)} vs Kalshi {sorted(right_entities)}"
        )
    if left_numbers != right_numbers:
        mismatches.append(
            "number/date mismatch: "
            f"Polymarket {sorted(left_numbers)} vs Kalshi {sorted(right_numbers)}"
        )
    if set(left["directions"]) != set(right["directions"]):
        mismatches.append(
            "outcome direction mismatch: "
            f"Polymarket {left['directions']} vs Kalshi {right['directions']}"
        )
    if set(left["threshold_modes"]) != set(right["threshold_modes"]):
        mismatches.append(
            "inclusive/exclusive threshold mismatch: "
            f"Polymarket {left['threshold_modes']} vs Kalshi {right['threshold_modes']}"
        )
    if set(left["timezones"]) != set(right["timezones"]):
        mismatches.append(
            f"timezone mismatch: Polymarket {left['timezones']} vs Kalshi {right['timezones']}"
        )
    return mismatches


def _directions(title: str) -> set[str]:
    directions: set[str] = set()
    for left, right in OPPOSITE_DIRECTIONS.items():
        if left in title:
            directions.add(left)
        if right in title:
            directions.add(right)
    return directions


def _threshold_modes(title: str) -> set[str]:
    modes: set[str] = set()
    if any(term in title for term in INCLUSIVE_WORDS):
        modes.add("inclusive")
    if any(term in title for term in EXCLUSIVE_WORDS):
        modes.add("exclusive")
    return modes


def _source_mismatches(left: list[str], right: list[str]) -> list[str]:
    if set(left) == set(right):
        return []
    if not left and not right:
        return []
    return [f"resolution source mismatch: Polymarket {left} vs Kalshi {right}"]


def _resolution_criteria(market: Market) -> str:
    candidates = [
        market.raw.get("description"),
        market.raw.get("resolutionSource"),
        market.raw.get("rules_primary"),
        market.raw.get("title"),
        market.raw.get("question"),
    ]
    return str(next((item for item in candidates if item), market.title))


def _sources(market: Market) -> list[str]:
    values = [
        market.raw.get("resolutionSource"),
        market.raw.get("resolution_source"),
        market.raw.get("source"),
    ]
    return [str(value) for value in values if value]


def _date_field(raw: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return str(value)
    return None


def _record_from_model(model: MarketPairReview) -> MarketPairReviewRecord:
    return MarketPairReviewRecord(**model.model_dump())


def _update_generated_fields(record: MarketPairReviewRecord, model: MarketPairReview) -> None:
    record.polymarket_title = model.polymarket_title
    record.kalshi_title = model.kalshi_title
    record.polymarket_resolution_criteria = model.polymarket_resolution_criteria
    record.kalshi_resolution_criteria = model.kalshi_resolution_criteria
    record.polymarket_close_date = model.polymarket_close_date
    record.kalshi_close_date = model.kalshi_close_date
    record.polymarket_settlement_date = model.polymarket_settlement_date
    record.kalshi_settlement_date = model.kalshi_settlement_date
    record.polymarket_resolution_sources = model.polymarket_resolution_sources
    record.kalshi_resolution_sources = model.kalshi_resolution_sources
    record.polymarket_entities = model.polymarket_entities
    record.kalshi_entities = model.kalshi_entities
    record.polymarket_numbers = model.polymarket_numbers
    record.kalshi_numbers = model.kalshi_numbers
    record.similarity_score = model.similarity_score
    record.mismatches = model.mismatches
    record.updated_at = model.updated_at


def _model_from_record(record: MarketPairReviewRecord) -> MarketPairReview:
    payload = {
        column.name: getattr(record, column.name)
        for column in MarketPairReviewRecord.__table__.columns
    }
    payload["status"] = LEGACY_STATUS_MAP.get(str(payload["status"]), payload["status"])
    return MarketPairReview.model_validate(payload)
