# System Health Audit

Audit date: 2026-07-26 UTC

## Environment

- Repository: `/Users/luciodelpin/prediction-market-arb-scanner`
- Backend: FastAPI, Python 3.12.13, SQLite local database, in-memory cache
- Frontend: Next.js 16.2.10, Node.js 20.20.2, npm 10.8.2
- Backend URL: `http://127.0.0.1:8000`
- Frontend dev URL tested: `http://localhost:3000`
- Data mode tested: `live`
- Read-only exchange behavior: confirmed; paper trading remains simulated execution only

## Architecture Summary

The backend exposes live market ingestion, market matching, arbitrage scanning, prediction-model
routes, analytics, and paper-trade routes from FastAPI. Local development uses SQLite through
SQLAlchemy and bypasses Redis by using the memory cache backend. PostgreSQL and Redis settings
remain present for production-oriented configuration.

The frontend uses a centralized API client driven by `NEXT_PUBLIC_API_URL`. The local value tested
was `http://127.0.0.1:8000`.

## Commands Executed

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
LOCAL_DEVELOPMENT=true DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db DATA_MODE=live USE_FIXTURES=false MODEL_LIVE_MARKET_LIMIT=5 LIVE_SCAN_MARKET_LIMIT=25 .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
rm -rf .next
npm run dev
```

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/openapi.json
curl -sS http://127.0.0.1:8000/markets?data_mode=live
curl -sS http://127.0.0.1:8000/opportunities?data_mode=live
curl -sS http://127.0.0.1:8000/analytics/opportunities?data_mode=live
curl -sS -X POST http://127.0.0.1:8000/market-matches/generate?data_mode=live
curl -sS -X POST http://127.0.0.1:8000/predictions/generate?data_mode=live
curl -sS -X POST http://127.0.0.1:8000/model-opportunities/generate?data_mode=live
curl -sS -X POST http://127.0.0.1:8000/model-paper-trades/run?data_mode=live
```

## Startup Results

- Backend startup: completed successfully.
- SQLite initialization: completed successfully.
- PostgreSQL in local mode: not attempted.
- Redis in local mode: not attempted; memory cache reported healthy.
- Frontend startup: completed successfully and loaded `.env.local`.
- Frontend production build: completed successfully.

## Route Results

- `GET /health`: 200, live mode, SQLite, memory cache, read-only.
- `GET /docs`: 200.
- `GET /openapi.json`: 200.
- `GET /markets?data_mode=live`: 200, returned 50 live markets with the configured 25-per-exchange limit.
- `GET /opportunities?data_mode=live`: 200, returned `[]`.
- `GET /analytics/opportunities?data_mode=live`: 200, current metrics zero, 243 old records excluded.
- `GET /scanner/status`: 200 after scan, last completed at `2026-07-26T05:36:07.586151Z`.
- `POST /market-matches/generate?data_mode=live`: 200, returned no current candidates in the final sample.
- `GET /market-matches`: 200, excludes old `SIMULATION` records by default.
- `GET /market-matches?data_mode=test`: 200, exposes isolated test records for tests only.
- `PATCH /market-matches/not-a-real-review`: 404 JSON, no stack trace.
- `GET /models`: 200.
- `GET /models/not-a-real-model`: 404 JSON, no stack trace.
- `POST /predictions/generate?data_mode=live`: 200, generated 8 current live predictions in final run.
- `GET /predictions?data_mode=live`: 200, returns only fresh current live predictions after the fix.
- `GET /predictions/not-a-real-prediction`: 404 JSON, no stack trace.
- `POST /model-opportunities/generate?data_mode=live`: 200, returned `[]`.
- `GET /model-opportunities?data_mode=live`: 200, returned `[]` after stale-record filtering.
- `POST /model-paper-trades/run?data_mode=live`: 200, returned `[]` because no eligible current opportunity existed.
- `GET /model-paper-trades?data_mode=live`: 200, returns historical live-data model paper trades.
- `GET /paper-trades?limit=5`: 200, returned `[]`.
- `GET /order-books/status`: 200, returned `[]` because no verified live pair books were active.

## CORS Findings

Manual and automated preflight checks passed for local origins:

- `http://localhost:3000`
- `http://127.0.0.1:3000`
- `http://localhost:3001`
- `http://127.0.0.1:3001`

`POST`, `PATCH`, `GET`, and `OPTIONS` are allowed for local development. Production is not made
permissive beyond configured origins.

## Live Exchange Results

Polymarket:

- Live endpoint observed in backend logs: `https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=25&offset=0`
- Status: 200 in live checks.
- Active market sample: 25 markets.
- Order-book endpoint observed for predictions: Polymarket CLOB `/book?token_id=...`, status 200.
- Fixture fallback: not used in live mode.

Kalshi:

- Live endpoint observed in backend logs: `https://external-api.kalshi.com/trade-api/v2/markets?status=open&limit=25&mve_filter=exclude`
- Status: 200 in live checks.
- Active market sample: 25 markets.
- Order-book endpoint observed for predictions: `/trade-api/v2/markets/{ticker}/orderbook`, status 200.
- Market-data authentication: not required for the REST market checks that succeeded.
- Fixture fallback: not used in live mode.

WebSocket ingestion was not active in this local run; REST fallback was the observed transport.

## Latest Timestamps

- Server time from analytics: `2026-07-26T05:36:49.624308Z`
- Latest completed live scan: `2026-07-26T05:36:07.586151Z`
- Latest live market fetch: `2026-07-26T05:36:07.412311Z`
- Latest current prediction batch: `2026-07-26T05:36:37.816473Z`
- Latest current model opportunity: none
- Latest current arbitrage opportunity: none
- Latest order-book status timestamp: none exposed through `/order-books/status` because no verified pair books were active

## Database Findings

SQLite database: `backend/prediction_market_arb.db`

- `market_pair_reviews`: 23 records, 3 old simulation-marked reviews.
- `model_predictions`: 120 records, newest `2026-07-26T05:36:37.816473Z`.
- `model_opportunities`: 3 historical records, newest `2026-07-25T21:46:50.617631Z`.
- `model_paper_trades`: 11 historical records, newest `2026-07-25T21:46:50.660600Z`.
- `opportunity_history`: 243 old rows, newest detected `2026-07-20T22:09:39.237570Z`.
- `order_book_snapshots`: 2504 old rows, newest observed `2026-07-21T20:48:33.779709Z`.
- `prediction_models`: 29 approved-for-paper records.
- `historical_training_snapshots`: 48 rows.

Current arbitrage analytics exclude the 243 old opportunity-history rows from current-day live
metrics. Old simulation market-pair reviews remain in the database but no longer appear in the
default live market-match listing or scanner verified-pair map.

## Market Matching Findings

Live market-match generation reaches FastAPI and uses live market samples from both exchanges.
The final sample returned no candidates. Earlier samples generated low-quality historical pending
reviews, such as Harvey Weinstein markets paired with unrelated Kalshi sports markets; these remain
pending and do not enter the scanner without manual approval.

Manual approval enforcement remains in place. Title similarity alone does not approve pairs.

Remaining limitation: `market_pair_reviews` has no explicit `data_source` or source freshness
columns, so older live-generated review candidates can still appear as historical pending reviews.

## Arbitrage Findings

- Live scanner completed successfully.
- Markets checked in final scan: 50.
- Verified pairs checked: 0.
- Books checked: 0.
- Opportunities found: 0.
- Current analytics:
  - Detected today: 0
  - Median duration: 0
  - Median ROI: 0
  - Maximum theoretical profit: 0
  - Historical records excluded: 243

The earlier frozen dashboard values were not current live opportunities. The scanner currently has
no verified live pairs with usable books, so no live arbitrage opportunity was available to paper
trade.

## Model Findings

- Approved models exist, but they are numerous duplicate Phase 3 models with a tiny 48-row training
dataset.
- The model metrics are not strong enough to claim superiority over the market baseline.
- Fresh live prediction generation works.
- Final current prediction feed count: 8.
- Every final current prediction was no-trade due low confidence, high uncertainty, and in some
Kalshi cases wide spreads.
- Stale live-labeled predictions are now excluded from the current live prediction feed.

Remaining limitation: model analytics still aggregate historical live-labeled model opportunities
and paper trades. They are historical records, not current opportunities.

## Leakage-Test Findings

Backend tests include leakage protections for:

- Future feature timestamps.
- Resolution labels excluded from features.
- Same-market snapshots separated across train/validation splits.
- Time-aware split behavior.

The backend test suite passed after the audit fixes.

## Paper-Trading Findings

- Real-money execution code was not found.
- Paper-trading routes are present and remain simulated.
- `POST /model-paper-trades/run?data_mode=live` returned `[]` because no current live model
  opportunity passed filters.
- A new live-data paper trade was not persisted during this audit because no eligible current
  opportunity existed.
- Historical model paper-trade records exist and are returned by historical endpoints.

## Frontend Findings

- `.env.local` exists and sets `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`.
- Frontend startup succeeded.
- Dashboard rendered through Next.js.
- Frontend API configuration tests passed.
- Production build passed.
- Requests use the centralized API client and no Docker-only hostnames were found in frontend API
  code.

Remaining limitation: the model page still shows historical model analytics and historical open
model paper trades alongside current controls; it should label historical/current scopes more
clearly in a later cleanup.

## Analytics Findings

Current arbitrage analytics are corrected and exclude stale rows:

- `total_candidates_recorded`: 0
- `unique_opportunities`: 0
- `raw_detections`: 0
- `active_opportunities`: 0
- `historical_records_excluded`: 243

Model analytics are historical aggregate metrics and should not be interpreted as current live
opportunity performance.

## Performance Findings

- Final live arbitrage scan duration: 3.6756 seconds for 50 markets and 0 verified pairs.
- Frontend production build completed successfully.
- Live prediction generation completed successfully for 8 current rows.
- No duplicate WebSocket subscriptions were observed because WebSocket order-book ingestion was not
  active.

## Security Findings

- No live order-submission route or exchange order-creation code was found.
- No wallet signing, deposit, withdrawal, or autonomous execution code was found.
- `KALSHI_PRIVATE_KEY_PATH` exists only as optional server-side config for market-data WebSocket
  authentication.
- Frontend public environment variables do not expose server secrets.
- Error responses for missing resources return JSON messages and request IDs, not stack traces.

## Bugs Found

1. Default live market-match listing exposed old `SIMULATION` review records from the local database.
2. Verified simulation reviews could theoretically be considered by scanner matching logic.
3. Current model-opportunity feed exposed stale live-labeled records from prior runs.
4. Current prediction feed exposed stale live-labeled records from prior runs.
5. Frontend model training helper used `data_mode: "test"` from normal UI code.

## Bugs Fixed

1. Default live market-match lists now filter non-live review records.
2. Scanner verified-pair map now excludes non-live review records.
3. Test-mode market-match listing remains available through explicit `data_mode=test`.
4. Live model-opportunity feed now rejects stale records by detection time and book freshness.
5. Live prediction feed now rejects stale records by source/feature timestamp.
6. Frontend model training helper now sends `data_mode: "live"`.

## Files Changed In This Audit

- `backend/app/main.py`
- `backend/app/services/market_matching.py`
- `backend/app/services/prediction.py`
- `backend/tests/test_api.py`
- `backend/tests/test_market_matching.py`
- `backend/tests/test_prediction_phase3.py`
- `frontend/lib/api.ts`
- `SYSTEM_HEALTH_AUDIT.md`

The working tree also contains many pre-existing Phase 1-3 changes and prior audit/report files.
Those were not all introduced by this audit pass.

## Migrations Changed

No database migrations were changed in this audit.

## Tests Run

Backend:

- `pytest -q`: 66 passed, 47 warnings, 0 failed, 0 skipped.
- `pytest -q tests/test_market_matching.py tests/test_prediction_phase3.py`: 18 passed before the final added stale prediction test.
- `pytest -q tests/test_prediction_phase3.py tests/test_api.py tests/test_market_matching.py`: 29 passed.
- `ruff check app tests`: passed.
- `mypy app tests`: passed.

Frontend:

- `npm run test`: passed, including 8 API-config tests.
- `npm run lint`: passed.
- `npm run build`: passed.

Warnings:

- Pydantic `json_encoders` deprecation warnings.
- FastAPI/Starlette TestClient deprecation warning.
- joblib CPU-count warning in local environment.

## Remaining Issues

1. The full live-data paper-trade workflow did not complete because no current eligible live
   arbitrage or model opportunity existed.
2. No verified live Polymarket/Kalshi pair is available in the current local database, so the
   arbitrage scanner checks zero verified pairs.
3. WebSocket order-book ingestion was not active in this run; REST polling/fallback was observed.
4. The model registry contains 29 approved models trained on only 48 snapshots. This is not enough
   evidence for model-based paper-trading confidence.
5. Historical live-labeled model analytics still aggregate old model opportunities and paper trades.
6. `market_pair_reviews` lacks explicit data-source/freshness columns, making cleanup and filtering
   less precise than the newer prediction/opportunity records.
7. Scanner status is in memory and resets after backend reload until a scan route is called.

## Exact Startup Commands

Backend:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=live
export USE_FIXTURES=false
export MODEL_LIVE_MARKET_LIMIT=5
export LIVE_SCAN_MARKET_LIMIT=25
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
cp .env.example .env.local
rm -rf .next
npm run dev
```

Verify:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/markets?data_mode=live
curl -sS http://127.0.0.1:8000/opportunities?data_mode=live
curl -sS -X POST "http://127.0.0.1:8000/predictions/generate?data_mode=live"
```

## Readiness Status

The system is healthy enough for local live-data observation of ingestion, dashboards, prediction
generation, and scanner status. It is not yet ready for several weeks of unattended model-based
paper-trading observation because no complete current live opportunity-to-paper-trade workflow
succeeded, models are trained on a very small dataset, WebSocket ingestion was not active, and
historical model analytics need clearer current/historical separation.
