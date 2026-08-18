from __future__ import annotations

import asyncio
import math
import pickle
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from statistics import mean
from typing import Any, Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Settings
from app.exchanges.base import ExchangeAdapter
from app.exchanges.kalshi import KalshiAdapter
from app.exchanges.polymarket import PolymarketAdapter
from app.models.domain import (
    Exchange,
    Market,
    MarketCategory,
    ModelOpportunity,
    ModelPaperTrade,
    ModelStatus,
    ModelTrainingRequest,
    OrderBook,
    PredictionModelSummary,
    PredictionResult,
    Side,
)
from app.persistence.database import (
    HistoricalTrainingSnapshotRecord,
    ModelOpportunityRecord,
    ModelPaperTradeRecord,
    ModelPredictionRecord,
    PredictionModelRecord,
)

try:  # pragma: no cover - import availability is verified by integration tests.
    from sklearn.ensemble import HistGradientBoostingClassifier  # type: ignore[import-untyped]
    from sklearn.isotonic import IsotonicRegression  # type: ignore[import-untyped]
    from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
    from sklearn.metrics import log_loss, roc_auc_score  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    HistGradientBoostingClassifier = None
    IsotonicRegression = None
    LogisticRegression = None
    log_loss = None
    roc_auc_score = None


FEATURE_SCHEMA_VERSION = "phase3.v1"
CALIBRATION_VERSION = "phase3.calibration.v1"
MIN_STACKER_VALIDATION_ROWS = 8

FEATURE_NAMES = [
    "time_remaining_seconds",
    "current_best_bid",
    "current_best_ask",
    "midpoint",
    "spread",
    "last_traded_price",
    "price_return_1m",
    "price_return_5m",
    "price_return_15m",
    "price_return_1h",
    "price_return_6h",
    "price_return_24h",
    "price_return_7d",
    "price_momentum",
    "price_volatility",
    "trading_volume",
    "volume_acceleration",
    "order_book_imbalance",
    "bid_depth",
    "ask_depth",
    "liquidity",
    "cross_platform_equivalent_price",
    "cross_platform_disagreement",
    "related_market_probability",
    "market_age_seconds",
    "observed_price_updates",
    "data_freshness_seconds",
    "signal_score",
    "price_change_1m",
    "log_return_1m",
    "realized_volatility_1m",
    "volume_change_1m",
    "spread_change_1m",
    "imbalance_change_1m",
    "high_low_range_1m",
    "distance_from_recent_high_1m",
    "distance_from_recent_low_1m",
    "cross_platform_divergence_1m",
    "trend_consistency_1m",
    "price_change_5m",
    "log_return_5m",
    "realized_volatility_5m",
    "volume_change_5m",
    "spread_change_5m",
    "imbalance_change_5m",
    "high_low_range_5m",
    "distance_from_recent_high_5m",
    "distance_from_recent_low_5m",
    "cross_platform_divergence_5m",
    "trend_consistency_5m",
    "price_change_15m",
    "log_return_15m",
    "realized_volatility_15m",
    "volume_change_15m",
    "spread_change_15m",
    "imbalance_change_15m",
    "high_low_range_15m",
    "distance_from_recent_high_15m",
    "distance_from_recent_low_15m",
    "cross_platform_divergence_15m",
    "trend_consistency_15m",
    "price_change_1h",
    "log_return_1h",
    "realized_volatility_1h",
    "volume_change_1h",
    "spread_change_1h",
    "imbalance_change_1h",
    "high_low_range_1h",
    "distance_from_recent_high_1h",
    "distance_from_recent_low_1h",
    "cross_platform_divergence_1h",
    "trend_consistency_1h",
    "price_change_6h",
    "log_return_6h",
    "realized_volatility_6h",
    "volume_change_6h",
    "spread_change_6h",
    "imbalance_change_6h",
    "high_low_range_6h",
    "distance_from_recent_high_6h",
    "distance_from_recent_low_6h",
    "cross_platform_divergence_6h",
    "trend_consistency_6h",
    "price_change_24h",
    "log_return_24h",
    "realized_volatility_24h",
    "volume_change_24h",
    "spread_change_24h",
    "imbalance_change_24h",
    "high_low_range_24h",
    "distance_from_recent_high_24h",
    "distance_from_recent_low_24h",
    "cross_platform_divergence_24h",
    "trend_consistency_24h",
    "price_change_7d",
    "log_return_7d",
    "realized_volatility_7d",
    "volume_change_7d",
    "spread_change_7d",
    "imbalance_change_7d",
    "high_low_range_7d",
    "distance_from_recent_high_7d",
    "distance_from_recent_low_7d",
    "cross_platform_divergence_7d",
    "trend_consistency_7d",
]


class PredictionModel(Protocol):
    def train(self, rows: list[FeatureRow]) -> None: ...

    def predict_proba(self, rows: list[FeatureRow]) -> list[float]: ...

    def save(self, path: Path) -> None: ...

    @classmethod
    def load(cls, path: Path) -> PredictionModel: ...

    @property
    def version(self) -> str: ...

    @property
    def feature_schema(self) -> list[str]: ...

    @property
    def training_metadata(self) -> dict[str, Any]: ...

    @property
    def calibration_metadata(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class FeatureRow:
    id: str
    market_id: str
    exchange: Exchange
    category: MarketCategory
    prediction_timestamp: datetime
    market_close_timestamp: datetime
    feature_timestamp: datetime
    outcome: int
    market_title: str
    features: dict[str, float]
    missing_indicators: dict[str, bool]


@dataclass(frozen=True)
class ModelSideEvaluation:
    side: Side
    probability: Decimal
    executable_price: Decimal
    executable_quantity: Decimal
    fees: Decimal
    slippage: Decimal
    uncertainty_buffer: Decimal
    gross_ev: Decimal
    net_ev: Decimal
    roi: Decimal


class SklearnBinaryModel:
    def __init__(self, model_type: str, seed: int, feature_names: list[str] | None = None) -> None:
        self.model_type = model_type
        self.seed = seed
        self._feature_names = feature_names or FEATURE_NAMES
        self.model: Any = None
        self._training_metadata: dict[str, Any] = {}
        self._calibration_metadata: dict[str, Any] = {}

    def train(self, rows: list[FeatureRow]) -> None:
        if not _has_two_classes(rows):
            self.model = None
            self._training_metadata = {"fallback": "single_class_market_baseline"}
            return
        x = _matrix(rows, self._feature_names)
        y = [row.outcome for row in rows]
        if self.model_type == "gradient_boosted":
            if HistGradientBoostingClassifier is None:
                self.model = None
                self._training_metadata = {"fallback": "sklearn_unavailable"}
                return
            self.model = HistGradientBoostingClassifier(random_state=self.seed, max_iter=80)
        else:
            if LogisticRegression is None:
                self.model = None
                self._training_metadata = {"fallback": "sklearn_unavailable"}
                return
            self.model = LogisticRegression(max_iter=500, random_state=self.seed)
        self.model.fit(x, y)
        self._training_metadata = {
            "model_type": self.model_type,
            "sample_count": len(rows),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
        }

    def predict_proba(self, rows: list[FeatureRow]) -> list[float]:
        if self.model is None:
            return [row.features["midpoint"] for row in rows]
        probabilities = self.model.predict_proba(_matrix(rows, self._feature_names))
        return _positive_class_probabilities(self.model, probabilities)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(self, handle)

    @classmethod
    def load(cls, path: Path) -> SklearnBinaryModel:
        with path.open("rb") as handle:
            loaded = pickle.load(handle)
        if not isinstance(loaded, SklearnBinaryModel):
            raise ValueError("artifact is not a SklearnBinaryModel")
        return loaded

    @property
    def version(self) -> str:
        return f"{self.model_type}:{FEATURE_SCHEMA_VERSION}"

    @property
    def feature_schema(self) -> list[str]:
        return self._feature_names

    @property
    def training_metadata(self) -> dict[str, Any]:
        return self._training_metadata

    @property
    def calibration_metadata(self) -> dict[str, Any]:
        return self._calibration_metadata


@dataclass
class CalibrationLayer:
    method: str
    version: str
    model: Any = None

    def apply(self, probabilities: list[float]) -> list[float]:
        if self.model is None:
            return [_clip_probability(value) for value in probabilities]
        if self.method == "isotonic":
            return [_clip_probability(float(value)) for value in self.model.predict(probabilities)]
        transformed = self.model.predict_proba([[value] for value in probabilities])
        positive_probabilities = _positive_class_probabilities(self.model, transformed)
        return [_clip_probability(value) for value in positive_probabilities]


class PredictionService:
    def __init__(self, settings: Settings, sessionmaker: async_sessionmaker[Any]) -> None:
        self.settings = settings
        self.sessionmaker = sessionmaker

    async def build_historical_dataset(self, data_mode: str = "test") -> dict[str, object]:
        if data_mode != "test":
            raise ValueError("fixture dataset builder is available only in DATA_MODE=test")
        rows = _fixture_feature_rows()
        async with self.sessionmaker() as session:
            inserted = 0
            for row in rows:
                if await session.get(HistoricalTrainingSnapshotRecord, row.id) is None:
                    session.add(_snapshot_record(row))
                    inserted += 1
            await session.commit()
        return {"inserted": inserted, "total_test_rows": len(rows), "source": "test"}

    async def train_model(self, request: ModelTrainingRequest) -> PredictionModelSummary:
        if request.data_mode == "test":
            await self.build_historical_dataset(request.data_mode)
        requested_category = request.category
        effective_category = request.category
        rows = await self._load_feature_rows(request.category)
        fallback_reason: str | None = None
        if (
            request.category != MarketCategory.GENERAL
            and len(rows) < self.settings.model_min_category_snapshots
        ):
            fallback_reason = "insufficient_category_snapshots"
            effective_category = MarketCategory.GENERAL
            rows = await self._load_feature_rows(MarketCategory.GENERAL)
        if len(rows) < self.settings.model_min_general_snapshots:
            fallback_reason = fallback_reason or "insufficient_general_snapshots"
            effective_category = MarketCategory.GENERAL
            rows = await self._load_feature_rows(MarketCategory.GENERAL)
        if len(rows) < self.settings.model_min_general_snapshots:
            raise ValueError("insufficient historical snapshots for model training")
        _assert_no_leakage(rows)

        train_rows, calibration_rows, final_test_rows = _grouped_chronological_train_cal_test_split(
            rows
        )
        seed = request.seed if request.seed is not None else self.settings.model_training_seed
        dataset_version = _dataset_version(rows)
        training_start = min(row.prediction_timestamp for row in rows)
        training_end = max(row.prediction_timestamp for row in rows)
        resolved_market_count = len({row.market_id for row in rows})
        training_fingerprint = _training_fingerprint(
            model_type=request.model_type,
            requested_category=requested_category,
            effective_category=effective_category,
            dataset_version=dataset_version,
            training_start=training_start,
            training_end=training_end,
            seed=seed,
            fallback_reason=fallback_reason,
        )
        existing = await self._equivalent_model(
            training_fingerprint=training_fingerprint,
            model_type=request.model_type,
            requested_category=requested_category,
            effective_category=effective_category,
            training_start=training_start,
            training_end=training_end,
            seed=seed,
            fallback_reason=fallback_reason,
            sample_count=len(rows),
        )
        if existing is not None and Path(existing.artifact_path).exists():
            return _model_summary(existing)

        logistic = SklearnBinaryModel("logistic", seed)
        logistic.train(train_rows)
        boosted = SklearnBinaryModel("gradient_boosted", seed)
        boosted.train(train_rows)

        calibration_logistic_raw = logistic.predict_proba(calibration_rows)
        calibration_boosted_raw = boosted.predict_proba(calibration_rows)
        calibration_baseline_raw = [row.features["midpoint"] for row in calibration_rows]
        calibration_component_average = [
            mean([market, logit, boosted_probability])
            for market, logit, boosted_probability in zip(
                calibration_baseline_raw,
                calibration_logistic_raw,
                calibration_boosted_raw,
                strict=True,
            )
        ]
        calibration = _fit_calibration(
            calibration_component_average,
            [row.outcome for row in calibration_rows],
        )
        final_baseline_raw = [row.features["midpoint"] for row in final_test_rows]
        final_logistic_raw = logistic.predict_proba(final_test_rows)
        final_boosted_raw = boosted.predict_proba(final_test_rows)
        final_component_average = [
            mean([market, logit, boosted_probability])
            for market, logit, boosted_probability in zip(
                final_baseline_raw,
                final_logistic_raw,
                final_boosted_raw,
                strict=True,
            )
        ]
        calibrated = calibration.apply(final_component_average)
        metrics = _validation_metrics(final_test_rows, calibrated, final_baseline_raw)
        metrics.update(
            {
                "chronological_split": "train_calibration_final_test",
                "train_sample_count": len(train_rows),
                "calibration_sample_count": len(calibration_rows),
                "final_test_sample_count": len(final_test_rows),
                "train_market_count": len({row.market_id for row in train_rows}),
                "calibration_market_count": len({row.market_id for row in calibration_rows}),
                "final_test_market_count": len({row.market_id for row in final_test_rows}),
                "market_baseline_log_loss": _safe_log_loss(
                    [row.outcome for row in final_test_rows],
                    final_baseline_raw,
                ),
            }
        )
        has_log_loss = (
            metrics.get("log_loss") is not None
            and metrics.get("market_baseline_log_loss") is not None
        )
        if has_log_loss:
            metrics["log_loss_improvement"] = (
                float(metrics["market_baseline_log_loss"]) - float(metrics["log_loss"])
            )
        calibration_table = _calibration_table(
            calibrated,
            [row.outcome for row in final_test_rows],
        )

        model_id = _stable_id("model", training_fingerprint)
        if await self._model_id_exists(model_id):
            model_id = _stable_id("model", training_fingerprint, datetime.now(UTC).isoformat())
        artifact_path = Path(self.settings.model_registry_dir) / f"{model_id}.pkl"
        artifact = {
            "logistic": logistic,
            "gradient_boosted": boosted,
            "calibration": calibration,
            "feature_names": FEATURE_NAMES,
            "stacker": "regularized_logistic_fallback_average"
            if len(calibration_rows) < MIN_STACKER_VALIDATION_ROWS
            else "held_out_component_average",
            "fallback_weights": {
                "market": 1 / 3,
                "logistic": 1 / 3,
                "gradient_boosted": 1 / 3,
            },
        }
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with artifact_path.open("wb") as handle:
            pickle.dump(artifact, handle)
        artifact_hash = _file_sha256(artifact_path)

        summary = PredictionModelSummary(
            id=model_id,
            name="phase3_market_anchored_ensemble",
            category=effective_category,
            version=f"phase3-{model_id}",
            status=ModelStatus.CANDIDATE,
            model_type=request.model_type,
            training_timestamp=datetime.now(UTC),
            training_sample_count=len(rows),
            validation_metrics=metrics,
            calibration_method=calibration.method,
            calibration_metrics={
                "calibration_table": calibration_table,
                "calibration_error": metrics["calibration_error"],
                "calibration_version": CALIBRATION_VERSION,
            },
            artifact_path=str(artifact_path),
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            training_fingerprint=training_fingerprint,
            artifact_hash=artifact_hash,
            dataset_version=dataset_version,
            training_start=training_start,
            training_end=training_end,
            resolved_market_count=resolved_market_count,
                    validation_sample_count=len(final_test_rows),
            baseline_score=Decimal(str(metrics["market_baseline_brier_score"])),
            model_score=Decimal(str(metrics["brier_score"])),
        )
        async with self.sessionmaker() as session:
            duplicate = await self._equivalent_model(
                training_fingerprint=training_fingerprint,
                model_type=request.model_type,
                requested_category=requested_category,
                effective_category=effective_category,
                training_start=training_start,
                training_end=training_end,
                seed=seed,
                fallback_reason=fallback_reason,
                sample_count=len(rows),
            )
            if duplicate is not None:
                return _model_summary(duplicate)
            session.add(
                PredictionModelRecord(
                    id=summary.id,
                    name=summary.name,
                    category=summary.category.value,
                    version=summary.version,
                    status=summary.status.value,
                    model_type=summary.model_type,
                    training_timestamp=summary.training_timestamp,
                    training_start=training_start,
                    training_end=training_end,
                    feature_schema_version=summary.feature_schema_version,
                    training_sample_count=summary.training_sample_count,
                    validation_metrics=summary.validation_metrics,
                    calibration_method=summary.calibration_method,
                    calibration_metrics=summary.calibration_metrics,
                    artifact_path=summary.artifact_path,
                    source_identifier=_source_identifier(),
                    training_fingerprint=summary.training_fingerprint,
                    artifact_hash=summary.artifact_hash,
                    dataset_version=summary.dataset_version,
                    resolved_market_count=summary.resolved_market_count,
                    validation_sample_count=summary.validation_sample_count,
                    baseline_score=summary.baseline_score,
                    model_score=summary.model_score,
                    metadata_payload={
                        "seed": seed,
                        "training_fingerprint": training_fingerprint,
                        "artifact_hash": artifact_hash,
                        "dataset_version": dataset_version,
                        "requested_category": requested_category.value,
                        "effective_category": effective_category.value,
                        "fallback_reason": fallback_reason,
                        "hyperparameters": _training_hyperparameters(request.model_type, seed),
                        "calibration_settings": _calibration_settings(),
                        "feature_names": FEATURE_NAMES,
                        "train_market_ids": sorted({row.market_id for row in train_rows}),
                        "calibration_market_ids": sorted(
                            {row.market_id for row in calibration_rows}
                        ),
                        "validation_market_ids": sorted(
                            {row.market_id for row in final_test_rows}
                        ),
                        "final_test_market_ids": sorted(
                            {row.market_id for row in final_test_rows}
                        ),
                        "resolved_market_count": resolved_market_count,
                        "calibration_sample_count": len(calibration_rows),
                        "validation_sample_count": len(final_test_rows),
                        "final_test_sample_count": len(final_test_rows),
                        "baseline_score": metrics["market_baseline_brier_score"],
                        "model_score": metrics["brier_score"],
                        "no_row_level_random_split": True,
                        "float_boundary": "scikit-learn training and inference only",
                    },
                )
            )
            await session.commit()
        return summary

    async def _equivalent_model(
        self,
        *,
        training_fingerprint: str,
        model_type: str,
        requested_category: MarketCategory,
        effective_category: MarketCategory,
        training_start: datetime,
        training_end: datetime,
        seed: int,
        fallback_reason: str | None,
        sample_count: int,
    ) -> PredictionModelRecord | None:
        async with self.sessionmaker() as session:
            records = list(
                (
                    await session.execute(
                        select(PredictionModelRecord).order_by(
                            PredictionModelRecord.training_timestamp.desc()
                        )
                    )
                ).scalars()
            )
        for record in records:
            if record.status == ModelStatus.RETIRED.value:
                continue
            if _record_training_fingerprint(record) == training_fingerprint:
                return cast(PredictionModelRecord, record)
            if _legacy_record_matches_training(
                record,
                model_type=model_type,
                requested_category=requested_category,
                effective_category=effective_category,
                training_start=training_start,
                training_end=training_end,
                seed=seed,
                fallback_reason=fallback_reason,
                sample_count=sample_count,
            ):
                return cast(PredictionModelRecord, record)
        return None

    async def _model_id_exists(self, model_id: str) -> bool:
        async with self.sessionmaker() as session:
            return await session.get(PredictionModelRecord, model_id) is not None

    async def list_models(self) -> list[PredictionModelSummary]:
        async with self.sessionmaker() as session:
            records = list(
                (
                    await session.execute(
                        select(PredictionModelRecord).order_by(
                            PredictionModelRecord.training_timestamp.desc()
                        )
                    )
                ).scalars()
            )
        return [_model_summary(record) for record in records]

    async def get_model(self, model_id: str) -> PredictionModelSummary | None:
        async with self.sessionmaker() as session:
            record = await session.get(PredictionModelRecord, model_id)
        return _model_summary(record) if record else None

    async def update_model_status(
        self,
        model_id: str,
        status: ModelStatus,
    ) -> PredictionModelSummary | None:
        async with self.sessionmaker() as session:
            record = await session.get(PredictionModelRecord, model_id)
            if record is None:
                return None
            if (
                record.status == ModelStatus.RETIRED.value
                and status == ModelStatus.APPROVED_FOR_PAPER
            ):
                raise ValueError("retired models cannot be approved for paper trading")
            if status == ModelStatus.APPROVED_FOR_PAPER:
                reasons = _model_approval_rejection_reasons(record, self.settings)
                if reasons:
                    raise ValueError(
                        "model does not meet paper-trading approval thresholds: "
                        + ", ".join(reasons)
                    )
            record.status = status.value
            await session.commit()
            await session.refresh(record)
        return _model_summary(record)

    async def generate_predictions(self, data_mode: str = "live") -> list[PredictionResult]:
        model_record = await self._research_model()
        if model_record is None:
            return []
        artifact = _load_artifact(model_record.artifact_path, self.settings)
        rows = (
            _current_fixture_rows()
            if data_mode == "test"
            else await self._current_live_rows()
        )
        return await self._generate_predictions_from_rows(rows, model_record, artifact)

    async def _generate_predictions_from_rows(
        self,
        rows: list[FeatureRow],
        model_record: PredictionModelRecord,
        artifact: dict[str, Any],
    ) -> list[PredictionResult]:
        predictions: list[PredictionResult] = []
        for row in rows:
            predictions.append(_predict_row(row, model_record, artifact, self.settings))
        await self._persist_predictions(predictions)
        return predictions

    async def predictions(
        self,
        limit: int = 100,
        data_mode: str = "live",
    ) -> list[PredictionResult]:
        now = datetime.now(UTC)
        async with self.sessionmaker() as session:
            records = list(
                (
                    await session.execute(
                        select(ModelPredictionRecord)
                        .order_by(ModelPredictionRecord.prediction_timestamp.desc())
                        .limit(limit)
                    )
                ).scalars()
            )
        return [
            prediction
            for prediction in (
                PredictionResult.model_validate(record.payload) for record in records
            )
            if _prediction_data_source(prediction) == data_mode
            and (
                data_mode != "live"
                or _prediction_is_current(prediction, now, self.settings)
            )
        ]

    async def prediction(self, prediction_id: str) -> PredictionResult | None:
        async with self.sessionmaker() as session:
            record = await session.get(ModelPredictionRecord, prediction_id)
        return PredictionResult.model_validate(record.payload) if record else None

    async def detect_model_opportunities(
        self,
        data_mode: str = "live",
    ) -> list[ModelOpportunity]:
        current_rows = (
            _current_fixture_rows()
            if data_mode == "test"
            else await self._current_live_rows()
        )
        model_record = await self._research_model()
        if model_record is None:
            return []
        artifact = _load_artifact(model_record.artifact_path, self.settings)
        predictions = await self._generate_predictions_from_rows(
            current_rows,
            model_record,
            artifact,
        )
        rows = {row.market_id: row for row in current_rows}
        opportunities = [
            _opportunity_from_prediction(prediction, rows[prediction.market_id], self.settings)
            for prediction in predictions
            if prediction.market_id in rows
        ]
        opportunities = [
            opportunity for opportunity in opportunities if not opportunity.no_trade_reasons
        ]
        await self._persist_opportunities(opportunities)
        return opportunities

    async def model_opportunities(self, data_mode: str = "live") -> list[ModelOpportunity]:
        now = datetime.now(UTC)
        async with self.sessionmaker() as session:
            records = list(
                (
                    await session.execute(
                        select(ModelOpportunityRecord).order_by(
                            ModelOpportunityRecord.detected_at.desc()
                        )
                    )
                ).scalars()
            )
        return [
            opportunity
            for opportunity in (
                ModelOpportunity.model_validate(record.payload) for record in records
            )
            if _model_opportunity_data_source(opportunity) == data_mode
            and (
                data_mode != "live"
                or _model_opportunity_is_current(opportunity, now, self.settings)
            )
        ]

    async def create_model_paper_trades(
        self,
        data_mode: str = "live",
    ) -> list[ModelPaperTrade]:
        if not self.settings.model_paper_trading_enabled:
            raise ValueError(
                "MODEL PAPER TRADING PAUSED. "
                f"{self.settings.model_paper_trading_freeze_reason}. "
                "Predictions and model opportunities remain research-only until "
                "manual audit approval."
            )
        opportunities = await self.detect_model_opportunities(data_mode)
        existing_open = await self.model_paper_trades(data_mode=data_mode)
        if len([trade for trade in existing_open if trade.status == "open"]) >= (
            self.settings.model_max_open_positions
        ):
            return []
        trades = [
            _paper_trade_from_opportunity(opportunity, self.settings)
            for opportunity in opportunities
        ]
        await self._persist_paper_trades(trades)
        return trades

    async def _current_live_rows(self) -> list[FeatureRow]:
        live_settings = self.settings.model_copy(
            update={"data_mode": "live", "use_fixtures": False}
        )
        adapters = [PolymarketAdapter(live_settings), KalshiAdapter(live_settings)]
        markets: list[Market] = []
        books: list[OrderBook] = []
        results = await asyncio.gather(
            *(self._fetch_live_adapter_rows(adapter) for adapter in adapters),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                continue
            adapter_markets, adapter_books = result
            markets.extend(adapter_markets)
            books.extend(adapter_books)
        now = datetime.now(UTC)
        return _live_feature_rows(markets, books, now, live_settings)

    async def _fetch_live_adapter_rows(
        self,
        adapter: ExchangeAdapter,
    ) -> tuple[list[Market], list[OrderBook]]:
        adapter_markets = await adapter.fetch_active_markets()
        limit = max(self.settings.model_live_market_limit, 0)
        if limit:
            adapter_markets = adapter_markets[:limit]
        return adapter_markets, await adapter.fetch_order_books(adapter_markets)

    async def model_paper_trades(
        self,
        limit: int = 100,
        data_mode: str = "live",
    ) -> list[ModelPaperTrade]:
        async with self.sessionmaker() as session:
            records = list(
                (
                    await session.execute(
                        select(ModelPaperTradeRecord)
                        .order_by(ModelPaperTradeRecord.created_at.desc())
                        .limit(limit)
                    )
                ).scalars()
            )
        return [
            trade
            for trade in (
                ModelPaperTrade.model_validate(record.payload) for record in records
            )
            if _model_trade_data_source(trade) == data_mode
        ]

    async def analytics(self, data_mode: str = "live") -> dict[str, object]:
        async with self.sessionmaker() as session:
            prediction_records = list(
                (await session.execute(select(ModelPredictionRecord))).scalars()
            )
            opportunity_records = list(
                (await session.execute(select(ModelOpportunityRecord))).scalars()
            )
            trade_records = list((await session.execute(select(ModelPaperTradeRecord))).scalars())
        predictions = [
            prediction
            for prediction in (
                PredictionResult.model_validate(record.payload) for record in prediction_records
            )
            if _prediction_data_source(prediction) == data_mode
        ]
        trades = [
            trade
            for trade in (
                ModelPaperTrade.model_validate(record.payload)
                for record in trade_records
            )
            if _model_trade_data_source(trade) == data_mode
        ]
        opportunities = [
            opportunity
            for opportunity in (
                ModelOpportunity.model_validate(record.payload) for record in opportunity_records
            )
            if _model_opportunity_data_source(opportunity) == data_mode
        ]
        buckets = Counter(
            _probability_bucket(prediction.fair_probability) for prediction in predictions
        )
        by_category = Counter(prediction.category.value for prediction in predictions)
        pnl = [trade.realized_pnl + trade.mark_to_market_pnl for trade in trades]
        return {
            "label": "MODEL PAPER TRADE",
            "model_paper_trading_paused": not self.settings.model_paper_trading_enabled,
            "model_paper_trading_freeze_enabled_at": (
                self.settings.model_paper_trading_freeze_enabled_at
                if not self.settings.model_paper_trading_enabled
                else None
            ),
            "model_paper_trading_freeze_reason": (
                self.settings.model_paper_trading_freeze_reason
                if not self.settings.model_paper_trading_enabled
                else None
            ),
            "prediction_count": len(predictions),
            "model_opportunity_count": len(opportunities),
            "model_paper_trade_count": len(trades),
            "resolved_model_paper_trade_count": len(
                [trade for trade in trades if trade.status == "closed"]
            ),
            "open_model_paper_trade_count": len(
                [trade for trade in trades if trade.status == "open"]
            ),
            "predictions_by_probability_bucket": dict(sorted(buckets.items())),
            "results_by_category": dict(sorted(by_category.items())),
            "cumulative_model_paper_pnl": sum(pnl, Decimal("0")),
            "return_on_deployed_paper_capital": _return_on_capital(trades),
            "win_rate": _win_rate(trades),
            "resolved_win_rate": _resolved_win_rate(trades),
            "average_edge_at_entry": _average_decimal([trade.expected_edge for trade in trades]),
            "maximum_drawdown": _maximum_drawdown(pnl),
            "sample_size_warning": len(predictions) < 30,
            "arbitrage_pnl_excluded": True,
        }

    async def dataset_readiness(self) -> dict[str, object]:
        rows = await self._load_feature_rows(MarketCategory.GENERAL)
        if not rows:
            return {
                "ready": False,
                "reason": "no_historical_training_snapshots",
                "model_paper_trading_paused": not self.settings.model_paper_trading_enabled,
            }
        _assert_no_leakage(rows)
        split = _grouped_chronological_train_cal_test_split(rows)
        train_rows, calibration_rows, final_test_rows = split
        comparison = _model_comparison(rows, train_rows, calibration_rows, final_test_rows)
        approval_requirements = _approval_requirement_summary(
            rows,
            train_rows,
            calibration_rows,
            final_test_rows,
            comparison,
            self.settings,
        )
        return {
            "ready": approval_requirements["all_passed"],
            "model_paper_trading_paused": not self.settings.model_paper_trading_enabled,
            "freeze_reason": (
                self.settings.model_paper_trading_freeze_reason
                if not self.settings.model_paper_trading_enabled
                else None
            ),
            "total_prediction_rows": len(rows),
            "unique_markets": len({row.market_id for row in rows}),
            "unique_resolved_markets": len({row.market_id for row in rows}),
            "category_distribution": dict(Counter(row.category.value for row in rows)),
            "exchange_distribution": dict(Counter(row.exchange.value for row in rows)),
            "outcome_balance": {
                "yes": sum(1 for row in rows if row.outcome == 1),
                "no": sum(1 for row in rows if row.outcome == 0),
            },
            "oldest_prediction_timestamp": min(row.prediction_timestamp for row in rows),
            "newest_prediction_timestamp": max(row.prediction_timestamp for row in rows),
            "snapshots_per_market": _snapshots_per_market_summary(rows),
            "chronological_splits": _split_summary(train_rows, calibration_rows, final_test_rows),
            "market_baseline": comparison["market_baseline"],
            "model_comparison": comparison,
            "approval_requirements": approval_requirements,
        }

    async def _load_feature_rows(self, category: MarketCategory) -> list[FeatureRow]:
        async with self.sessionmaker() as session:
            statement = select(HistoricalTrainingSnapshotRecord)
            if category != MarketCategory.GENERAL:
                statement = statement.where(
                    HistoricalTrainingSnapshotRecord.category == category.value
                )
            records = list((await session.execute(statement)).scalars())
        return [_feature_row_from_record(record) for record in records]

    async def _approved_model(self) -> PredictionModelRecord | None:
        async with self.sessionmaker() as session:
            record = (
                await session.execute(
                    select(PredictionModelRecord)
                    .where(PredictionModelRecord.status == ModelStatus.APPROVED_FOR_PAPER.value)
                    .order_by(PredictionModelRecord.training_timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        return cast(PredictionModelRecord | None, record)

    async def _research_model(self) -> PredictionModelRecord | None:
        async with self.sessionmaker() as session:
            record = (
                await session.execute(
                    select(PredictionModelRecord)
                    .where(PredictionModelRecord.status != ModelStatus.RETIRED.value)
                    .order_by(PredictionModelRecord.training_timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        return cast(PredictionModelRecord | None, record)

    async def _persist_predictions(self, predictions: list[PredictionResult]) -> None:
        async with self.sessionmaker() as session:
            for prediction in predictions:
                record = ModelPredictionRecord(
                    id=prediction.id,
                    model_id=prediction.model_id,
                    market_id=prediction.market_id,
                    exchange=prediction.exchange.value,
                    category=prediction.category.value,
                    prediction_timestamp=prediction.prediction_timestamp,
                    fair_probability=prediction.fair_probability,
                    market_probability=prediction.market_probability,
                    confidence_score=prediction.confidence_score,
                    uncertainty_score=prediction.uncertainty_score,
                    no_trade_reasons=prediction.no_trade_reasons,
                    payload=prediction.model_dump(mode="json"),
                )
                await session.merge(record)
            await session.commit()

    async def _persist_opportunities(self, opportunities: list[ModelOpportunity]) -> None:
        async with self.sessionmaker() as session:
            for opportunity in opportunities:
                record = ModelOpportunityRecord(
                    id=opportunity.id,
                    prediction_id=opportunity.prediction_id,
                    model_id=opportunity.model_id,
                    market_id=opportunity.market_id,
                    exchange=opportunity.exchange.value,
                    category=opportunity.category.value,
                    direction=opportunity.direction.value,
                    detected_at=opportunity.detected_at,
                    net_expected_value=opportunity.net_expected_value,
                    expected_roi=opportunity.expected_roi,
                    executable_quantity=opportunity.executable_quantity,
                    label=opportunity.label,
                    payload=opportunity.model_dump(mode="json"),
                )
                await session.merge(record)
            await session.commit()

    async def _persist_paper_trades(self, trades: list[ModelPaperTrade]) -> None:
        async with self.sessionmaker() as session:
            for trade in trades:
                record = ModelPaperTradeRecord(
                    id=trade.id,
                    opportunity_id=trade.opportunity_id,
                    prediction_id=trade.prediction_id,
                    model_id=trade.model_id,
                    market_id=trade.market_id,
                    exchange=trade.exchange.value,
                    category=trade.category.value,
                    direction=trade.direction.value,
                    created_at=trade.created_at,
                    status=trade.status,
                    label=trade.label,
                    requested_quantity=trade.requested_quantity,
                    filled_quantity=trade.filled_quantity,
                    entry_price=trade.entry_price,
                    position_size=trade.position_size,
                    expected_edge=trade.expected_edge,
                    mark_to_market_pnl=trade.mark_to_market_pnl,
                    realized_pnl=trade.realized_pnl,
                    exit_reason=trade.exit_reason,
                    resolved_outcome=trade.resolved_outcome.value
                    if trade.resolved_outcome is not None
                    else None,
                    resolution_timestamp=trade.resolution_timestamp,
                    last_resolution_check_timestamp=trade.last_resolution_check_timestamp,
                    settlement_value=trade.settlement_value,
                    payload=trade.model_dump(mode="json"),
                )
                await session.merge(record)
            await session.commit()


def _fixture_feature_rows() -> list[FeatureRow]:
    rows: list[FeatureRow] = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    categories = [
        MarketCategory.POLITICS,
        MarketCategory.ECONOMICS,
        MarketCategory.CRYPTO,
        MarketCategory.SPORTS,
        MarketCategory.TECHNOLOGY,
        MarketCategory.GENERAL,
    ]
    for index in range(24):
        category = categories[index % len(categories)]
        outcome = 1 if index % 4 in {0, 1} else 0
        market_id = f"phase3-historical-{index:02d}"
        close_ts = base + timedelta(days=30 + index)
        for snapshot in range(2):
            prediction_ts = close_ts - timedelta(days=7 - snapshot * 2)
            signal = Decimal("0.72") if outcome else Decimal("0.28")
            midpoint = signal - Decimal("0.08") if outcome else signal + Decimal("0.08")
            midpoint += Decimal(str((index + snapshot) % 3 - 1)) * Decimal("0.01")
            rows.append(
                _make_feature_row(
                    row_id=f"{market_id}:{snapshot}",
                    market_id=market_id,
                    exchange=Exchange.POLYMARKET if index % 2 == 0 else Exchange.KALSHI,
                    category=category,
                    prediction_timestamp=prediction_ts,
                    close_timestamp=close_ts,
                    outcome=outcome,
                    title=f"Resolved fixture market {index}",
                    midpoint=_clamp_decimal(midpoint),
                    spread=Decimal("0.04"),
                    signal_score=signal,
                    volume=Decimal(1000 + index * 15 + snapshot * 20),
                )
            )
    return rows


def _current_fixture_rows() -> list[FeatureRow]:
    now = datetime.now(UTC)
    return [
        _make_feature_row(
            row_id="phase3-current-polymarket-tech",
            market_id="TEST-MODEL-POLY-TECH",
            exchange=Exchange.POLYMARKET,
            category=MarketCategory.TECHNOLOGY,
            prediction_timestamp=now,
            close_timestamp=now + timedelta(days=14),
            outcome=0,
            title="TEST: Major AI benchmark released before quarter end",
            midpoint=Decimal("0.43"),
            spread=Decimal("0.04"),
            signal_score=Decimal("0.76"),
            volume=Decimal("2500"),
        ),
        _make_feature_row(
            row_id="phase3-current-kalshi-economics",
            market_id="TEST-MODEL-KALSHI-ECON",
            exchange=Exchange.KALSHI,
            category=MarketCategory.ECONOMICS,
            prediction_timestamp=now,
            close_timestamp=now + timedelta(days=21),
            outcome=0,
            title="TEST: Inflation print below consensus",
            midpoint=Decimal("0.57"),
            spread=Decimal("0.05"),
            signal_score=Decimal("0.36"),
            volume=Decimal("1800"),
        ),
    ]


def _live_feature_rows(
    markets: list[Market],
    books: list[OrderBook],
    prediction_timestamp: datetime,
    settings: Settings,
) -> list[FeatureRow]:
    books_by_market: dict[tuple[Exchange, str], list[OrderBook]] = defaultdict(list)
    for book in books:
        if book.is_stale(settings.orderbook_max_age_seconds, prediction_timestamp):
            continue
        books_by_market[(book.exchange, book.market_id)].append(book)

    rows: list[FeatureRow] = []
    for market in markets:
        market_books = books_by_market.get((market.exchange, market.exchange_market_id), [])
        yes_book = next((book for book in market_books if book.side == Side.YES), None)
        if yes_book is None or not yes_book.asks or not yes_book.bids:
            continue
        best_bid = max((level.price for level in yes_book.bids), default=Decimal("0"))
        best_ask = min((level.price for level in yes_book.asks), default=Decimal("0"))
        if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask or best_ask >= 1:
            continue
        bid_depth = sum((level.quantity for level in yes_book.bids), Decimal("0"))
        ask_depth = sum((level.quantity for level in yes_book.asks), Decimal("0"))
        midpoint = (best_bid + best_ask) / Decimal("2")
        spread = best_ask - best_bid
        volume = max((bid_depth + ask_depth) * Decimal("10"), Decimal("100"))
        rows.append(
            _make_feature_row(
                row_id=_stable_id(
                    "live-feature-row",
                    market.exchange.value,
                    market.exchange_market_id,
                ),
                market_id=market.exchange_market_id,
                exchange=market.exchange,
                category=_category_from_title(market.title),
                prediction_timestamp=prediction_timestamp,
                close_timestamp=prediction_timestamp + timedelta(days=7),
                outcome=0,
                title=f"LIVE: {market.title}",
                midpoint=midpoint,
                spread=spread,
                signal_score=midpoint,
                volume=volume,
            )
        )
        row = rows[-1]
        row.features["current_best_bid"] = float(best_bid)
        row.features["current_best_ask"] = float(best_ask)
        row.features["midpoint"] = float(midpoint)
        row.features["spread"] = float(spread)
        row.features["last_traded_price"] = float(midpoint)
        row.features["price_momentum"] = 0.0
        row.features["order_book_imbalance"] = float(_book_imbalance(bid_depth, ask_depth))
        row.features["bid_depth"] = float(bid_depth)
        row.features["ask_depth"] = float(ask_depth)
        row.features["liquidity"] = float(min(bid_depth, ask_depth))
        row.features["cross_platform_equivalent_price"] = float(midpoint)
        row.features["cross_platform_disagreement"] = 0.0
        row.features["related_market_probability"] = float(midpoint)
        row.features["data_freshness_seconds"] = float(
            max(Decimal("0"), yes_book.age_seconds(prediction_timestamp))
        )
    return rows


def _book_imbalance(bid_depth: Decimal, ask_depth: Decimal) -> Decimal:
    total = bid_depth + ask_depth
    if total <= 0:
        return Decimal("0")
    return (bid_depth - ask_depth) / total


def _category_from_title(title: str) -> MarketCategory:
    normalized = title.lower()
    if any(word in normalized for word in ["election", "president", "senate", "congress"]):
        return MarketCategory.POLITICS
    if any(word in normalized for word in ["fed", "inflation", "rate", "gdp", "cpi", "silver"]):
        return MarketCategory.ECONOMICS
    if any(word in normalized for word in ["bitcoin", "ethereum", "crypto", "solana"]):
        return MarketCategory.CRYPTO
    if any(
        word in normalized
        for word in ["wins", "goals", "match", "team", "fc", "nba", "nfl", "mlb"]
    ):
        return MarketCategory.SPORTS
    if any(word in normalized for word in ["ai", "technology", "software", "tesla", "apple"]):
        return MarketCategory.TECHNOLOGY
    return MarketCategory.GENERAL


def _make_feature_row(
    row_id: str,
    market_id: str,
    exchange: Exchange,
    category: MarketCategory,
    prediction_timestamp: datetime,
    close_timestamp: datetime,
    outcome: int,
    title: str,
    midpoint: Decimal,
    spread: Decimal,
    signal_score: Decimal,
    volume: Decimal,
) -> FeatureRow:
    best_bid = _clamp_decimal(midpoint - spread / Decimal("2"))
    best_ask = _clamp_decimal(midpoint + spread / Decimal("2"))
    time_remaining = Decimal(str((close_timestamp - prediction_timestamp).total_seconds()))
    features: dict[str, float] = {
        "time_remaining_seconds": float(time_remaining),
        "current_best_bid": float(best_bid),
        "current_best_ask": float(best_ask),
        "midpoint": float(midpoint),
        "spread": float(spread),
        "last_traded_price": float(midpoint - Decimal("0.01")),
        "price_momentum": float(signal_score - midpoint),
        "price_volatility": 0.035,
        "trading_volume": float(volume),
        "volume_acceleration": 0.08,
        "order_book_imbalance": float(signal_score - Decimal("0.5")),
        "bid_depth": float(volume / Decimal("20")),
        "ask_depth": float(volume / Decimal("25")),
        "liquidity": float(volume / Decimal("10")),
        "cross_platform_equivalent_price": float(_clamp_decimal(midpoint + Decimal("0.03"))),
        "cross_platform_disagreement": 0.03,
        "related_market_probability": float(signal_score),
        "market_age_seconds": 86400.0 * 3,
        "observed_price_updates": 12.0,
        "data_freshness_seconds": 2.0,
        "signal_score": float(signal_score),
    }
    for window, multiplier in [
        ("1m", Decimal("0.10")),
        ("5m", Decimal("0.20")),
        ("15m", Decimal("0.30")),
        ("1h", Decimal("0.45")),
        ("6h", Decimal("0.60")),
        ("24h", Decimal("0.80")),
        ("7d", Decimal("1.00")),
    ]:
        change = (signal_score - midpoint) * multiplier
        features[f"price_return_{window}"] = float(change)
        features[f"price_change_{window}"] = float(change)
        features[f"log_return_{window}"] = float(_safe_log_return(midpoint, midpoint + change))
        features[f"realized_volatility_{window}"] = float(abs(change) + Decimal("0.01"))
        features[f"volume_change_{window}"] = float(volume * multiplier / Decimal("1000"))
        features[f"spread_change_{window}"] = float(spread * multiplier / Decimal("10"))
        features[f"imbalance_change_{window}"] = float((signal_score - Decimal("0.5")) * multiplier)
        features[f"high_low_range_{window}"] = float(abs(change) + spread)
        features[f"distance_from_recent_high_{window}"] = float(
            max(Decimal("0"), signal_score - midpoint)
        )
        features[f"distance_from_recent_low_{window}"] = float(
            max(Decimal("0"), midpoint - signal_score)
        )
        features[f"cross_platform_divergence_{window}"] = float(Decimal("0.03") * multiplier)
        features[f"trend_consistency_{window}"] = 1.0 if change > 0 else -1.0
    missing = {f"{name}_missing": name not in features for name in FEATURE_NAMES}
    for name in FEATURE_NAMES:
        features.setdefault(name, 0.0)
    return FeatureRow(
        id=row_id,
        market_id=market_id,
        exchange=exchange,
        category=category,
        prediction_timestamp=prediction_timestamp,
        market_close_timestamp=close_timestamp,
        feature_timestamp=prediction_timestamp,
        outcome=outcome,
        market_title=title,
        features=features,
        missing_indicators=missing,
    )


def _snapshot_record(row: FeatureRow) -> HistoricalTrainingSnapshotRecord:
    return HistoricalTrainingSnapshotRecord(
        id=row.id,
        market_id=row.market_id,
        exchange=row.exchange.value,
        category=row.category.value,
        prediction_timestamp=row.prediction_timestamp,
        market_close_timestamp=row.market_close_timestamp,
        feature_timestamp=row.feature_timestamp,
        resolution_outcome=row.outcome,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        features=row.features,
        missing_indicators=row.missing_indicators,
        payload={
            "market_title": row.market_title,
            "leakage_guard": "features contain no resolution_outcome",
        },
    )


def _feature_row_from_record(record: HistoricalTrainingSnapshotRecord) -> FeatureRow:
    return FeatureRow(
        id=record.id,
        market_id=record.market_id,
        exchange=Exchange(record.exchange),
        category=MarketCategory(record.category),
        prediction_timestamp=record.prediction_timestamp,
        market_close_timestamp=record.market_close_timestamp,
        feature_timestamp=record.feature_timestamp,
        outcome=record.resolution_outcome,
        market_title=str(record.payload.get("market_title", record.market_id)),
        features={key: float(value) for key, value in record.features.items()},
        missing_indicators={key: bool(value) for key, value in record.missing_indicators.items()},
    )


def _assert_no_leakage(rows: list[FeatureRow]) -> None:
    for row in rows:
        if row.feature_timestamp > row.prediction_timestamp:
            raise ValueError("feature timestamp exceeds prediction timestamp")
        if row.market_close_timestamp <= row.prediction_timestamp:
            raise ValueError("market close data cannot enter earlier prediction snapshots")
        forbidden = {"resolution_outcome", "outcome", "settlement", "resolved"}
        if forbidden.intersection(row.features):
            raise ValueError("resolution outcome leaked into features")


def _grouped_chronological_split(
    rows: list[FeatureRow],
) -> tuple[list[FeatureRow], list[FeatureRow]]:
    train_rows, calibration_rows, final_test_rows = _grouped_chronological_train_cal_test_split(
        rows
    )
    return train_rows + calibration_rows, final_test_rows


def _grouped_chronological_train_cal_test_split(
    rows: list[FeatureRow],
) -> tuple[list[FeatureRow], list[FeatureRow], list[FeatureRow]]:
    markets: dict[str, list[FeatureRow]] = defaultdict(list)
    for row in sorted(rows, key=lambda item: item.market_close_timestamp):
        markets[row.market_id].append(row)
    market_ids = list(markets)
    if len(market_ids) < 3:
        raise ValueError("at least three resolved markets are required for grouped splits")
    train_end = max(1, int(len(market_ids) * 0.6))
    calibration_end = max(train_end + 1, int(len(market_ids) * 0.8))
    if calibration_end >= len(market_ids):
        calibration_end = len(market_ids) - 1
    train_ids = set(market_ids[:train_end])
    calibration_ids = set(market_ids[train_end:calibration_end])
    final_test_ids = set(market_ids[calibration_end:])
    if not train_ids or not calibration_ids or not final_test_ids:
        raise ValueError("train, calibration, and final test splits must be non-empty")
    if train_ids.intersection(calibration_ids | final_test_ids) or calibration_ids.intersection(
        final_test_ids
    ):
        raise ValueError("same-market snapshots crossed dataset splits")
    return (
        [row for market_id in train_ids for row in markets[market_id]],
        [row for market_id in calibration_ids for row in markets[market_id]],
        [row for market_id in final_test_ids for row in markets[market_id]],
    )


def _matrix(rows: list[FeatureRow], feature_names: list[str]) -> list[list[float]]:
    return [[float(row.features.get(feature, 0.0)) for feature in feature_names] for row in rows]


def _has_two_classes(rows: list[FeatureRow]) -> bool:
    return len({row.outcome for row in rows}) == 2


def _fit_calibration(probabilities: list[float], outcomes: list[int]) -> CalibrationLayer:
    if len(probabilities) >= 40 and IsotonicRegression is not None and len(set(outcomes)) == 2:
        model = IsotonicRegression(out_of_bounds="clip")
        model.fit(probabilities, outcomes)
        return CalibrationLayer("isotonic", CALIBRATION_VERSION, model)
    if len(probabilities) >= 6 and LogisticRegression is not None and len(set(outcomes)) == 2:
        model = LogisticRegression(max_iter=200)
        model.fit([[value] for value in probabilities], outcomes)
        return CalibrationLayer("platt", CALIBRATION_VERSION, model)
    return CalibrationLayer("identity_insufficient_data", CALIBRATION_VERSION, None)


def _validation_metrics(
    rows: list[FeatureRow],
    probabilities: list[float],
    baseline: list[float],
) -> dict[str, Any]:
    outcomes = [row.outcome for row in rows]
    brier = mean(
        [(prob - outcome) ** 2 for prob, outcome in zip(probabilities, outcomes, strict=True)]
    )
    baseline_brier = mean(
        [(prob - outcome) ** 2 for prob, outcome in zip(baseline, outcomes, strict=True)]
    )
    metrics: dict[str, Any] = {
        "brier_score": brier,
        "market_baseline_brier_score": baseline_brier,
        "calibration_error": _calibration_error(probabilities, outcomes),
        "accuracy": mean(
            [
                (prob >= 0.5) == bool(outcome)
                for prob, outcome in zip(probabilities, outcomes, strict=True)
            ]
        ),
        "prediction_count": len(rows),
        "trade_count": 0,
        "average_predicted_edge": mean(
            [prob - market for prob, market in zip(probabilities, baseline, strict=True)]
        ),
        "realized_paper_trading_return": 0.0,
        "maximum_drawdown": 0.0,
        "category_counts": dict(Counter(row.category.value for row in rows)),
        "exchange_counts": dict(Counter(row.exchange.value for row in rows)),
        "time_aware_split": True,
        "grouped_by_market_id": True,
    }
    if log_loss is not None and len(set(outcomes)) == 2:
        metrics["log_loss"] = _safe_log_loss(outcomes, probabilities)
    if roc_auc_score is not None and len(set(outcomes)) == 2:
        metrics["roc_auc"] = float(roc_auc_score(outcomes, probabilities))
    return metrics


def _safe_log_loss(outcomes: list[int], probabilities: list[float]) -> float | None:
    if log_loss is None or len(set(outcomes)) < 2:
        return None
    return float(log_loss(outcomes, probabilities, labels=[0, 1]))


def _model_comparison(
    rows: list[FeatureRow],
    train_rows: list[FeatureRow],
    calibration_rows: list[FeatureRow],
    final_test_rows: list[FeatureRow],
) -> dict[str, Any]:
    seed = 42
    outcomes = [row.outcome for row in final_test_rows]
    market_baseline = [row.features["midpoint"] for row in final_test_rows]
    comparison: dict[str, Any] = {
        "sample_counts": {
            "total_rows": len(rows),
            "train_rows": len(train_rows),
            "calibration_rows": len(calibration_rows),
            "final_test_rows": len(final_test_rows),
            "train_markets": len({row.market_id for row in train_rows}),
            "calibration_markets": len({row.market_id for row in calibration_rows}),
            "final_test_markets": len({row.market_id for row in final_test_rows}),
        },
        "market_baseline": _model_metric_summary(final_test_rows, market_baseline),
    }
    logistic = SklearnBinaryModel("logistic", seed)
    logistic.train(train_rows)
    logistic_calibration_raw = logistic.predict_proba(calibration_rows)
    logistic_calibration = _fit_calibration(
        logistic_calibration_raw,
        [row.outcome for row in calibration_rows],
    )
    logistic_probs = logistic_calibration.apply(logistic.predict_proba(final_test_rows))
    comparison["logistic_regression"] = _model_metric_summary(final_test_rows, logistic_probs)

    boosted_result: dict[str, Any]
    if len({row.market_id for row in train_rows}) >= 30:
        boosted = SklearnBinaryModel("gradient_boosted", seed)
        boosted.train(train_rows)
        boosted_calibration_raw = boosted.predict_proba(calibration_rows)
        boosted_calibration = _fit_calibration(
            boosted_calibration_raw,
            [row.outcome for row in calibration_rows],
        )
        boosted_probs = boosted_calibration.apply(boosted.predict_proba(final_test_rows))
        boosted_result = _model_metric_summary(final_test_rows, boosted_probs)
    else:
        boosted_calibration_raw = [row.features["midpoint"] for row in calibration_rows]
        boosted_probs = market_baseline
        boosted_result = {
            "not_trained_reason": "insufficient_unique_training_markets_for_category_boosting",
            "required_unique_training_markets": 30,
            "available_unique_training_markets": len({row.market_id for row in train_rows}),
        }
    comparison["gradient_boosted"] = boosted_result

    ensemble_calibration_input = [
        mean([market, logit, boosted])
        for market, logit, boosted in zip(
            [row.features["midpoint"] for row in calibration_rows],
            logistic_calibration_raw,
            boosted_calibration_raw,
            strict=True,
        )
    ]
    ensemble_calibration = _fit_calibration(
        ensemble_calibration_input,
        [row.outcome for row in calibration_rows],
    )
    final_boosted_for_ensemble = (
        boosted_probs if len(boosted_probs) == len(final_test_rows) else market_baseline
    )
    ensemble_raw = [
        mean([market, logit, boosted])
        for market, logit, boosted in zip(
            market_baseline,
            logistic.predict_proba(final_test_rows),
            final_boosted_for_ensemble,
            strict=True,
        )
    ]
    ensemble_probs = ensemble_calibration.apply(ensemble_raw)
    comparison["calibrated_market_anchored_ensemble"] = _model_metric_summary(
        final_test_rows,
        ensemble_probs,
    )
    comparison["baseline_outcomes"] = {
        "yes": sum(1 for outcome in outcomes if outcome == 1),
        "no": sum(1 for outcome in outcomes if outcome == 0),
    }
    return comparison


def _model_metric_summary(rows: list[FeatureRow], probabilities: list[float]) -> dict[str, Any]:
    outcomes = [row.outcome for row in rows]
    brier = mean(
        [
            (probability - outcome) ** 2
            for probability, outcome in zip(probabilities, outcomes, strict=True)
        ]
    )
    return {
        "brier_score": brier,
        "log_loss": _safe_log_loss(outcomes, probabilities),
        "calibration_error": _calibration_error(probabilities, outcomes),
        "sample_count": len(rows),
        "unique_market_count": len({row.market_id for row in rows}),
        "calibration_table": _calibration_table(probabilities, outcomes),
    }


def _snapshots_per_market_summary(rows: list[FeatureRow]) -> dict[str, Any]:
    counts = Counter(row.market_id for row in rows)
    values = sorted(counts.values())
    return {
        "minimum": values[0],
        "median": values[len(values) // 2],
        "maximum": values[-1],
        "top_markets": dict(counts.most_common(10)),
    }


def _split_summary(
    train_rows: list[FeatureRow],
    calibration_rows: list[FeatureRow],
    final_test_rows: list[FeatureRow],
) -> dict[str, Any]:
    def item(rows: list[FeatureRow]) -> dict[str, Any]:
        return {
            "rows": len(rows),
            "unique_markets": len({row.market_id for row in rows}),
            "start": min(row.prediction_timestamp for row in rows),
            "end": max(row.prediction_timestamp for row in rows),
            "market_ids": sorted({row.market_id for row in rows}),
        }

    train_ids = {row.market_id for row in train_rows}
    calibration_ids = {row.market_id for row in calibration_rows}
    final_test_ids = {row.market_id for row in final_test_rows}
    return {
        "train": item(train_rows),
        "calibration": item(calibration_rows),
        "final_test": item(final_test_rows),
        "market_overlap": bool(
            train_ids.intersection(calibration_ids | final_test_ids)
            or calibration_ids.intersection(final_test_ids)
        ),
    }


def _approval_requirement_summary(
    rows: list[FeatureRow],
    train_rows: list[FeatureRow],
    calibration_rows: list[FeatureRow],
    final_test_rows: list[FeatureRow],
    comparison: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    baseline = comparison["market_baseline"]
    ensemble = comparison["calibrated_market_anchored_ensemble"]
    brier_improvement = Decimal(str(baseline["brier_score"])) - Decimal(
        str(ensemble["brier_score"])
    )
    baseline_log_loss = baseline.get("log_loss")
    model_log_loss = ensemble.get("log_loss")
    log_loss_improvement = (
        Decimal(str(baseline_log_loss)) - Decimal(str(model_log_loss))
        if baseline_log_loss is not None and model_log_loss is not None
        else None
    )
    checks: dict[str, dict[str, object]] = {
        "minimum_unique_resolved_training_markets": {
            "required": settings.model_min_approval_training_markets,
            "actual": len({row.market_id for row in rows}),
            "passed": len({row.market_id for row in rows})
            >= settings.model_min_approval_training_markets,
        },
        "minimum_unique_validation_markets": {
            "required": settings.model_min_approval_validation_markets,
            "actual": len({row.market_id for row in calibration_rows}),
            "passed": len({row.market_id for row in calibration_rows})
            >= settings.model_min_approval_validation_markets,
        },
        "minimum_unique_final_test_markets": {
            "required": settings.model_min_approval_final_test_markets,
            "actual": len({row.market_id for row in final_test_rows}),
            "passed": len({row.market_id for row in final_test_rows})
            >= settings.model_min_approval_final_test_markets,
        },
        "maximum_calibration_error": {
            "required": str(settings.model_max_approval_calibration_error),
            "actual": str(ensemble["calibration_error"]),
            "passed": Decimal(str(ensemble["calibration_error"]))
            <= settings.model_max_approval_calibration_error,
        },
        "required_brier_improvement": {
            "required": str(settings.model_required_brier_improvement),
            "actual": str(brier_improvement),
            "passed": brier_improvement >= settings.model_required_brier_improvement,
        },
        "required_log_loss_improvement": {
            "required": str(settings.model_required_log_loss_improvement),
            "actual": str(log_loss_improvement) if log_loss_improvement is not None else None,
            "passed": log_loss_improvement is not None
            and log_loss_improvement >= settings.model_required_log_loss_improvement,
        },
        "maximum_paper_drawdown": {
            "required": str(settings.model_max_approval_paper_drawdown),
            "actual": "not_available_without_valid_paper_simulation",
            "passed": False,
        },
        "minimum_paper_trade_sample_size": {
            "required": settings.model_min_approval_paper_trade_sample,
            "actual": 0,
            "passed": False,
        },
        "no_random_row_level_split": {"required": True, "actual": True, "passed": True},
    }
    return {
        "all_passed": all(bool(item["passed"]) for item in checks.values()),
        "checks": checks,
    }


def _calibration_table(probabilities: list[float], outcomes: list[int]) -> list[dict[str, Any]]:
    buckets: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for probability, outcome in zip(probabilities, outcomes, strict=True):
        buckets[_probability_bucket(Decimal(str(probability)))].append((probability, outcome))
    return [
        {
            "bucket": bucket,
            "count": len(values),
            "average_predicted_probability": mean([item[0] for item in values]),
            "actual_resolution_rate": mean([item[1] for item in values]),
            "calibration_gap": mean([item[0] for item in values])
            - mean([item[1] for item in values]),
        }
        for bucket, values in sorted(buckets.items())
    ]


def _calibration_error(probabilities: list[float], outcomes: list[int]) -> float:
    table = _calibration_table(probabilities, outcomes)
    total = sum(item["count"] for item in table)
    if total == 0:
        return 0.0
    return float(
        sum(abs(item["calibration_gap"]) * item["count"] for item in table) / total
    )


def _dataset_version(rows: list[FeatureRow]) -> str:
    payload = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "row_ids": sorted(row.id for row in rows),
        "market_ids": sorted({row.market_id for row in rows}),
        "outcomes": {row.id: row.outcome for row in sorted(rows, key=lambda item: item.id)},
    }
    return f"dataset-{_hash_payload(payload)[:24]}"


def _training_fingerprint(
    *,
    model_type: str,
    requested_category: MarketCategory,
    effective_category: MarketCategory,
    dataset_version: str,
    training_start: datetime,
    training_end: datetime,
    seed: int,
    fallback_reason: str | None,
) -> str:
    payload = {
        "model_type": model_type,
        "requested_category": requested_category.value,
        "effective_category": effective_category.value,
        "dataset_version": dataset_version,
        "training_start": _canonical_datetime(training_start),
        "training_end": _canonical_datetime(training_end),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "hyperparameters": _training_hyperparameters(model_type, seed),
        "random_seed": seed,
        "calibration_settings": _calibration_settings(),
        "source_identifier": _source_identifier(),
        "fallback_reason": fallback_reason,
    }
    return f"model-{_hash_payload(payload)}"


def _record_training_fingerprint(record: PredictionModelRecord) -> str:
    metadata = record.metadata_payload or {}
    stored = record.training_fingerprint or metadata.get("training_fingerprint")
    if isinstance(stored, str) and stored:
        return stored
    seed = _int_metadata(metadata, "seed") or 42
    requested_value = metadata.get("requested_category")
    requested_category = MarketCategory(
        requested_value
        if requested_value in {category.value for category in MarketCategory}
        else record.category
    )
    effective_category = MarketCategory(record.category)
    dataset_version = (
        record.dataset_version
        or metadata.get("dataset_version")
        or _legacy_dataset_version(record)
    )
    return _training_fingerprint(
        model_type=record.model_type,
        requested_category=requested_category,
        effective_category=effective_category,
        dataset_version=str(dataset_version),
        training_start=record.training_start,
        training_end=record.training_end,
        seed=seed,
        fallback_reason=cast(str | None, metadata.get("fallback_reason")),
    )


def _legacy_record_matches_training(
    record: PredictionModelRecord,
    *,
    model_type: str,
    requested_category: MarketCategory,
    effective_category: MarketCategory,
    training_start: datetime,
    training_end: datetime,
    seed: int,
    fallback_reason: str | None,
    sample_count: int,
) -> bool:
    metadata = record.metadata_payload or {}
    requested_value = metadata.get("requested_category")
    effective_value = metadata.get("effective_category", record.category)
    return (
        record.model_type == model_type
        and record.category == effective_category.value
        and requested_value == requested_category.value
        and effective_value == effective_category.value
        and _same_training_day(record.training_start, training_start)
        and _same_training_day(record.training_end, training_end)
        and record.feature_schema_version == FEATURE_SCHEMA_VERSION
        and record.training_sample_count == sample_count
        and (_int_metadata(metadata, "seed") or 42) == seed
        and metadata.get("fallback_reason") == fallback_reason
    )


def _same_training_day(left: datetime, right: datetime) -> bool:
    if left.tzinfo is None:
        left = left.replace(tzinfo=UTC)
    if right.tzinfo is None:
        right = right.replace(tzinfo=UTC)
    return left.astimezone(UTC).date() == right.astimezone(UTC).date()


def _legacy_dataset_version(record: PredictionModelRecord) -> str:
    metadata = record.metadata_payload or {}
    payload = {
        "feature_schema_version": record.feature_schema_version,
        "training_sample_count": record.training_sample_count,
        "training_start": _canonical_datetime(record.training_start),
        "training_end": _canonical_datetime(record.training_end),
        "train_market_ids": sorted(metadata.get("train_market_ids", [])),
        "validation_market_ids": sorted(metadata.get("validation_market_ids", [])),
    }
    return f"dataset-{_hash_payload(payload)[:24]}"


def _training_hyperparameters(model_type: str, seed: int) -> dict[str, object]:
    return {
        "requested_model_type": model_type,
        "logistic": {"max_iter": 500, "random_state": seed},
        "gradient_boosted": {"max_iter": 80, "random_state": seed},
        "stacker": {
            "fallback": "component_average_when_validation_rows_below_threshold",
            "minimum_validation_rows": MIN_STACKER_VALIDATION_ROWS,
        },
    }


def _calibration_settings() -> dict[str, object]:
    return {
        "version": CALIBRATION_VERSION,
        "small_dataset_method": "platt",
        "large_dataset_method": "isotonic",
    }


def _source_identifier() -> str:
    return "phase3_prediction_service"


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_payload(payload: object) -> str:
    return sha256(
        _json_dumps(payload).encode("utf-8")
    ).hexdigest()


def _json_dumps(payload: object) -> str:
    import json

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _canonical_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _int_metadata(metadata: dict[str, Any], key: str) -> int | None:
    value = metadata.get(key)
    return value if isinstance(value, int) else None


def _int_metric(metrics: dict[str, Any], key: str) -> int | None:
    value = metrics.get(key)
    return value if isinstance(value, int) else None


def _decimal_metric(metrics: dict[str, Any], key: str) -> Decimal | None:
    value = metrics.get(key)
    return Decimal(str(value)) if value is not None else None


def _resolved_market_count_from_metadata(metadata: dict[str, Any]) -> int | None:
    count = _int_metadata(metadata, "resolved_market_count")
    if count is not None:
        return count
    market_ids = set(metadata.get("train_market_ids", [])) | set(
        metadata.get("validation_market_ids", [])
    )
    return len(market_ids) if market_ids else None


def _model_summary(record: PredictionModelRecord) -> PredictionModelSummary:
    metrics = record.validation_metrics
    metadata = record.metadata_payload
    return PredictionModelSummary(
        id=record.id,
        name=record.name,
        category=MarketCategory(record.category),
        version=record.version,
        status=ModelStatus(record.status),
        model_type=record.model_type,
        training_timestamp=record.training_timestamp,
        training_sample_count=record.training_sample_count,
        validation_metrics=record.validation_metrics,
        calibration_method=record.calibration_method,
        calibration_metrics=record.calibration_metrics,
        artifact_path=record.artifact_path,
        feature_schema_version=record.feature_schema_version,
        training_fingerprint=_record_training_fingerprint(record),
        artifact_hash=record.artifact_hash or metadata.get("artifact_hash"),
        dataset_version=record.dataset_version or metadata.get("dataset_version"),
        training_start=record.training_start,
        training_end=record.training_end,
        resolved_market_count=record.resolved_market_count
        or _resolved_market_count_from_metadata(metadata),
        validation_sample_count=record.validation_sample_count
        or _int_metadata(metadata, "validation_sample_count")
        or _int_metric(metrics, "prediction_count"),
        baseline_score=record.baseline_score
        or _decimal_metric(metrics, "market_baseline_brier_score"),
        model_score=record.model_score or _decimal_metric(metrics, "brier_score"),
    )


def _load_artifact(path: str, settings: Settings) -> dict[str, Any]:
    registry = Path(settings.model_registry_dir).resolve()
    artifact_path = Path(path)
    if not artifact_path.is_absolute():
        artifact_path = artifact_path.resolve()
    else:
        artifact_path = artifact_path.resolve()
    if not artifact_path.is_relative_to(registry):
        raise ValueError("model artifact path is outside configured registry directory")
    if not artifact_path.exists():
        raise ValueError(f"model artifact not found: {artifact_path.name}")
    try:
        with artifact_path.open("rb") as handle:
            artifact = pickle.load(handle)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"model artifact could not be loaded: {artifact_path.name}") from exc
    if not isinstance(artifact, dict):
        raise ValueError("invalid model artifact")
    required_keys = {"logistic", "gradient_boosted", "calibration"}
    missing_keys = sorted(required_keys - set(artifact))
    if missing_keys:
        raise ValueError(f"invalid model artifact missing keys: {', '.join(missing_keys)}")
    return artifact


def _predict_row(
    row: FeatureRow,
    model_record: PredictionModelRecord,
    artifact: dict[str, Any],
    settings: Settings,
) -> PredictionResult:
    logistic = artifact["logistic"]
    boosted = artifact["gradient_boosted"]
    calibration = artifact["calibration"]
    market_probability = Decimal(str(row.features["midpoint"]))
    raw_logistic = logistic.predict_proba([row])[0]
    raw_boosted = boosted.predict_proba([row])[0]
    raw_model_probability = mean([raw_logistic, raw_boosted])
    cross_platform = Decimal(str(row.features["cross_platform_equivalent_price"]))
    ensemble_raw = mean([float(market_probability), raw_model_probability, float(cross_platform)])
    calibrated_probability = Decimal(str(calibration.apply([ensemble_raw])[0]))
    uncertainty = _uncertainty(
        row,
        calibrated_probability,
        market_probability,
        raw_logistic,
        raw_boosted,
    )
    confidence = Decimal("1") - uncertainty
    no_trade_reasons: list[str] = []
    if model_record.status != ModelStatus.APPROVED_FOR_PAPER.value:
        no_trade_reasons.append("model_not_approved_for_paper")
    if confidence < settings.model_min_confidence:
        no_trade_reasons.append("confidence_below_threshold")
    if uncertainty > settings.model_max_uncertainty:
        no_trade_reasons.append("uncertainty_above_threshold")
    if Decimal(str(row.features["spread"])) > settings.model_max_spread:
        no_trade_reasons.append("spread_too_wide")
    prediction_timestamp = datetime.now(UTC)
    return PredictionResult(
        id=_stable_id(
            "prediction",
            model_record.id,
            row.market_id,
            prediction_timestamp.isoformat(),
        ),
        model_id=model_record.id,
        market_id=row.market_id,
        exchange=row.exchange,
        category=row.category,
        market_title=row.market_title,
        fair_probability=_decimal_probability(calibrated_probability),
        raw_model_probability=_decimal_probability(Decimal(str(raw_model_probability))),
        calibrated_probability=_decimal_probability(calibrated_probability),
        market_probability=_decimal_probability(market_probability),
        cross_platform_probability=_decimal_probability(cross_platform),
        confidence_score=confidence,
        uncertainty_score=uncertainty,
        model_version=model_record.version,
        calibration_version=CALIBRATION_VERSION,
        feature_timestamp=row.feature_timestamp,
        prediction_timestamp=prediction_timestamp,
        important_features=[
            "signal_score",
            "market_probability",
            "cross_platform_disagreement",
            "liquidity",
            "spread",
        ],
        no_trade_reasons=no_trade_reasons,
        data_source="test" if row.market_title.startswith("TEST:") else "live",
        is_live_data=not row.market_title.startswith("TEST:"),
        source_timestamp=row.feature_timestamp,
        freshness_status="TEST" if row.market_title.startswith("TEST:") else "LIVE",
    )


def _opportunity_from_prediction(
    prediction: PredictionResult,
    row: FeatureRow,
    settings: Settings,
) -> ModelOpportunity:
    yes_price = Decimal(str(row.features["current_best_ask"]))
    no_price = Decimal("1") - Decimal(str(row.features["current_best_bid"]))
    yes = _model_side_evaluation(
        Side.YES,
        prediction.calibrated_probability,
        yes_price,
        Decimal(str(row.features["ask_depth"])),
        prediction,
        settings,
    )
    no = _model_side_evaluation(
        Side.NO,
        Decimal("1") - prediction.calibrated_probability,
        no_price,
        Decimal(str(row.features["bid_depth"])),
        prediction,
        settings,
    )
    selected = yes if yes.net_ev >= no.net_ev else no
    reasons = list(prediction.no_trade_reasons)
    if selected.executable_quantity <= 0:
        reasons.append("liquidity_or_position_limit_insufficient")
    if selected.net_ev < settings.model_min_expected_edge:
        reasons.append("net_expected_edge_below_threshold")
    if selected.roi < settings.model_min_expected_roi:
        reasons.append("expected_roi_below_threshold")
    if Decimal(str(row.features["data_freshness_seconds"])) > Decimal(
        str(settings.orderbook_max_age_seconds)
    ):
        reasons.append("data_stale")
    paper_execution_eligible = settings.model_paper_trading_enabled and not reasons
    return ModelOpportunity(
        id=_stable_id("model-opportunity", prediction.id, selected.side.value),
        prediction_id=prediction.id,
        model_id=prediction.model_id,
        market_id=prediction.market_id,
        exchange=prediction.exchange,
        category=prediction.category,
        market_title=prediction.market_title,
        direction=selected.side,
        executable_quantity=selected.executable_quantity,
        weighted_average_entry_price=selected.executable_price,
        gross_expected_value=selected.gross_ev,
        fees=selected.fees,
        expected_slippage=selected.slippage,
        uncertainty_buffer=selected.uncertainty_buffer,
        net_expected_value=selected.net_ev,
        expected_roi=selected.roi,
        confidence_score=prediction.confidence_score,
        uncertainty_score=prediction.uncertainty_score,
        book_freshness_seconds=Decimal(str(row.features["data_freshness_seconds"])),
        detected_at=datetime.now(UTC),
        no_trade_reasons=reasons,
        model_version=prediction.model_version,
        calibration_version=prediction.calibration_version,
        data_source=prediction.data_source,
        is_live_data=prediction.is_live_data,
        source_timestamp=prediction.source_timestamp,
        freshness_status=prediction.freshness_status,
        paper_execution_eligible=paper_execution_eligible,
        paper_execution_status=(
            "ELIGIBLE_FOR_PAPER_EXECUTION"
            if paper_execution_eligible
            else "NOT ELIGIBLE FOR PAPER EXECUTION"
        ),
        paper_execution_reason=(
            None
            if settings.model_paper_trading_enabled
            else settings.model_paper_trading_freeze_reason
        ),
    )


def _paper_trade_from_opportunity(
    opportunity: ModelOpportunity,
    settings: Settings,
) -> ModelPaperTrade:
    requested = opportunity.executable_quantity
    filled = requested
    position_size = filled * opportunity.weighted_average_entry_price
    mark_to_market = opportunity.net_expected_value * Decimal("0.25")
    return ModelPaperTrade(
        id=_stable_id("model-paper-trade", opportunity.id),
        opportunity_id=opportunity.id,
        prediction_id=opportunity.prediction_id,
        model_id=opportunity.model_id,
        market_id=opportunity.market_id,
        exchange=opportunity.exchange,
        category=opportunity.category,
        direction=opportunity.direction,
        created_at=datetime.now(UTC),
        status="open",
        requested_quantity=requested,
        filled_quantity=filled,
        entry_price=opportunity.weighted_average_entry_price,
        position_size=position_size,
        expected_edge=opportunity.net_expected_value,
        mark_to_market_pnl=mark_to_market,
        realized_pnl=Decimal("0"),
        exit_reason=None,
        model_version=opportunity.model_version,
        calibration_version=opportunity.calibration_version,
        label=(
            "LIVE-DATA MODEL PAPER TRADE"
            if opportunity.is_live_data
            else "TEST MODEL PAPER TRADE"
        ),
        data_source=opportunity.data_source,
        is_live_data=opportunity.is_live_data,
        uses_live_market_data=opportunity.is_live_data,
    )


def _position_quantity(
    prediction: PredictionResult,
    price: Decimal,
    row: FeatureRow,
    settings: Settings,
) -> Decimal:
    probability = (
        prediction.calibrated_probability
        if prediction.calibrated_probability >= Decimal("0.5")
        else Decimal("1") - prediction.calibrated_probability
    )
    liquidity_cap = Decimal(str(row.features["ask_depth"]))
    return _position_quantity_for_probability(
        probability,
        prediction.confidence_score,
        prediction.uncertainty_score,
        price,
        liquidity_cap,
        settings,
    )


def _model_side_evaluation(
    side: Side,
    probability: Decimal,
    price: Decimal,
    liquidity_cap: Decimal,
    prediction: PredictionResult,
    settings: Settings,
) -> ModelSideEvaluation:
    quantity = _position_quantity_for_probability(
        probability,
        prediction.confidence_score,
        prediction.uncertainty_score,
        price,
        liquidity_cap,
        settings,
    )
    fees = price * quantity * settings.fee_rate
    slippage = price * quantity * settings.slippage_rate
    uncertainty_buffer = prediction.uncertainty_score * Decimal("0.05") * quantity
    gross_ev = (probability - price) * quantity
    net_ev = gross_ev - fees - slippage - uncertainty_buffer
    roi = net_ev / (price * quantity) if price > 0 and quantity > 0 else Decimal("0")
    return ModelSideEvaluation(
        side,
        probability,
        price,
        quantity,
        fees,
        slippage,
        uncertainty_buffer,
        gross_ev,
        net_ev,
        roi,
    )


def _position_quantity_for_probability(
    probability: Decimal,
    confidence: Decimal,
    uncertainty: Decimal,
    price: Decimal,
    liquidity_cap: Decimal,
    settings: Settings,
) -> Decimal:
    if price <= 0 or price >= 1:
        return Decimal("0")
    probability = max(Decimal("0"), probability - uncertainty * Decimal("0.10"))
    b = (Decimal("1") - price) / price
    q = Decimal("1") - probability
    kelly = (b * probability - q) / b if b > 0 else Decimal("0")
    kelly = max(Decimal("0"), kelly) * settings.model_kelly_fraction
    cap = (
        settings.model_high_confidence_bankroll_pct
        if confidence > Decimal("0.80")
        else settings.model_max_bankroll_pct_per_trade
    )
    bankroll_amount = settings.model_bankroll * min(kelly, cap)
    return min(bankroll_amount / price, liquidity_cap).quantize(Decimal("0.0001"))


def _uncertainty(
    row: FeatureRow,
    calibrated: Decimal,
    market: Decimal,
    logistic_probability: float,
    boosted_probability: float,
) -> Decimal:
    disagreement = max(
        abs(calibrated - market),
        abs(calibrated - Decimal(str(logistic_probability))),
        abs(calibrated - Decimal(str(boosted_probability))),
    )
    spread = Decimal(str(row.features["spread"]))
    freshness = min(
        Decimal("0.20"),
        Decimal(str(row.features["data_freshness_seconds"])) / Decimal("100"),
    )
    missing_count = Decimal(sum(1 for value in row.missing_indicators.values() if value))
    missing_penalty = min(Decimal("0.20"), missing_count / Decimal("200"))
    return min(Decimal("0.95"), disagreement + spread + freshness + missing_penalty)


def _copy_columns(target: Any, source: Any) -> None:
    for column in source.__table__.columns:
        if column.name != "id":
            setattr(target, column.name, getattr(source, column.name))


def _positive_class_probabilities(model: Any, probabilities: Any) -> list[float]:
    classes = list(getattr(model, "classes_", []))
    has_negative = 0 in classes or "0" in classes
    has_positive = 1 in classes or "1" in classes
    if not has_negative:
        raise ValueError("binary model does not expose NO/negative class label 0")
    if not has_positive:
        raise ValueError("binary model does not expose YES/positive class label 1")
    if 1 in classes:
        positive_index = classes.index(1)
    else:
        positive_index = classes.index("1")
    return [float(row[positive_index]) for row in probabilities]


def _model_approval_rejection_reasons(
    record: PredictionModelRecord,
    settings: Settings,
) -> list[str]:
    metrics = record.validation_metrics or {}
    metadata = record.metadata_payload or {}
    resolved_markets = (
        record.resolved_market_count or _resolved_market_count_from_metadata(metadata) or 0
    )
    validation_rows = (
        record.validation_sample_count
        or _int_metadata(metadata, "validation_sample_count")
        or _int_metric(metrics, "prediction_count")
        or 0
    )
    validation_markets = len(set(metadata.get("validation_market_ids", [])))
    final_test_rows = _int_metadata(metadata, "final_test_sample_count") or validation_rows
    final_test_markets = len(
        set(metadata.get("final_test_market_ids", metadata.get("validation_market_ids", [])))
    )
    model_score = record.model_score or _decimal_metric(metrics, "brier_score")
    baseline_score = record.baseline_score or _decimal_metric(
        metrics,
        "market_baseline_brier_score",
    )
    model_log_loss = _decimal_metric(metrics, "log_loss")
    baseline_log_loss = _decimal_metric(metrics, "market_baseline_log_loss")
    maximum_drawdown = _decimal_metric(metrics, "maximum_drawdown")
    trade_count = _int_metric(metrics, "trade_count") or 0
    calibration_error = _decimal_metric(metrics, "calibration_error")
    reasons: list[str] = []
    if resolved_markets < settings.model_min_approval_training_markets:
        reasons.append(
            f"resolved_training_markets {resolved_markets} < "
            f"{settings.model_min_approval_training_markets}"
        )
    if validation_markets < settings.model_min_approval_validation_markets:
        reasons.append(
            f"validation_markets {validation_markets} < "
            f"{settings.model_min_approval_validation_markets}"
        )
    if validation_rows < settings.model_min_approval_validation_rows:
        reasons.append(
            f"validation_rows {validation_rows} < {settings.model_min_approval_validation_rows}"
        )
    if final_test_markets < settings.model_min_approval_final_test_markets:
        reasons.append(
            f"final_test_markets {final_test_markets} < "
            f"{settings.model_min_approval_final_test_markets}"
        )
    if final_test_rows < settings.model_min_approval_final_test_rows:
        reasons.append(
            f"final_test_rows {final_test_rows} < {settings.model_min_approval_final_test_rows}"
        )
    if calibration_error is None:
        reasons.append("calibration_error_missing")
    elif calibration_error > settings.model_max_approval_calibration_error:
        reasons.append(
            f"calibration_error {calibration_error} > "
            f"{settings.model_max_approval_calibration_error}"
        )
    if model_score is None or baseline_score is None:
        reasons.append("model_or_baseline_score_missing")
    elif baseline_score - model_score < settings.model_required_brier_improvement:
        reasons.append(
            f"brier_improvement {baseline_score - model_score} < "
            f"{settings.model_required_brier_improvement}"
        )
    if model_log_loss is None or baseline_log_loss is None:
        reasons.append("model_or_baseline_log_loss_missing")
    elif baseline_log_loss - model_log_loss < settings.model_required_log_loss_improvement:
        reasons.append(
            f"log_loss_improvement {baseline_log_loss - model_log_loss} < "
            f"{settings.model_required_log_loss_improvement}"
        )
    if maximum_drawdown is None:
        reasons.append("paper_drawdown_missing")
    elif abs(maximum_drawdown) > settings.model_max_approval_paper_drawdown:
        reasons.append(
            f"paper_drawdown {abs(maximum_drawdown)} > "
            f"{settings.model_max_approval_paper_drawdown}"
        )
    if trade_count < settings.model_min_approval_paper_trade_sample:
        reasons.append(
            f"paper_trade_sample {trade_count} < "
            f"{settings.model_min_approval_paper_trade_sample}"
        )
    return reasons


def _probability_bucket(value: Decimal) -> str:
    start = int((value * Decimal("10")).to_integral_value(rounding="ROUND_FLOOR")) * 10
    start = min(max(start, 0), 90)
    return f"{start:02d}-{start + 10:02d}"


def _legacy_source_from_values(*values: str | None) -> str | None:
    for value in values:
        if not value:
            continue
        normalized = value.lower()
        if normalized.startswith("simulation:") or normalized.startswith("test:"):
            return "test"
        if normalized.startswith("sim-") or normalized.startswith("test-"):
            return "test"
        if "simulation" in normalized or "fixture" in normalized:
            return "test"
    return None


def _prediction_data_source(prediction: PredictionResult) -> str:
    return (
        _legacy_source_from_values(prediction.market_title, prediction.market_id)
        or prediction.data_source
    )


def _prediction_is_current(
    prediction: PredictionResult,
    now: datetime,
    settings: Settings,
) -> bool:
    if prediction.freshness_status != "LIVE" or not prediction.is_live_data:
        return False
    reference_timestamp = prediction.source_timestamp or prediction.feature_timestamp
    age_seconds = Decimal(str((now - reference_timestamp).total_seconds()))
    if age_seconds < Decimal("0"):
        return False
    return age_seconds <= Decimal(settings.orderbook_max_age_seconds)


def _model_opportunity_data_source(opportunity: ModelOpportunity) -> str:
    return (
        _legacy_source_from_values(opportunity.market_title, opportunity.market_id)
        or opportunity.data_source
    )


def _model_opportunity_is_current(
    opportunity: ModelOpportunity,
    now: datetime,
    settings: Settings,
) -> bool:
    if opportunity.freshness_status != "LIVE" or not opportunity.is_live_data:
        return False
    age_seconds = Decimal(str((now - opportunity.detected_at).total_seconds()))
    if age_seconds < Decimal("0"):
        return False
    max_age = Decimal(settings.orderbook_max_age_seconds)
    return age_seconds <= max_age and opportunity.book_freshness_seconds <= max_age


def _model_trade_data_source(trade: ModelPaperTrade) -> str:
    return (
        _legacy_source_from_values(trade.label, trade.market_id, trade.opportunity_id)
        or trade.data_source
    )


def _return_on_capital(trades: list[ModelPaperTrade]) -> Decimal:
    deployed = sum((trade.position_size for trade in trades), Decimal("0"))
    if deployed <= 0:
        return Decimal("0")
    pnl = sum((trade.realized_pnl + trade.mark_to_market_pnl for trade in trades), Decimal("0"))
    return pnl / deployed


def _win_rate(trades: list[ModelPaperTrade]) -> Decimal:
    if not trades:
        return Decimal("0")
    wins = sum(1 for trade in trades if trade.realized_pnl + trade.mark_to_market_pnl > 0)
    return Decimal(wins) / Decimal(len(trades))


def _resolved_win_rate(trades: list[ModelPaperTrade]) -> Decimal:
    resolved = [trade for trade in trades if trade.status == "closed"]
    if not resolved:
        return Decimal("0")
    wins = sum(1 for trade in resolved if trade.realized_pnl > 0)
    return Decimal(wins) / Decimal(len(resolved))


def _average_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _maximum_drawdown(values: list[Decimal]) -> Decimal:
    cumulative = Decimal("0")
    peak = Decimal("0")
    max_drawdown = Decimal("0")
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
    return max_drawdown


def _stable_id(*parts: str) -> str:
    return sha256(":".join(parts).encode()).hexdigest()[:24]


def _clip_probability(value: float) -> float:
    return min(max(value, 0.001), 0.999)


def _decimal_probability(value: Decimal) -> Decimal:
    return min(max(value, Decimal("0.001")), Decimal("0.999"))


def _clamp_decimal(value: Decimal) -> Decimal:
    return min(max(value, Decimal("0.01")), Decimal("0.99"))


def _safe_log_return(start: Decimal, end: Decimal) -> Decimal:
    if start <= 0 or end <= 0:
        return Decimal("0")
    return Decimal(str(math.log(float(end / start))))
