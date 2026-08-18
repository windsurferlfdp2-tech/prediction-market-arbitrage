import pickle
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import app
from app.models.domain import (
    Exchange,
    Market,
    MarketCategory,
    ModelOpportunity,
    ModelStatus,
    ModelTrainingRequest,
    OrderBook,
    Outcome,
    PredictionResult,
    PriceLevel,
    Side,
)
from app.persistence.database import (
    AsyncSessionLocal,
    ModelOpportunityRecord,
    ModelPredictionRecord,
    PredictionModelRecord,
    SqlAlchemyDatabaseBackend,
    init_db,
)
from app.services.prediction import (
    CalibrationLayer,
    FeatureRow,
    PredictionService,
    _assert_no_leakage,
    _fixture_feature_rows,
    _grouped_chronological_split,
    _grouped_chronological_train_cal_test_split,
    _live_feature_rows,
    _load_artifact,
    _opportunity_from_prediction,
    _position_quantity,
    _positive_class_probabilities,
)


@pytest.mark.asyncio
async def test_feature_rows_have_no_future_data_or_resolution_leakage() -> None:
    rows = _fixture_feature_rows()

    _assert_no_leakage(rows)

    assert rows
    assert all(row.feature_timestamp <= row.prediction_timestamp for row in rows)
    assert all(row.market_close_timestamp > row.prediction_timestamp for row in rows)
    assert all("resolution_outcome" not in row.features for row in rows)


def test_same_market_snapshots_do_not_cross_train_validation_split() -> None:
    rows = _fixture_feature_rows()

    train, validation = _grouped_chronological_split(rows)

    train_markets = {row.market_id for row in train}
    validation_markets = {row.market_id for row in validation}
    assert train_markets
    assert validation_markets
    assert train_markets.isdisjoint(validation_markets)


def test_same_market_snapshots_do_not_cross_train_calibration_final_test_split() -> None:
    rows = _fixture_feature_rows()

    train, calibration, final_test = _grouped_chronological_train_cal_test_split(rows)

    train_markets = {row.market_id for row in train}
    calibration_markets = {row.market_id for row in calibration}
    final_test_markets = {row.market_id for row in final_test}
    assert train_markets
    assert calibration_markets
    assert final_test_markets
    assert train_markets.isdisjoint(calibration_markets)
    assert train_markets.isdisjoint(final_test_markets)
    assert calibration_markets.isdisjoint(final_test_markets)


def test_feature_timestamp_after_prediction_is_rejected() -> None:
    row = _fixture_feature_rows()[0]
    bad_row = row.__class__(
        **{
            **row.__dict__,
            "feature_timestamp": row.prediction_timestamp + timedelta(seconds=1),
        }
    )

    with pytest.raises(ValueError, match="feature timestamp"):
        _assert_no_leakage([bad_row])


def test_live_feature_rows_use_executable_order_book_prices() -> None:
    now = _fixture_feature_rows()[0].prediction_timestamp
    market = Market(
        exchange=Exchange.POLYMARKET,
        exchange_market_id="LIVE-PM-1",
        title="Will Bitcoin be above $100k?",
        status="active",
        outcomes=[
            Outcome(id="LIVE-PM-1:yes", name="Yes", side=Side.YES),
            Outcome(id="LIVE-PM-1:no", name="No", side=Side.NO),
        ],
    )
    book = OrderBook(
        exchange=Exchange.POLYMARKET,
        market_id="LIVE-PM-1",
        outcome_id="LIVE-PM-1:yes",
        side=Side.YES,
        bids=[
            PriceLevel(price=Decimal("0.41"), quantity=Decimal("50"), source_side="bid"),
            PriceLevel(price=Decimal("0.42"), quantity=Decimal("40"), source_side="bid"),
        ],
        asks=[
            PriceLevel(price=Decimal("0.45"), quantity=Decimal("25"), source_side="ask"),
            PriceLevel(price=Decimal("0.46"), quantity=Decimal("75"), source_side="ask"),
        ],
        fetched_at=now,
    )

    rows = _live_feature_rows([market], [book], now, Settings(local_development=True))

    assert len(rows) == 1
    row = rows[0]
    assert row.market_id == "LIVE-PM-1"
    assert row.category == MarketCategory.CRYPTO
    assert row.market_title.startswith("LIVE:")
    assert row.features["current_best_bid"] == 0.42
    assert row.features["current_best_ask"] == 0.45
    assert row.features["bid_depth"] == 90.0
    assert row.features["ask_depth"] == 100.0
    assert row.features["liquidity"] == 90.0


def test_live_feature_rows_do_not_report_negative_freshness() -> None:
    now = _fixture_feature_rows()[0].prediction_timestamp
    market = Market(
        exchange=Exchange.KALSHI,
        exchange_market_id="LIVE-KALSHI-1",
        title="Will a technology bill pass?",
        status="active",
        outcomes=[
            Outcome(id="LIVE-KALSHI-1:yes", name="Yes", side=Side.YES),
            Outcome(id="LIVE-KALSHI-1:no", name="No", side=Side.NO),
        ],
    )
    book = OrderBook(
        exchange=Exchange.KALSHI,
        market_id="LIVE-KALSHI-1",
        outcome_id="LIVE-KALSHI-1:yes",
        side=Side.YES,
        bids=[PriceLevel(price=Decimal("0.35"), quantity=Decimal("10"), source_side="bid")],
        asks=[PriceLevel(price=Decimal("0.40"), quantity=Decimal("10"), source_side="ask")],
        fetched_at=now + timedelta(seconds=1),
    )

    rows = _live_feature_rows([market], [book], now, Settings(local_development=True))

    assert len(rows) == 1
    assert rows[0].features["data_freshness_seconds"] == 0.0


def test_model_position_size_uses_conservative_emergency_cap() -> None:
    row = _fixture_feature_rows()[0]
    row.features["ask_depth"] = 10000.0
    prediction = PredictionResult(
        id="prediction-500-cap",
        model_id="model-500-cap",
        market_id=row.market_id,
        exchange=row.exchange,
        category=row.category,
        market_title=row.market_title,
        fair_probability=Decimal("0.95"),
        raw_model_probability=Decimal("0.95"),
        calibrated_probability=Decimal("0.95"),
        market_probability=Decimal("0.20"),
        cross_platform_probability=Decimal("0.20"),
        confidence_score=Decimal("0.90"),
        uncertainty_score=Decimal("0"),
        model_version="test",
        calibration_version="test",
        feature_timestamp=row.feature_timestamp,
        prediction_timestamp=row.prediction_timestamp,
        important_features=[],
        no_trade_reasons=[],
    )

    quantity = _position_quantity(
        prediction,
        Decimal("0.20"),
        row,
        Settings(
            local_development=True,
            model_kelly_fraction=Decimal("0.025"),
            model_max_bankroll_pct_per_trade=Decimal("0.0025"),
            model_high_confidence_bankroll_pct=Decimal("0.005"),
        ),
    )

    assert quantity == Decimal("250.0000")
    assert quantity * Decimal("0.20") == Decimal("50.00000")


def test_positive_class_probability_uses_explicit_class_order() -> None:
    class OrderedModel:
        classes_ = [0, 1]

    class ReversedModel:
        classes_ = [1, 0]

    assert _positive_class_probabilities(OrderedModel(), [[0.80, 0.20]]) == [0.20]
    assert _positive_class_probabilities(ReversedModel(), [[0.80, 0.20]]) == [0.80]


def test_positive_class_probability_supports_string_labels() -> None:
    class StringModel:
        classes_ = ["1", "0"]

    assert _positive_class_probabilities(StringModel(), [[0.70, 0.30]]) == [0.70]


def test_positive_class_probability_rejects_missing_classes() -> None:
    class MissingNoModel:
        classes_ = [1]

    class MissingYesModel:
        classes_ = [0]

    with pytest.raises(ValueError, match="negative class label 0"):
        _positive_class_probabilities(MissingNoModel(), [[1.0]])
    with pytest.raises(ValueError, match="positive class label 1"):
        _positive_class_probabilities(MissingYesModel(), [[1.0]])


def test_platt_calibration_uses_positive_class_label() -> None:
    class ReversedCalibrator:
        classes_ = [1, 0]

        def predict_proba(self, values: list[list[float]]) -> list[list[float]]:
            return [[value[0], 1 - value[0]] for value in values]

    calibration = CalibrationLayer("platt", "test", ReversedCalibrator())

    assert calibration.apply([0.73]) == [0.73]


def test_invalid_saved_artifact_missing_required_keys_fails_safely(tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifact.pkl"
    with artifact_path.open("wb") as handle:
        pickle.dump({"logistic": object()}, handle)

    with pytest.raises(ValueError, match="missing keys"):
        _load_artifact(str(artifact_path), Settings(model_registry_dir=str(tmp_path)))


def test_strong_yes_probability_creates_buy_yes() -> None:
    row = _model_decision_row(yes_ask=Decimal("0.30"), yes_bid=Decimal("0.20"))
    prediction = _prediction_for_decision(row, calibrated=Decimal("0.75"))

    opportunity = _opportunity_from_prediction(prediction, row, _decision_settings())

    assert opportunity.direction == Side.YES
    assert opportunity.net_expected_value > 0
    assert opportunity.no_trade_reasons == []


def test_strong_no_probability_creates_buy_no_using_one_minus_yes() -> None:
    row = _model_decision_row(yes_ask=Decimal("0.80"), yes_bid=Decimal("0.60"))
    prediction = _prediction_for_decision(row, calibrated=Decimal("0.20"))

    opportunity = _opportunity_from_prediction(prediction, row, _decision_settings())

    assert opportunity.direction == Side.NO
    assert opportunity.weighted_average_entry_price == Decimal("0.40")
    assert opportunity.net_expected_value > 0
    assert opportunity.no_trade_reasons == []


def test_no_trade_when_both_sides_have_negative_net_ev() -> None:
    row = _model_decision_row(yes_ask=Decimal("0.55"), yes_bid=Decimal("0.45"))
    prediction = _prediction_for_decision(row, calibrated=Decimal("0.50"))

    opportunity = _opportunity_from_prediction(prediction, row, _decision_settings())

    assert "net_expected_edge_below_threshold" in opportunity.no_trade_reasons


def test_selected_side_matches_greater_net_ev_after_costs() -> None:
    row = _model_decision_row(yes_ask=Decimal("0.50"), yes_bid=Decimal("0.80"))
    prediction = _prediction_for_decision(row, calibrated=Decimal("0.45"))

    opportunity = _opportunity_from_prediction(
        prediction,
        row,
        _decision_settings(fee_rate=Decimal("0.01"), slippage_rate=Decimal("0.01")),
    )

    assert opportunity.direction == Side.NO
    assert opportunity.weighted_average_entry_price == Decimal("0.20")


def _model_decision_row(yes_ask: Decimal, yes_bid: Decimal) -> FeatureRow:
    row = _fixture_feature_rows()[0]
    row.features["current_best_ask"] = float(yes_ask)
    row.features["current_best_bid"] = float(yes_bid)
    row.features["ask_depth"] = 1000.0
    row.features["bid_depth"] = 1000.0
    row.features["data_freshness_seconds"] = 1.0
    row.features["spread"] = float(yes_ask - yes_bid)
    return row


def _prediction_for_decision(row: FeatureRow, calibrated: Decimal) -> PredictionResult:
    return PredictionResult(
        id="decision-prediction",
        model_id="decision-model",
        market_id=row.market_id,
        exchange=row.exchange,
        category=row.category,
        market_title=row.market_title,
        fair_probability=calibrated,
        raw_model_probability=calibrated,
        calibrated_probability=calibrated,
        market_probability=Decimal(str(row.features["midpoint"])),
        cross_platform_probability=Decimal(str(row.features["cross_platform_equivalent_price"])),
        confidence_score=Decimal("0.95"),
        uncertainty_score=Decimal("0"),
        model_version="test-model",
        calibration_version="test-calibration",
        feature_timestamp=row.feature_timestamp,
        prediction_timestamp=row.prediction_timestamp,
        important_features=[],
        no_trade_reasons=[],
    )


def _decision_settings(
    fee_rate: Decimal = Decimal("0"),
    slippage_rate: Decimal = Decimal("0"),
) -> Settings:
    return Settings(
        local_development=True,
        model_paper_trading_enabled=False,
        model_kelly_fraction=Decimal("0.10"),
        model_max_bankroll_pct_per_trade=Decimal("0.10"),
        model_high_confidence_bankroll_pct=Decimal("0.10"),
        model_min_expected_edge=Decimal("0.01"),
        model_min_expected_roi=Decimal("0.01"),
        model_max_spread=Decimal("1"),
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )


@pytest.mark.asyncio
async def test_training_registers_candidate_and_manual_approval_controls_predictions() -> None:
    await init_db()
    service = PredictionService(
        Settings(
            local_development=True,
            model_min_approval_training_markets=1,
            model_min_approval_validation_markets=1,
            model_min_approval_validation_rows=1,
            model_min_approval_final_test_markets=1,
            model_min_approval_final_test_rows=1,
            model_max_approval_calibration_error=Decimal("1"),
            model_required_brier_improvement=Decimal("-1"),
            model_required_log_loss_improvement=Decimal("-1"),
            model_min_approval_paper_trade_sample=0,
        ),
        AsyncSessionLocal,
    )

    summary = await service.train_model(
        ModelTrainingRequest(category=MarketCategory.GENERAL, data_mode="test")
    )
    assert summary.status == ModelStatus.CANDIDATE
    assert summary.validation_metrics["prediction_count"] > 0
    assert summary.validation_metrics["time_aware_split"] is True
    assert summary.calibration_method in {"platt", "isotonic", "identity_insufficient_data"}

    research_predictions = await service.generate_predictions("test")
    assert research_predictions
    assert all(
        "model_not_approved_for_paper" in prediction.no_trade_reasons
        for prediction in research_predictions
    )

    approved = await service.update_model_status(summary.id, ModelStatus.APPROVED_FOR_PAPER)
    assert approved is not None
    predictions = await service.generate_predictions("test")
    assert predictions
    assert all(prediction.label == "MODEL PREDICTION" for prediction in predictions)


@pytest.mark.asyncio
async def test_undersampled_model_cannot_be_approved_for_paper(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'approval.db'}")
    await backend.init()
    settings = Settings(local_development=True, model_registry_dir=str(tmp_path / "artifacts"))
    service = PredictionService(settings, backend.sessionmaker)
    summary = await service.train_model(ModelTrainingRequest(data_mode="test"))

    with pytest.raises(ValueError, match="approval thresholds"):
        await service.update_model_status(summary.id, ModelStatus.APPROVED_FOR_PAPER)


@pytest.mark.asyncio
async def test_dataset_readiness_reports_grouped_final_test_and_baseline(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'readiness.db'}")
    await backend.init()
    service = PredictionService(
        Settings(local_development=True, model_registry_dir=str(tmp_path / "artifacts")),
        backend.sessionmaker,
    )
    await service.build_historical_dataset("test")

    readiness = await service.dataset_readiness()

    assert readiness["model_paper_trading_paused"] is True
    assert readiness["total_prediction_rows"] == 48
    assert readiness["unique_resolved_markets"] == 24
    assert readiness["outcome_balance"] == {"yes": 24, "no": 24}
    splits = cast(dict[str, object], readiness["chronological_splits"])
    baseline = cast(dict[str, object], readiness["market_baseline"])
    requirements = cast(dict[str, object], readiness["approval_requirements"])
    assert splits["market_overlap"] is False
    assert cast(int, baseline["sample_count"]) > 0
    assert cast(float, baseline["brier_score"]) >= 0
    assert requirements["all_passed"] is False


@pytest.mark.asyncio
async def test_prediction_generation_preserves_timestamped_history(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'pred-history.db'}")
    await backend.init()
    settings = Settings(
        local_development=True,
        model_registry_dir=str(tmp_path / "artifacts"),
        model_min_approval_training_markets=1,
        model_min_approval_validation_markets=1,
        model_min_approval_validation_rows=1,
        model_min_approval_final_test_markets=1,
        model_min_approval_final_test_rows=1,
        model_max_approval_calibration_error=Decimal("1"),
        model_required_brier_improvement=Decimal("-1"),
        model_required_log_loss_improvement=Decimal("-1"),
        model_min_approval_paper_trade_sample=0,
    )
    service = PredictionService(settings, backend.sessionmaker)
    summary = await service.train_model(ModelTrainingRequest(data_mode="test"))
    await service.update_model_status(summary.id, ModelStatus.APPROVED_FOR_PAPER)

    first = await service.generate_predictions("test")
    second = await service.generate_predictions("test")

    assert first
    assert second
    assert {prediction.id for prediction in first}.isdisjoint(
        {prediction.id for prediction in second}
    )
    async with backend.sessionmaker() as session:
        count = len((await session.execute(select(ModelPredictionRecord))).scalars().all())
    assert count == len(first) + len(second)


@pytest.mark.asyncio
async def test_duplicate_training_registration_returns_existing_model(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'registry.db'}")
    await backend.init()
    settings = Settings(local_development=True, model_registry_dir=str(tmp_path / "artifacts"))
    service = PredictionService(settings, backend.sessionmaker)
    request = ModelTrainingRequest(category=MarketCategory.GENERAL, data_mode="test", seed=123)

    first = await service.train_model(request)
    second = await service.train_model(request)

    assert second.id == first.id
    assert second.training_fingerprint == first.training_fingerprint
    assert second.artifact_path == first.artifact_path
    async with backend.sessionmaker() as session:
        count = len((await session.execute(select(PredictionModelRecord))).scalars().all())
    assert count == 1


@pytest.mark.asyncio
async def test_genuinely_different_training_seed_creates_new_model(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'registry-seeds.db'}")
    await backend.init()
    settings = Settings(local_development=True, model_registry_dir=str(tmp_path / "artifacts"))
    service = PredictionService(settings, backend.sessionmaker)

    first = await service.train_model(ModelTrainingRequest(data_mode="test", seed=123))
    second = await service.train_model(ModelTrainingRequest(data_mode="test", seed=456))

    assert second.id != first.id
    assert second.training_fingerprint != first.training_fingerprint


@pytest.mark.asyncio
async def test_repeated_dataset_seed_execution_is_idempotent(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'dataset.db'}")
    await backend.init()
    service = PredictionService(Settings(local_development=True), backend.sessionmaker)

    first = await service.build_historical_dataset("test")
    second = await service.build_historical_dataset("test")

    assert first["inserted"] == 48
    assert second["inserted"] == 0
    assert second["total_test_rows"] == 48


@pytest.mark.asyncio
async def test_retired_model_cannot_be_reapproved(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'retired.db'}")
    await backend.init()
    settings = Settings(local_development=True, model_registry_dir=str(tmp_path / "artifacts"))
    service = PredictionService(settings, backend.sessionmaker)
    model = await service.train_model(ModelTrainingRequest(data_mode="test"))

    await service.update_model_status(model.id, ModelStatus.RETIRED)

    with pytest.raises(ValueError, match="retired models cannot be approved"):
        await service.update_model_status(model.id, ModelStatus.APPROVED_FOR_PAPER)


@pytest.mark.asyncio
async def test_model_opportunity_and_paper_trade_are_separate_from_arbitrage_labels() -> None:
    await init_db()
    service = PredictionService(
        Settings(
            local_development=True,
            model_paper_trading_enabled=True,
            model_min_approval_training_markets=1,
            model_min_approval_validation_markets=1,
            model_min_approval_validation_rows=1,
            model_min_approval_final_test_markets=1,
            model_min_approval_final_test_rows=1,
            model_max_approval_calibration_error=Decimal("1"),
            model_required_brier_improvement=Decimal("-1"),
            model_required_log_loss_improvement=Decimal("-1"),
            model_min_approval_paper_trade_sample=0,
        ),
        AsyncSessionLocal,
    )
    summary = await service.train_model(
        ModelTrainingRequest(category=MarketCategory.GENERAL, data_mode="test")
    )
    await service.update_model_status(summary.id, ModelStatus.APPROVED_FOR_PAPER)

    opportunities = await service.detect_model_opportunities("test")
    trades = await service.create_model_paper_trades("test")
    analytics = await service.analytics("test")

    assert opportunities
    assert all(opportunity.label == "MODEL OPPORTUNITY" for opportunity in opportunities)
    assert all(opportunity.net_expected_value > Decimal("0") for opportunity in opportunities)
    assert trades
    assert all(trade.label == "TEST MODEL PAPER TRADE" for trade in trades)
    assert analytics["arbitrage_pnl_excluded"] is True
    assert cast(int, analytics["model_paper_trade_count"]) >= len(trades)


@pytest.mark.asyncio
async def test_model_paper_trade_creation_is_paused_by_default(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'freeze.db'}")
    await backend.init()
    service = PredictionService(Settings(local_development=True), backend.sessionmaker)

    with pytest.raises(ValueError, match="MODEL PAPER TRADING PAUSED"):
        await service.create_model_paper_trades("test")


@pytest.mark.asyncio
async def test_live_model_opportunities_exclude_stale_records(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'model-ops.db'}")
    await backend.init()
    settings = Settings(local_development=True, orderbook_max_age_seconds=30)
    service = PredictionService(settings, backend.sessionmaker)
    detected_at = datetime.now(UTC) - timedelta(minutes=5)
    stale = ModelOpportunity(
        id="stale-live-model-opportunity",
        prediction_id="prediction",
        model_id="model",
        market_id="market",
        exchange=Exchange.KALSHI,
        category=MarketCategory.SPORTS,
        market_title="LIVE: stale market",
        direction=Side.YES,
        executable_quantity=Decimal("10"),
        weighted_average_entry_price=Decimal("0.20"),
        gross_expected_value=Decimal("1"),
        fees=Decimal("0"),
        expected_slippage=Decimal("0"),
        uncertainty_buffer=Decimal("0"),
        net_expected_value=Decimal("1"),
        expected_roi=Decimal("0.5"),
        confidence_score=Decimal("0.8"),
        uncertainty_score=Decimal("0.1"),
        book_freshness_seconds=Decimal("1"),
        detected_at=detected_at,
        no_trade_reasons=[],
        model_version="model-v1",
        calibration_version="cal-v1",
        data_source="live",
        is_live_data=True,
        source_timestamp=detected_at,
        freshness_status="LIVE",
    )
    async with backend.sessionmaker() as session:
        session.add(
            ModelOpportunityRecord(
                id=stale.id,
                prediction_id=stale.prediction_id,
                model_id=stale.model_id,
                market_id=stale.market_id,
                exchange=stale.exchange.value,
                category=stale.category.value,
                direction=stale.direction.value,
                detected_at=stale.detected_at,
                net_expected_value=stale.net_expected_value,
                expected_roi=stale.expected_roi,
                executable_quantity=stale.executable_quantity,
                label=stale.label,
                payload=stale.model_dump(mode="json"),
            )
        )
        await session.commit()

    assert await service.model_opportunities("live") == []


@pytest.mark.asyncio
async def test_live_predictions_exclude_stale_records(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'predictions.db'}")
    await backend.init()
    settings = Settings(local_development=True, orderbook_max_age_seconds=30)
    service = PredictionService(settings, backend.sessionmaker)
    prediction_timestamp = datetime.now(UTC) - timedelta(minutes=5)
    stale = PredictionResult(
        id="stale-live-prediction",
        model_id="model",
        market_id="market",
        exchange=Exchange.KALSHI,
        category=MarketCategory.SPORTS,
        market_title="LIVE: stale prediction",
        fair_probability=Decimal("0.50"),
        raw_model_probability=Decimal("0.50"),
        calibrated_probability=Decimal("0.50"),
        market_probability=Decimal("0.50"),
        cross_platform_probability=Decimal("0.50"),
        confidence_score=Decimal("0.8"),
        uncertainty_score=Decimal("0.1"),
        model_version="model-v1",
        calibration_version="cal-v1",
        feature_timestamp=prediction_timestamp,
        prediction_timestamp=prediction_timestamp,
        important_features=[],
        no_trade_reasons=[],
        data_source="live",
        is_live_data=True,
        source_timestamp=prediction_timestamp,
        freshness_status="LIVE",
    )
    async with backend.sessionmaker() as session:
        session.add(
            ModelPredictionRecord(
                id=stale.id,
                model_id=stale.model_id,
                market_id=stale.market_id,
                exchange=stale.exchange.value,
                category=stale.category.value,
                prediction_timestamp=stale.prediction_timestamp,
                fair_probability=stale.fair_probability,
                market_probability=stale.market_probability,
                confidence_score=stale.confidence_score,
                uncertainty_score=stale.uncertainty_score,
                no_trade_reasons=stale.no_trade_reasons,
                payload=stale.model_dump(mode="json"),
            )
        )
        await session.commit()

    assert await service.predictions(data_mode="live") == []


def test_phase3_api_vertical_slice() -> None:
    with TestClient(app) as client:
        for existing_model in client.get("/models").json():
            client.post(f"/models/{existing_model['id']}/retire")

        dataset_response = client.post("/models/dataset")
        assert dataset_response.status_code == 200

        train_response = client.post(
            "/models/train",
            json={"category": "general", "data_mode": "test", "model_type": "ensemble"},
        )
        assert train_response.status_code == 200
        model = train_response.json()
        assert model["status"] == "candidate"

        prediction_before_approval = client.post("/predictions/generate?data_mode=test")
        assert prediction_before_approval.status_code == 200
        assert prediction_before_approval.json()
        assert all(
            "model_not_approved_for_paper" in prediction["no_trade_reasons"]
            for prediction in prediction_before_approval.json()
        )

        approve_response = client.post(f"/models/{model['id']}/approve-paper")
        assert approve_response.status_code == 400
        assert "approval thresholds" in approve_response.json()["detail"]

        prediction_response = client.post("/predictions/generate?data_mode=test")
        assert prediction_response.status_code == 200
        assert prediction_response.json()

        opportunity_response = client.post("/model-opportunities/generate?data_mode=test")
        assert opportunity_response.status_code == 200
        assert opportunity_response.json() == []

        trade_response = client.post("/model-paper-trades/run?data_mode=test")
        assert trade_response.status_code == 400
        assert "MODEL PAPER TRADING PAUSED" in trade_response.json()["detail"]

        analytics_response = client.get("/model-analytics")
        assert analytics_response.status_code == 200
        assert analytics_response.json()["arbitrage_pnl_excluded"] is True

        readiness_response = client.get("/models/readiness")
        assert readiness_response.status_code == 200
        readiness = readiness_response.json()
        assert readiness["model_paper_trading_paused"] is True
        assert readiness["unique_resolved_markets"] == 24
        assert readiness["chronological_splits"]["market_overlap"] is False


@pytest.mark.asyncio
async def test_under_sampled_category_training_registers_general_fallback() -> None:
    await init_db()
    service = PredictionService(Settings(local_development=True), AsyncSessionLocal)

    summary = await service.train_model(
        ModelTrainingRequest(category=MarketCategory.POLITICS, data_mode="test")
    )

    assert summary.category == MarketCategory.GENERAL
    assert summary.training_sample_count == 48


@pytest.mark.asyncio
async def test_missing_approved_model_artifact_fails_clearly(tmp_path: Path) -> None:
    backend = SqlAlchemyDatabaseBackend(f"sqlite+aiosqlite:///{tmp_path / 'missing.db'}")
    await backend.init()
    service = PredictionService(
        Settings(local_development=True, model_registry_dir=str(tmp_path / "artifacts")),
        backend.sessionmaker,
    )
    summary = await service.train_model(ModelTrainingRequest(data_mode="test"))

    async with backend.sessionmaker() as session:
        record = await session.get(PredictionModelRecord, summary.id)
        assert record is not None
        record.status = ModelStatus.APPROVED_FOR_PAPER.value
        record.artifact_path = "model_artifacts/does-not-exist.pkl"
        await session.commit()

    with pytest.raises(ValueError, match="model artifact"):
        await service.generate_predictions("test")
