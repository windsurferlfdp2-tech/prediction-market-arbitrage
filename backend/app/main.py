import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated, cast
from uuid import uuid4

import structlog
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.config import Settings, SwitchableDataMode, settings
from app.exchanges.kalshi import KalshiAdapter
from app.exchanges.polymarket import PolymarketAdapter
from app.logging import configure_logging
from app.models.domain import (
    ArbitrageOpportunity,
    ExchangeHealth,
    Market,
    ModelOpportunity,
    ModelPaperTrade,
    ModelStatus,
    ModelTrainingRequest,
    PaperTradeSimulation,
    PredictionModelSummary,
    PredictionResult,
    RealtimeBookStatus,
)
from app.persistence.database import AsyncSessionLocal, init_db
from app.services.cache import create_cache_backend
from app.services.history import OpportunityAnalyticsService, OpportunityHistoryRecorder
from app.services.market_matching import (
    MarketMatchingService,
    MarketPairReview,
    MarketPairStatusUpdate,
)
from app.services.paper_trading import PaperTradingSimulator
from app.services.position_reconciliation import PositionReconciliationService
from app.services.prediction import PredictionService
from app.services.realtime_books import (
    OrderBookSnapshotRecorder,
    RealtimeOrderBookService,
)
from app.services.scanner import ScannerService

configure_logging(settings.log_level)
log = structlog.get_logger()

history_recorder = OpportunityHistoryRecorder(AsyncSessionLocal)
analytics_service = OpportunityAnalyticsService(AsyncSessionLocal)
market_matching_service = MarketMatchingService(AsyncSessionLocal)
realtime_books = RealtimeOrderBookService(
    settings,
    [PolymarketAdapter(settings), KalshiAdapter(settings)],
)
paper_trading = PaperTradingSimulator(settings, AsyncSessionLocal)
prediction_service = PredictionService(settings, AsyncSessionLocal)
position_reconciliation_service = PositionReconciliationService(settings, AsyncSessionLocal)
book_snapshot_recorder = OrderBookSnapshotRecorder(AsyncSessionLocal, settings)
scanner = ScannerService(
    settings,
    [PolymarketAdapter(settings), KalshiAdapter(settings)],
    history_recorder,
    market_matching_service,
    realtime_books,
    paper_trading,
    book_snapshot_recorder,
)
cache = create_cache_backend(settings)
mode_scanners: dict[str, ScannerService] = {}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    reconciliation_task: asyncio.Task[None] | None = None
    if (
        settings.effective_data_mode == "live"
        and settings.model_position_reconciliation_enabled
    ):
        reconciliation_task = asyncio.create_task(_position_reconciliation_loop())
    try:
        yield
    finally:
        if reconciliation_task is not None:
            reconciliation_task.cancel()
            try:
                await reconciliation_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Prediction Market Arbitrage Scanner",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("x-request-id", str(uuid4()))
    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (perf_counter() - started) * 1000
        log.exception(
            "request_failed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=500,
            duration_ms=round(duration_ms, 2),
            error=type(exc).__name__,
        )
        raise
    duration_ms = (perf_counter() - started) * 1000
    response.headers["x-request-id"] = request_id
    log.info(
        "request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


def _scanner_for_mode(data_mode: SwitchableDataMode | None) -> ScannerService:
    if data_mode is None or data_mode == settings.effective_data_mode:
        return scanner
    cached = mode_scanners.get(data_mode)
    if cached is not None:
        return cached
    request_settings = settings.model_copy(update={"data_mode": data_mode, "use_fixtures": False})
    mode_scanners[data_mode] = ScannerService(
        request_settings,
        [PolymarketAdapter(request_settings), KalshiAdapter(request_settings)],
        history_recorder,
        market_matching_service,
        RealtimeOrderBookService(
            request_settings,
            [PolymarketAdapter(request_settings), KalshiAdapter(request_settings)],
        ),
        paper_trading,
        OrderBookSnapshotRecorder(AsyncSessionLocal, request_settings),
    )
    return mode_scanners[data_mode]


def _settings_for_mode(data_mode: SwitchableDataMode | None) -> Settings:
    if data_mode is None or data_mode == settings.effective_data_mode:
        return settings
    return settings.model_copy(update={"data_mode": data_mode, "use_fixtures": False})


@app.get("/health")
async def health(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> dict[str, object]:
    request_settings = _settings_for_mode(data_mode)
    request_scanner = _scanner_for_mode(data_mode)
    exchanges: list[ExchangeHealth] = await request_scanner.health()
    cache_ok = await cache.ping()
    return {
        "ok": request_settings.effective_data_mode == "test"
        or all(item.ok for item in exchanges),
        "mode": request_settings.effective_data_mode,
        "test_mode": request_settings.effective_data_mode == "test",
        "data_source": request_settings.effective_data_mode,
        "is_live_data": request_settings.effective_data_mode == "live",
        "local_development": request_settings.local_development,
        "database": "sqlite" if request_settings.local_development else "postgresql",
        "cache": request_settings.cache_backend,
        "cache_ok": cache_ok,
        "read_only": True,
        "exchanges": exchanges,
    }


@app.get("/markets", response_model=list[Market])
async def markets(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[Market]:
    return await _scanner_for_mode(data_mode).markets()


@app.get("/opportunities", response_model=list[ArbitrageOpportunity])
async def opportunities(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[ArbitrageOpportunity]:
    return await _scanner_for_mode(data_mode).opportunities()


@app.get("/opportunities/{opportunity_id}", response_model=ArbitrageOpportunity)
async def opportunity(
    opportunity_id: str,
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> ArbitrageOpportunity:
    result = await _scanner_for_mode(data_mode).opportunity(opportunity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return result


@app.get("/analytics/opportunities")
async def opportunity_analytics(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> dict[str, object]:
    overview = await analytics_service.overview(data_mode)
    scanner_status = _scanner_for_mode(data_mode).status()
    if scanner_status.get("last_completed_at") is not None:
        overview["latest_scan_timestamp"] = scanner_status["last_completed_at"]
    if data_mode == "test":
        overview.update(await paper_trading.analytics())
    return overview


@app.get("/paper-trades", response_model=list[PaperTradeSimulation])
async def paper_trades(limit: int = Query(default=50, ge=1, le=250)) -> list[PaperTradeSimulation]:
    return await paper_trading.latest(limit)


@app.get("/order-books/status", response_model=list[RealtimeBookStatus])
async def order_book_status() -> list[RealtimeBookStatus]:
    return realtime_books.statuses()


@app.get("/scanner/status")
async def scanner_status(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> dict[str, object]:
    request_scanner = _scanner_for_mode(data_mode)
    return request_scanner.status()


@app.get("/scanner/diagnostics")
async def scanner_diagnostics(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> dict[str, object]:
    request_scanner = _scanner_for_mode(data_mode)
    return dict(request_scanner.status().get("diagnostics", {}))


@app.get("/models", response_model=list[PredictionModelSummary])
async def models() -> list[PredictionModelSummary]:
    return await prediction_service.list_models()


@app.get("/models/readiness")
async def model_dataset_readiness() -> dict[str, object]:
    try:
        return await prediction_service.dataset_readiness()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/models/{model_id}", response_model=PredictionModelSummary)
async def model(model_id: str) -> PredictionModelSummary:
    result = await prediction_service.get_model(model_id)
    if result is None:
        raise HTTPException(status_code=404, detail="model not found")
    return result


@app.post("/models/train", response_model=PredictionModelSummary)
async def train_model(request: ModelTrainingRequest) -> PredictionModelSummary:
    try:
        return await prediction_service.train_model(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/models/{model_id}/approve-paper", response_model=PredictionModelSummary)
async def approve_model_for_paper(model_id: str) -> PredictionModelSummary:
    try:
        result = await prediction_service.update_model_status(
            model_id,
            ModelStatus.APPROVED_FOR_PAPER,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="model not found")
    return result


@app.post("/models/{model_id}/retire", response_model=PredictionModelSummary)
async def retire_model(model_id: str) -> PredictionModelSummary:
    try:
        result = await prediction_service.update_model_status(model_id, ModelStatus.RETIRED)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="model not found")
    return result


@app.post("/models/dataset")
async def build_model_dataset() -> dict[str, object]:
    try:
        return await prediction_service.build_historical_dataset("test")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/predictions/generate", response_model=list[PredictionResult])
async def generate_predictions(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[PredictionResult]:
    try:
        return await prediction_service.generate_predictions(
            data_mode or settings.effective_data_mode
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/predictions", response_model=list[PredictionResult])
async def predictions(
    limit: int = Query(default=100, ge=1, le=500),
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[PredictionResult]:
    return await prediction_service.predictions(
        limit,
        data_mode or settings.effective_data_mode,
    )


@app.get("/predictions/{prediction_id}", response_model=PredictionResult)
async def prediction(prediction_id: str) -> PredictionResult:
    result = await prediction_service.prediction(prediction_id)
    if result is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    return result


@app.post("/model-opportunities/generate", response_model=list[ModelOpportunity])
async def generate_model_opportunities(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[ModelOpportunity]:
    try:
        return await prediction_service.detect_model_opportunities(
            data_mode or settings.effective_data_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/model-opportunities", response_model=list[ModelOpportunity])
async def model_opportunities(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[ModelOpportunity]:
    return await prediction_service.model_opportunities(data_mode or settings.effective_data_mode)


@app.post("/model-paper-trades/run", response_model=list[ModelPaperTrade])
async def run_model_paper_trades(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[ModelPaperTrade]:
    try:
        return await prediction_service.create_model_paper_trades(
            data_mode or settings.effective_data_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/model-paper-trades", response_model=list[ModelPaperTrade])
async def model_paper_trades(
    limit: int = Query(default=100, ge=1, le=500),
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[ModelPaperTrade]:
    return await prediction_service.model_paper_trades(
        limit,
        data_mode or settings.effective_data_mode,
    )


@app.post("/model-paper-trades/reconcile")
async def reconcile_model_paper_trades(
    position_id: str | None = Query(default=None),
    market_id: str | None = Query(default=None),
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
    apply: bool = Query(default=False),
) -> list[dict[str, object]]:
    results = await position_reconciliation_service.reconcile(
        position_id=position_id,
        market_id=market_id,
        data_mode=data_mode or settings.effective_data_mode,
        apply=apply,
    )
    return [result.as_dict() for result in results]


@app.get("/model-analytics")
async def model_analytics(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> dict[str, object]:
    return await prediction_service.analytics(data_mode or settings.effective_data_mode)


@app.post("/market-matches/generate", response_model=list[MarketPairReview])
async def generate_market_matches(
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[MarketPairReview]:
    markets = await _scanner_for_mode(data_mode).candidate_markets()
    return await market_matching_service.generate_candidates(markets)


@app.get("/market-matches", response_model=list[MarketPairReview])
async def market_matches(
    status: str | None = Query(default=None),
    data_mode: Annotated[SwitchableDataMode | None, Query()] = None,
) -> list[MarketPairReview]:
    mode = data_mode or settings.effective_data_mode
    return await market_matching_service.list_reviews(
        status,
        include_non_live=mode == "test",
    )


@app.patch("/market-matches/{review_id}", response_model=MarketPairReview)
async def update_market_match(
    review_id: str,
    update: MarketPairStatusUpdate,
) -> MarketPairReview:
    result = await market_matching_service.update_status(review_id, update.status)
    if result is None:
        raise HTTPException(status_code=404, detail="market pair review not found")
    return result


@app.websocket("/ws/opportunities")
async def ws_opportunities(websocket: WebSocket) -> None:
    data_mode = websocket.query_params.get("data_mode")
    if data_mode not in {None, "live", "test"}:
        await websocket.close(code=1008)
        return
    request_scanner = _scanner_for_mode(cast(SwitchableDataMode | None, data_mode))
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(
                [item.model_dump(mode="json") for item in await request_scanner.opportunities()]
            )
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return


async def _position_reconciliation_loop() -> None:
    while True:
        try:
            await position_reconciliation_service.reconcile(
                data_mode=settings.effective_data_mode,
                apply=True,
            )
        except Exception as exc:
            log.exception("position_resolution_check_error", error=str(exc))
        await asyncio.sleep(settings.model_position_reconciliation_interval_seconds)
