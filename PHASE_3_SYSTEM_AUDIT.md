# Phase 3 System Audit

Audit date: 2026-07-21

## Overall Status

Phase 1, Phase 2, and the Phase 3 fixture workflow run locally without Docker. Local development
uses SQLite and in-memory cache. PostgreSQL and Redis production configuration remains present.

The system remains read-only with respect to exchanges. No live order execution, wallet, signing,
deposit, or withdrawal implementation was found.

Phase 3 is not ready for several weeks of model-based paper-trading observation as a research
signal. It is ready for fixture-based local development and further data collection. The current
model training data is deterministic fixture data, and the trained ensemble did not beat the raw
market baseline on Brier score.

## Environment Details

- Repository: `/Users/luciodelpin/prediction-market-arb-scanner`
- Backend: FastAPI, SQLAlchemy async, SQLite local mode
- Frontend: Next.js 16
- Python: 3.12.13 from backend `.venv`
- Backend audit DB: `sqlite+aiosqlite:////private/tmp/pma_phase3_audit_final.db`
- Backend URL verified: `http://127.0.0.1:8000`
- Frontend URL verified: `http://localhost:3000`
- Data mode for full workflow: `simulation`

## Architecture Summary

- Phase 1: Polymarket/Kalshi adapters normalize markets and order books into common Pydantic
  domain models.
- Phase 2: Manual market-pair reviews gate deterministic cross-platform arbitrage detection,
  paper-trading simulation, order-book snapshots, and historical analytics.
- Phase 3: Market-anchored prediction service builds deterministic point-in-time fixture features,
  trains logistic and gradient-boosted models, applies calibration, registers models, requires
  manual approval, generates model expected-value opportunities, and records `MODEL PAPER TRADE`
  simulations.

Strategy labels are separate:

- Deterministic arbitrage: `PAPER TRADING`
- Model expected value: `MODEL OPPORTUNITY`
- Model paper trading: `MODEL PAPER TRADE`
- Fixture/simulation data: `SIMULATION`

## Commands Executed

Repository/config:

```text
find . -maxdepth 3 -type f
sed -n PHASE_2_PLAN.md
sed -n PHASE_3_PLAN.md
sed -n PHASE_3_REPORT.md
git ls-files | rg secrets/artifacts/cache patterns
rg TODO/FIXME/security/trading/path/config patterns
find backend/migrations -maxdepth 1 -type f
git check-ignore generated local artifacts
```

Clean startup:

```text
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:3000 -sTCP:LISTEN
kill existing backend/frontend app PIDs
backend/.venv/bin/python -c import dependency check
npm --prefix frontend ls --depth=0
rm -r frontend/.next backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
LOCAL_DEVELOPMENT=true DATABASE_URL=sqlite+aiosqlite:////private/tmp/pma_phase3_audit_clean.db DATA_MODE=simulation .venv/bin/python -c init_db
LOCAL_DEVELOPMENT=true DATABASE_URL=sqlite+aiosqlite:////private/tmp/pma_phase3_audit_final.db DATA_MODE=simulation USE_FIXTURES=false .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/opportunities npm run dev
```

Quality:

```text
LOCAL_DEVELOPMENT=true DATABASE_URL=sqlite+aiosqlite:///:memory: DATA_MODE=simulation .venv/bin/pytest -q
.venv/bin/ruff check app tests
.venv/bin/mypy app tests
npm run lint
npm run typecheck
npm test
npm run build
```

## Repository And Configuration Findings

- No tracked `.env`, SQLite DB, model artifact, `.next`, `node_modules`, virtualenv, or cache files
  were found by `git ls-files`.
- `.gitignore` correctly ignores `.env`, DB files, `backend/model_artifacts/`, `.next`,
  `node_modules`, and caches.
- `.env.example` includes local SQLite, in-memory/local-development settings, live exchange URLs,
  WebSocket URLs, paper-trading settings, and Phase 3 model settings.
- Local development does not require PostgreSQL or Redis. `LOCAL_DEVELOPMENT=true` selects SQLite
  and memory cache.
- Production support remains present through `DATABASE_URL`, `REDIS_URL`, asyncpg, Redis, and
  docker-compose service URLs.
- Frontend public variables are backend URL and WebSocket URL only; no secrets were found in
  frontend public configuration.
- Model artifact path is configurable with `MODEL_REGISTRY_DIR`.
- Docker-only service names appear in Docker Compose and production/local-development tests, not in
  local-mode startup requirements.

## Database Findings

Migrations found and recorded:

```text
0001_opportunity_history
0002_market_pair_reviews
0003_phase_2_paper_and_books
0004_phase_3_prediction_models
```

Fresh database after Phase 3 workflow:

```text
historical_training_snapshots: 48
market_pair_reviews: 3
model_opportunities: 1
model_paper_trades: 1
model_predictions: 2
opportunity_history: 3
order_book_snapshots: 12
paper_trade_simulations: 3
prediction_models: 1
schema_migrations: 4
```

Phase 2-style upgrade test:

- Created a SQLite DB with only the first three migration records.
- Ran `init_db()`.
- Verified Phase 3 tables were created and `0004_phase_3_prediction_models` was recorded.

Bug fixed during audit:

- SQLite `NUMERIC` columns were storing raw financial values as floating point and SQLAlchemy was
  quantizing default `Numeric` values. Added `DecimalValue`, which stores decimals as text in
  SQLite and `NUMERIC(38,18)` in PostgreSQL.
- SQLite `DateTime(timezone=True)` reads returned naive datetimes. Added `UtcDateTimeValue`, which
  stores ISO UTC text in SQLite and native timezone-aware timestamps in PostgreSQL.

Verified after fix:

```text
raw SQLite decimal: ('1.123456789123456789', 'text')
ORM decimal: Decimal 1.123456789123456789
raw SQLite timestamp: '2026-07-21T23:30:00Z'
ORM timestamp: 2026-07-21T23:30:00+00:00
```

## Routes Verified

All route checks below were made over HTTP against the running backend.

```text
GET /health?data_mode=simulation                         200
GET /markets?data_mode=simulation                        200 list:6
GET /opportunities?data_mode=simulation                  200 list:3
GET /opportunities/not-found?data_mode=simulation        404
GET /analytics/opportunities?data_mode=simulation        200
GET /paper-trades?limit=5                                200
GET /paper-trades?limit=0                                422
GET /order-books/status                                  200
GET /market-matches                                      200
PATCH /market-matches/not-found                          404
POST /market-matches/generate?data_mode=simulation       200 list:3
GET /models                                              200
GET /models/not-found                                    404
POST /models/dataset                                     200
POST /models/train                                       200
GET /models/{model_id}                                   200
POST /predictions/generate before approval               200 list:0
POST /models/{model_id}/approve-paper                    200
POST /predictions/generate?data_mode=simulation          200 list:2
GET /predictions                                         200
GET /predictions/{prediction_id}                         200
GET /predictions/not-found                               404
POST /model-opportunities/generate?data_mode=simulation  200 list:1
GET /model-opportunities                                 200
POST /model-paper-trades/run?data_mode=simulation        200 list:1
GET /model-paper-trades                                  200
GET /model-analytics                                     200
POST /models/{model_id}/retire                           200
POST /models/not-found/approve-paper                     404
POST /models/train with invalid category                 422
```

Artifact failure behavior:

- Missing approved model artifacts previously raised raw `FileNotFoundError`.
- Fixed during audit: artifacts must load from `MODEL_REGISTRY_DIR`, missing/corrupt artifacts raise
  clear `400` API errors and do not create model paper trades.

## Live Exchange Findings

Live read-only checks were run with `LIVE_SCAN_MARKET_LIMIT=25`.

Polymarket:

- Endpoint used: `https://gamma-api.polymarket.com/markets`
- Order book endpoint: `https://clob.polymarket.com/book`
- Latest successful audit request timestamp: `2026-07-21T23:21:55.841474+00:00`
- Active normalized markets: 25
- Rejected markets in capped sample: 0
- Probed order books: 4
- Usable order books: 4
- Raw payload keys preserved included `asks`, `bids`, `asset_id`, `market`, `timestamp`, `hash`.
- Pagination exists through `limit` and `offset`.
- Retry/backoff exists in `RetryingHttpClient`.

Kalshi:

- Endpoint used: `https://external-api.kalshi.com/trade-api/v2/markets`
- Order book endpoint: `/markets/{ticker}/orderbook`
- Latest successful audit request timestamp: `2026-07-21T23:22:00.218777+00:00`
- Active normalized markets: 25
- Rejected markets in capped sample: 0
- Probed order books: 4
- Usable order books: 4
- Raw payload keys preserved included `ticker`, `orderbook_fp`.
- Pagination exists through `cursor`.
- Kalshi executable asks are derived from opposite-side bids as `1 - bid`.

Limitations:

- Health route reports exchange configuration, not latest successful live request timestamps.
- Rate-limit behavior is generic retry/logging; no exchange-specific rate-limit cooldown state was
  observed.

## Background Task And Freshness Findings

- REST fallback order-book refresh works.
- Realtime order-book in-memory state, stale marking, sequence-gap checks, delta merge, reconnect
  backoff helper, and snapshot recorder are implemented and tested.
- Local WebSocket ingestors currently call REST fallback. Long-running network WebSocket loops are
  not implemented as always-on background tasks in local mode.
- No scheduler/watchdog was found for automatic recurring prediction generation or model paper
  trade updates.
- Health does not expose last successful scan timestamps, degraded/offline states, or watchdog
  state.

## Dataset Summary

Historical fixture dataset after build:

```text
snapshots: 48
markets: 24
date range: 2026-01-24T00:00:00+00:00 to 2026-02-18T00:00:00+00:00
categories: politics 8, economics 8, crypto 8, sports 8, technology 8, general 8
exchanges: polymarket 24, kalshi 24
labels: YES/1 24, NO/0 24
train markets: 16
validation markets: 8
split overlap: false
feature count: 105
missing indicators true: none in deterministic fixture data
```

Dataset build is idempotent by primary key; rerunning inserts zero duplicate fixture rows after the
first build.

## Leakage-Test Results

Automated tests cover:

- Feature timestamp cannot exceed prediction timestamp.
- Resolution outcome is excluded from features.
- Market close timestamp must be after prediction timestamp.
- Same-market snapshots do not cross train/validation split.
- Calibration is trained on held-out validation predictions.
- Prediction generation before model approval produces no predictions.

No leakage tests failed.

Limitations:

- External data revision leakage is not applicable because external providers are not implemented.
- Walk-forward folds are not fully implemented beyond grouped chronological holdout.

## Feature Audit

Implemented feature groups include:

- midpoint, best bid, best ask, spread
- time remaining, market age
- returns/log returns
- volatility
- volume and volume acceleration
- bid/ask depth and liquidity
- order-book imbalance
- spread and imbalance change
- distance from recent high/low
- cross-platform equivalent price and divergence
- related-market probability
- data freshness and update count
- missing-value indicators

Lookback windows present:

```text
1m, 5m, 15m, 1h, 6h, 24h, 7d
```

Limitations:

- Fixture data currently populates all features deterministically; insufficient-history missingness
  behavior is structurally represented but not exercised by a sparse real history dataset.

## Models And Validation

Models implemented:

- raw market midpoint baseline
- logistic regression
- `HistGradientBoostingClassifier`
- fallback market-anchored ensemble average
- Platt calibration for the current small held-out sample

Final audit run:

```text
model id: be58e263a53276ef4ef7137c
status after manual approval: approved_for_paper
calibration: platt
validation predictions: 16
Brier: 0.18277652680543502
market baseline Brier: 0.13011874999999998
log loss: 0.5577834214698962
ROC AUC: 1.0
calibration error: 0.42752248001058146
```

Best out-of-sample model by Brier score:

- Raw market baseline, not the ensemble.

Do not interpret the fixture model as profitable or superior. Accuracy/ROC AUC is not sufficient
for approval.

## Category Routing Findings

Bug fixed during audit:

- Category-specific training requests with only 8 snapshots were falling back to the general
  dataset but still registering as the requested category.
- Fixed: under-sampled category requests register as `general`, with requested/effective category
  and fallback reason stored in metadata.

Verified current fixture behavior:

```text
politics -> registered_category general
economics -> registered_category general
crypto -> registered_category general
sports -> registered_category general
technology -> registered_category general
general -> registered_category general
```

## Calibration And Ensemble Findings

- Current held-out sample uses Platt calibration.
- Isotonic calibration path exists for larger held-out samples.
- Calibration table is stored in model metadata.
- Ensemble fallback weights are explicit and stored because the fixture sample is too small for a
  robust trained stacker.

Limitations:

- Category/exchange/time-to-resolution-specific calibrators are not fully implemented.
- No calibration plot image is generated; calibration tables are stored.

## Uncertainty Findings

Implemented uncertainty components:

- component/model disagreement
- spread
- data freshness
- missing-feature count

Not implemented:

- bootstrap variance
- training-distribution distance
- sample-density model
- cross-validation variance beyond stored validation predictions

Confidence and uncertainty are bounded and displayed, but are not statistical guarantees.

## Expected-Value And Position-Sizing Findings

Model opportunity engine is separate from deterministic arbitrage. It calculates:

- direction
- executable quantity
- weighted average entry price
- gross expected value
- fees
- slippage
- uncertainty buffer
- net expected value
- expected ROI
- confidence/uncertainty
- freshness

Position sizing uses fractional Kelly with conservative caps:

- 0.5% normal model trade cap
- 1% highest-confidence cap
- 2% event exposure setting
- 5% category exposure setting

Limitations:

- Per-event, category, correlated exposure, and daily loss limits are configured but not fully
  enforced across a portfolio ledger.
- Market-too-close-to-resolution and out-of-distribution no-trade checks are limited.

## Model Registry Findings

Verified:

- candidate registration
- manual approval to `approved_for_paper`
- retirement
- missing model 404
- invalid payload 422
- prediction generation only after approval
- metadata persistence after restart
- artifact path validation inside configured registry
- reproducibility command

Reproducibility result:

```text
reproduced_from=be58e263a53276ef4ef7137c
new_model_id=6d80dc6c14df31cb50a16425
status=candidate
seed=42
original Brier: 0.18277652680543502
reproduced Brier: 0.18277652680543527
```

Limitations:

- Duplicate version prevention is not strict; model IDs are timestamp-derived.
- Rejection status exists in the enum but no reject route is exposed.
- Model-management endpoints are local administrative endpoints without authentication.

## Paper-Trading Findings

Verified:

- Phase 2 arbitrage paper trades are labeled `PAPER TRADING`.
- Phase 3 model trades are labeled `MODEL PAPER TRADE`.
- Model trade records include prediction ID, model ID, model version, calibration version,
  direction, entry price, quantity, position size, expected edge, mark-to-market P&L, and realized
  P&L fields.
- Model paper P&L is reported separately from arbitrage P&L.

Limitations:

- The Phase 3 fixture workflow creates an open model paper trade and mark-to-market P&L.
- Close/resolve fixture position, hold-until-resolution, fair-value exit, stop-loss, prediction
  reversal, and settlement-risk exit logic are not fully implemented.
- Therefore the requested 27-step workflow does not fully pass through step 21.

## Analytics Findings

Verified:

- model prediction count
- model opportunity count
- model paper trade count
- probability buckets
- category breakdown
- cumulative model paper P&L
- return on deployed paper capital
- win rate
- average edge at entry
- max drawdown
- sample-size warning
- explicit `arbitrage_pnl_excluded`

Limitations:

- Date/category/ROI/liquidity/freshness filters for model analytics are not exposed.
- Risk-adjusted metrics are minimal.
- Time-to-resolution and confidence/uncertainty bucket analytics are incomplete.

## Frontend Findings

Frontend verified:

```text
GET /                200
GET /models          200
GET /market-matches  200
```

Rendered HTML included:

- `Prediction Models`
- `MODEL PREDICTION`
- `MODEL PAPER TRADE`
- `SIMULATION`

Frontend dev log showed successful rendering for checked pages and no failed API requests during
the audit checks.

Limitations:

- Browser console was not inspected with Playwright/DevTools.
- There are no separate pages for training-run detail, model comparison detail, calibration plots,
  resolved model trades, or full model analytics drilldowns. `/models` is a combined dashboard.

## Security Findings

Search results:

- No wallet code found.
- No seed phrase handling found.
- No live order endpoint implementation found.
- No deposit/withdrawal implementation found.
- No hardcoded private API secrets found.
- `KALSHI_PRIVATE_KEY_PATH` exists only as optional server-side config for Kalshi WebSocket auth
  fallback; it is not returned to frontend APIs.

Safety limitations:

- Model-management routes are writable and unauthenticated. They are acceptable only for local
  administrative use and should not be exposed to untrusted networks.
- Production error-response hardening was not deeply tested beyond normal FastAPI 404/422/400
  behavior.

## Performance Findings

Local fixture API probe:

```text
POST /models/dataset average 0.1496s, max 0.3249s
POST /predictions/generate average 0.0642s, max 0.2164s
POST /model-opportunities/generate average 0.0353s, max 0.0442s
POST /model-paper-trades/run average 0.0438s, max 0.0498s
GET /model-analytics average 0.0062s, max 0.0066s
```

Limitations:

- Training is synchronous inside API requests and can block the request worker on larger datasets.
- Model artifacts are loaded on prediction generation rather than cached.
- No long-running memory-leak soak test was performed.
- Pagination exists for some list routes but not all model analytics surfaces.

## Bugs Found And Fixed

1. SQLite financial persistence used floating-point/raw default `Numeric` behavior.
   - Fixed with `DecimalValue`.
   - Added regression test.

2. SQLite timezone persistence returned naive datetimes.
   - Fixed with `UtcDateTimeValue`.
   - Added regression test and updated history tests.

3. Under-sampled category model training registered fallback general models under the requested
   category.
   - Fixed effective category registration and metadata.
   - Added regression test.

4. Missing approved model artifact produced raw `FileNotFoundError`.
   - Fixed artifact path validation and clear `ValueError`/400 API behavior.
   - Added regression test.

## Test Results

Backend:

```text
pytest: 52 passed, 0 failed, 0 skipped, 47 warnings, 15.45s
ruff: all checks passed
mypy: success, 32 source files
```

Frontend:

```text
npm run lint: passed
npm run typecheck: passed
npm test: passed
npm run build: passed
```

Warnings:

- Pydantic v2 `json_encoders` deprecation warnings.
- FastAPI/Starlette TestClient deprecation warning.
- scikit-learn/joblib CPU-count warning on this Mac.

Tests requiring live services:

- The automated suite uses fixtures/simulation.
- Live exchange checks were run manually during the audit.

## Full Phase 3 Workflow Result

Completed:

1. Clean DB started.
2. Backend started.
3. Frontend started.
4. Fixture markets loaded.
5. Historical fixture dataset built.
6. Market baseline evaluated.
7. Logistic regression trained.
8. Gradient-boosted model trained.
9. Chronological grouped validation run.
10. Out-of-sample validation predictions generated.
11. Platt calibration applied.
12. Fallback ensemble applied.
13. Compared against market baseline.
14. Candidate model registered.
15. Model manually approved.
16. Current fixture predictions generated.
17. Positive EV opportunity detected.
18. Position sized.
19. Model paper trade created.
20. Mark-to-market P&L recorded.
22. Analytics updated.
23. Backend restarted.
24. Model, predictions, trade, analytics persisted.
25. Frontend displayed Phase 3 results.

Not completed:

- Step 21: close or resolve fixture model trade. The current implementation records open model
  paper trades but does not implement full exit/resolution workflow.

Latest successful prediction timestamp:

```text
2026-07-21T23:34:11.924465Z
```

Latest model paper trade timestamp:

```text
2026-07-21T23:34:12.047884Z
```

## Remaining Failures And Limitations

- Not ready for several weeks of model-based paper-trading observation as a research signal.
- Current historical dataset is deterministic fixture data, not sufficient resolved live history.
- Ensemble underperforms market baseline on Brier score in fixture validation.
- Long-running live WebSocket loops/watchdogs are incomplete.
- Health route lacks last-successful scan timestamps and degraded/offline/historical state.
- Model trade exit/resolution logic is incomplete.
- Model-management routes lack authentication.
- Category-specific models/calibrators need more data before meaningful use.
- External data and LLM forecaster interfaces are not implemented/enabled.

## Recommended Observation Period

Collect several weeks to months of resolved live market snapshots before treating model-based paper
trading metrics as meaningful. Require category-specific sample sizes, stable calibration buckets,
and out-of-sample performance better than executable market baselines before Phase 4.

## Criteria For Proceeding To Phase 4

- Real resolved historical dataset, not only fixtures.
- No leakage test failures.
- Model beats market midpoint and executable-price baselines out of sample.
- Calibration error improves with adequate sample sizes.
- Full model trade lifecycle including exits/resolution is implemented.
- Local admin endpoints are protected before any network exposure.
- Continued explicit separation of arbitrage, model, and simulation results.
