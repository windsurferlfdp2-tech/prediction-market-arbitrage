# Live Data Migration Report

Audit date: 2026-07-25

## Summary

Normal runtime was changed from simulation-driven operation to live-market-data-only operation.
Supported data modes are now `live` and `test`.

`DATA_MODE=live` is the local development default. `DATA_MODE=test` is reserved for automated tests
and isolated deterministic workflows. Live mode no longer falls back to fixtures when exchange
requests fail.

Trade execution remains paper-only. No live order submission, wallet signing, deposit, withdrawal,
or private-key trading flow was added.

## Previous Non-Live Paths Found

- Backend settings accepted `simulation` and `fixtures` as runtime data modes.
- Local docs and environment examples instructed developers to start with `DATA_MODE=simulation`.
- Exchange adapters could load fixture payloads from runtime adapter code.
- Scanner service could generate simulated markets and order books in normal runtime.
- Frontend dashboards exposed mode switching controls that allowed simulated/test data in normal UI.
- Model prediction endpoints accepted simulation request parameters and stored simulation predictions.
- Existing SQLite database contained old simulation records.

## Runtime Simulation Paths Removed

- Runtime modes restricted to `live` and `test`.
- Local backend and frontend docs now use live mode.
- Frontend normal dashboards always request live data.
- Live exchange adapters do not import fixture loaders unless `DATA_MODE=test`.
- Scanner-generated deterministic data is gated behind `DATA_MODE=test`.
- Analytics default to live records only.
- Legacy stored `SIMULATION:` and `TEST:` prediction records are excluded from live model APIs.
- New paper-trade records use `paper_trade` payloads and labels:
  - `LIVE-DATA PAPER TRADE`
  - `LIVE-DATA MODEL PAPER TRADE`

## Test Fixtures Preserved

Fixtures remain under backend test paths and adapter fixture modules for automated tests only.
`USE_FIXTURES=true` is rejected unless `DATA_MODE=test`.
Production rejects `DATA_MODE=test`.

## Database Cleanup

Dry-run before cleanup found:

- `opportunity_history`: 3 simulation records
- `order_book_snapshots`: 8,334 simulation records
- `model_predictions`: 22 simulation records
- `model_opportunities`: 10 simulation records
- `paper_trade_simulations`: 3 simulation records
- `opportunities`: 0 non-live records
- `model_paper_trades`: 0 non-live records

Cleanup was applied after creating backup:

`backend/prediction_market_arb.db.backup-20260725T212040Z`

Deleted:

- `opportunity_history`: 3
- `order_book_snapshots`: 8,334
- `model_predictions`: 22
- `model_opportunities`: 10
- `paper_trade_simulations`: 3

Post-cleanup dry-run found zero non-live records in audited runtime tables.

## Live Exchange Checks

Backend started with:

```bash
LOCAL_DEVELOPMENT=true DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db DATA_MODE=live USE_FIXTURES=false MODEL_LIVE_MARKET_LIMIT=5 LIVE_SCAN_MARKET_LIMIT=10 .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verified routes:

- `GET /health`: 200, `mode=live`, `data_source=live`, `is_live_data=true`
- `GET /markets`: 200, returned live Polymarket and Kalshi markets
- `GET /opportunities`: 200, returned `[]`
- `GET /analytics/opportunities`: 200, live metrics only
- `POST /market-matches/generate`: 200, returned `[]`
- `POST /predictions/generate?data_mode=live`: 200, generated live predictions
- `POST /model-opportunities/generate?data_mode=live`: 200 after persistence fix, returned `[]`
- `POST /model-paper-trades/run?data_mode=live`: 200, returned `[]`

Latest observed live timestamps during smoke test:

- Server health timestamp: 2026-07-25T21:22:07Z
- Polymarket market fetch: 2026-07-25T21:22:07Z
- Kalshi market fetch: 2026-07-25T21:22:08Z
- Live order-book requests: 2026-07-25T21:22:25Z to 2026-07-25T21:22:28Z
- Latest successful live prediction timestamp: 2026-07-25T21:22:30Z

Live market sample:

- Polymarket returned active markets including `New Rihanna Album before GTA VI?`
- Kalshi returned active markets including `San Fancisco wins by over 11.5 runs?`

No qualifying live arbitrage or model paper trade existed during verification. No synthetic
opportunity was generated.

## Bugs Fixed

- Repeated live model-opportunity generation crashed with SQLite
  `UNIQUE constraint failed: model_predictions.id`.
- Root cause: prediction persistence used stable IDs and SQLAlchemy autoflush could insert a
  duplicate pending record before the existing-record check completed.
- Fix: model prediction, model opportunity, and model paper-trade persistence now uses merge-style
  upserts.
- Legacy prediction/model records without `data_source` could be treated as live by model defaults.
- Fix: live API filtering now infers legacy non-live source from old `SIMULATION:` / `TEST:` titles
  and IDs.

## API Contract Changes

Models now include live-source metadata where applicable:

- `data_source`
- `is_live_data`
- `source_timestamp`
- `processed_timestamp`
- `freshness_status`
- `execution_mode=paper`
- `uses_live_market_data=true` for live-data paper trades

Unsupported fixture usage in live mode fails during settings validation.

## Frontend Changes

- Removed normal data-mode selectors from dashboard, market matching, model dashboard, and
  opportunity detail flow.
- Normal frontend API calls use live data.
- UI labels live operation as live market data.
- Empty live dashboards remain empty with truthful messages rather than sample data.

## Files Changed For This Migration

Primary live-data migration files:

- `.env`
- `.env.example`
- `README.md`
- `backend/app/config.py`
- `backend/app/exchanges/polymarket.py`
- `backend/app/exchanges/kalshi.py`
- `backend/app/main.py`
- `backend/app/models/domain.py`
- `backend/app/services/scanner.py`
- `backend/app/services/history.py`
- `backend/app/services/paper_trading.py`
- `backend/app/services/prediction.py`
- `backend/app/services/realtime_books.py`
- `backend/app/tools/cleanup_non_live_data.py`
- `backend/app/tools/__init__.py`
- `backend/tests/test_simulation_mode.py`
- `frontend/app/page.tsx`
- `frontend/app/components/OpportunityDashboard.tsx`
- `frontend/app/market-matches/MarketMatchReviewClient.tsx`
- `frontend/app/market-matches/page.tsx`
- `frontend/app/models/ModelDashboardClient.tsx`
- `frontend/app/opportunities/[id]/page.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `scripts/start-backend-local.sh`

The working tree also contains prior Phase 2 and Phase 3 implementation files that predate this
specific migration.

## Tests Run

Backend:

- `pytest`: 63 passed, 47 warnings
- Focused API/prediction regression suite: 21 passed, 47 warnings
- `ruff check app tests`: passed
- `mypy app tests`: passed

Frontend:

- `npm test`: passed (`tsc --noEmit`)
- `npm run typecheck`: passed
- `npm run lint`: passed
- `npm run build`: passed

Warnings remaining:

- Pydantic v2 deprecation warning for `json_encoders`
- Starlette/FastAPI TestClient deprecation warning
- joblib physical core-count warning on macOS

## Remaining Live-Data Limitations

- Live market matching returned no candidate pairs with the current limited fetch window.
- Live arbitrage scanning returned no opportunities because no verified live pair with fresh books
  qualified.
- Live model predictions run against current live market/order-book data, but approved models in the
  local registry were trained from the earlier deterministic test dataset. This is acceptable for
  plumbing verification, not evidence of predictive quality.
- Live model-opportunity generation returned no current opportunities after filters/no-trade rules.
- Live-data paper trading did not create a trade because there was no qualifying live opportunity.
- `GET /order-books/status` was empty after smoke tests because no verified-pair scanner books were
  maintained in the realtime status service during this run; model prediction book fetches were
  performed directly through adapters.

## Safety Findings

- No live order submission was added.
- No wallet signing was added.
- No deposit or withdrawal flow was added.
- Paper trading remains simulated execution only.
- Live-data paper trades are explicitly labeled as paper trades using live market data.

## Recommended Next Steps

- Run live mode for several hours with a larger `LIVE_SCAN_MARKET_LIMIT` and manually verify any
  generated market-match candidates before expecting cross-platform arbitrage.
- Rebuild and approve models only after collecting genuine resolved live historical data.
- Add a UI indicator for “live predictions exist but no model opportunities passed filters.”
- Improve realtime order-book status reporting for model-prediction adapter fetches.
