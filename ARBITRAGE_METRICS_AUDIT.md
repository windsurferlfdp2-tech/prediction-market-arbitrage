# Arbitrage Metrics Audit

Audit date: 2026-07-22 UTC

## Root Cause

The dashboard values were not genuine current live arbitrage metrics.

Three issues combined:

1. The analytics endpoint returned all historical opportunity rows for a data mode, and the frontend summed every day in `opportunities_detected_per_day` under the label "Detected today".
2. The detector allowed same-exchange books to be paired when they shared a `same_market_key`. The stale live records were Kalshi YES/NO combinations across different threshold contracts in the same Kalshi event, not manually verified Polymarket/Kalshi equivalent markets.
3. Active opportunity duration used wall-clock time for still-active rows, so stale records could keep aging even when no fresh executable book updates arrived.

Paper-trading analytics were also being merged into explicit live arbitrage analytics. That has been separated so live arbitrage totals do not include simulated paper-trading summaries.

## Freshness Findings

Current UTC server time captured: `2026-07-22T00:46:50.743632+00:00`

Latest verified live scan after fixes:

| Field | Value |
| --- | --- |
| Latest completed scan | `2026-07-22T00:47:25.785129Z` |
| Latest Polymarket market fetch | `2026-07-22T00:46:05.335297Z` |
| Latest Kalshi market fetch | `2026-07-22T00:46:05.749565Z` |
| Latest order-book update | `null` |
| Latest current live opportunity | `null` |
| Markets checked | 50 |
| Verified pairs checked | 0 |
| Books checked | 0 |
| Opportunities found | 0 |

No order books were used in the displayed corrected live analytics because there were no manually verified live pairs to fetch books for. Therefore, no order-book ages contributed to corrected live metrics.

The stale dashboard records were based on `2026-07-20` data:

| Field | Value |
| --- | --- |
| Maximum live opportunity `detected_at` in SQLite | `2026-07-20 16:09:39.237570` |
| Maximum live opportunity `last_seen_at` in SQLite | `2026-07-20T22:09:39.257117Z` |
| Current UTC-day live opportunity rows | 0 |
| Current local-day live opportunity rows (`America/Costa_Rica`) | 0 |
| Historical live rows excluded from corrected current-day analytics | 243 |

## Scanner Loop Findings

The scanner is request/WebSocket driven in this implementation, not a continuously running daemon loop. It now records and exposes structured scan status:

- scan start time
- scan completion time
- markets checked
- books checked
- verified pairs checked
- opportunities found
- scan duration
- last error

Structured logs were added for `scanner_scan_start`, `scanner_scan_complete`, and `scanner_scan_error`.

Two consecutive live scan cycles completed after the fix:

| Scan | Completed | Markets | Books | Opportunities |
| --- | --- | ---: | ---: | ---: |
| 1 | `2026-07-22T00:46:05.788691Z` | 50 | 0 | 0 |
| 2 | `2026-07-22T00:47:25.785129Z` | 50 | 0 | 0 |

## Live, Simulation, Fixture, Historical Separation

Corrected live analytics now use:

- `analytics_data_type=live`
- `analytics_scope=current_utc_day`
- `latest_scan_timestamp`
- `latest_record_seen_timestamp`
- `historical_records_excluded`
- `simulated_records_excluded`
- `unique_opportunities`
- `raw_detections`
- `duplicate_updates`
- `active_opportunities`

Live analytics no longer merge paper-trading analytics. Simulation analytics remain clearly labeled as simulation/PAPER TRADING where applicable.

## Database Findings

SQLite database inspected: `backend/prediction_market_arb.db`

| Metric | Value |
| --- | ---: |
| Total opportunity history rows | 246 |
| Live rows | 243 |
| Simulation rows | 3 |
| Current UTC-day live rows | 0 |
| Current local-day live rows | 0 |
| Historical live unique pair group count | 241 |
| Duplicate live groups found | 1 |

Duplicate group found:

| same_market_key | YES exchange | NO exchange | YES price | NO price | Quantity | ROI | Rows |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `KXSILVERH-26JUL2014` | kalshi | kalshi | 0.16 | 0.83 | 500 | 0.010101010101010102 | 2 |

## 38.89% Median ROI Investigation

Records contributing to `38.89%` ROI were stale live rows from `2026-07-20`, all with `yes_exchange=kalshi` and `no_exchange=kalshi`.

Example records:

| ID | YES market | NO market | YES price | NO price | Combined cost | Quantity | Net edge | ROI | Book age |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 98 | `KXSILVERH-26JUL2014-T57.199` | `KXSILVERH-26JUL2014-T56.849` | 0.48 | 0.24 | 0.72 | 500 | 140 | 0.3888888888888889 | 17.541462 |
| 99 | `KXSILVERH-26JUL2014-T57.149` | `KXSILVERH-26JUL2014-T56.749` | 0.54 | 0.18 | 0.72 | 500 | 140 | 0.3888888888888889 | 17.541462 |
| 113 | `KXSILVERH-26JUL2014-T57.399` | `KXSILVERH-26JUL2014-T57.099` | 0.27 | 0.45 | 0.72 | 500 | 140 | 0.3888888888888889 | 17.541462 |
| 118 | `KXSILVERH-26JUL2014-T57.649` | `KXSILVERH-26JUL2014-T57.249` | 0.10 | 0.62 | 0.72 | 500 | 140 | 0.3888888888888889 | 17.541462 |
| 124 | `KXSILVERH-26JUL2014-T57.549` | `KXSILVERH-26JUL2014-T57.199` | 0.16 | 0.56 | 0.72 | 500 | 140 | 0.3888888888888889 | 17.541462 |

Conclusion: the median ROI was not a valid current cross-platform arbitrage metric. It came from incompatible same-exchange Kalshi threshold-market pairings and stale historical records.

## Maximum Theoretical Profit Investigation

The `$385` row was:

| Field | Value |
| --- | --- |
| ID | 223 |
| Title | Will the SILVER close price be above 56.749 USD/ounce on July 20, 2026 at 2:00 PM ET? |
| YES exchange | kalshi |
| NO exchange | kalshi |
| YES market | `KXSILVERH-26JUL2014-T57.849` |
| NO market | `KXSILVERH-26JUL2014-T56.749` |
| YES price | 0.05 |
| NO price | 0.18 |
| Combined cost | 0.23 |
| Quantity | 500 |
| Net edge | 385 |
| ROI | 3.347826086956522 |
| Detected | `2026-07-20 16:09:37.861520` |

Conclusion: `$385` was not executable cross-platform arbitrage. It was an old Kalshi-vs-Kalshi threshold mismatch.

## Price Conversion Findings

No evidence was found that the `38.89%` median ROI came from a cents-to-dollars double conversion. Current detector logic now rejects prices outside the binary 0 to 1 range before evaluation.

The primary pricing error was semantic: the engine compared YES and NO legs from different Kalshi threshold contracts under the same event key. The detector now refuses same-exchange pairings, so deterministic arbitrage requires cross-exchange books.

## Duration Findings

The `271.89` second duration was based on historical rows from `2026-07-20`. Duration now uses the persisted executable lifecycle duration for active rows instead of increasing merely because wall-clock time has passed.

Required lifecycle behavior implemented for this fix:

- unchanged repeated scans update an existing active row instead of creating a new row
- opportunities absent from a refresh are closed with `not_present_in_latest_scan`
- current-day analytics exclude historical active rows
- stale books are already rejected by the detector before opportunity calculation

## Frontend Findings

The frontend API client already used `cache: "no-store"`. The incorrect dashboard value came from display logic plus backend analytics scope, not an indefinite frontend fetch cache.

Frontend changes made:

- dashboard now labels current-day metrics as UTC
- dashboard displays scanner status
- dashboard displays last scan and last DB record separately
- dashboard displays raw detections, unique opportunities, duplicate updates, historical exclusions, and simulation exclusions
- TypeScript API client includes `/scanner/status`

Runtime note: `npm run build` passed. A stale Next dev process was found and stopped; a fresh Next dev process reported ready on port 3001 and `lsof` showed Node listening, but `curl` from the tool sandbox could not connect to port 3001. I did not claim browser-level refresh verification.

## Files Changed In This Fix Pass

- `backend/app/arbitrage/detector.py`
- `backend/app/main.py`
- `backend/app/services/history.py`
- `backend/app/services/scanner.py`
- `backend/tests/test_arbitrage.py`
- `backend/tests/test_history.py`
- `frontend/app/components/OpportunityDashboard.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `ARBITRAGE_METRICS_AUDIT.md`

The repository also contains prior Phase 1-3 modified/untracked files not created by this specific audit pass.

## Tests And Checks Run

| Command | Result |
| --- | --- |
| `pytest tests/test_arbitrage.py tests/test_history.py` | 18 passed |
| `pytest` | 55 passed, 47 warnings |
| `pytest tests/test_api.py tests/test_simulation_mode.py tests/test_arbitrage.py tests/test_history.py` | 29 passed |
| `pytest tests/test_api.py tests/test_history.py` | 11 passed |
| `ruff check .` | passed |
| `mypy app tests` | passed |
| `npm run typecheck` | passed |
| `npm run lint` | passed |
| `npm run build` | passed |

Remaining warnings:

- Pydantic V2 `json_encoders` deprecation warnings
- Starlette `TestClient` deprecation warning
- joblib CPU-count warning in the full backend suite

## Corrected Current Live Metrics

As of `2026-07-22T00:47:34.085463Z`:

| Metric | Corrected live value |
| --- | ---: |
| Detected today UTC | 0 |
| Unique today | 0 |
| Raw detections | 0 |
| Duplicate updates | 0 |
| Active opportunities | 0 |
| Median duration | 0 seconds |
| Median ROI | 0% |
| Maximum theoretical profit | $0 |
| Longer than 1 second | 0% |
| Longer than 3 seconds | 0% |
| Longer than 5 seconds | 0% |
| Longer than 10 seconds | 0% |
| Historical records excluded | 243 |
| Simulated records excluded | 0 |

## Remaining Limitations

- The live scanner currently has zero manually verified live cross-platform pairs, so it fetches live markets but does not fetch live order books for arbitrage evaluation.
- Scanner execution is request/WebSocket driven, not a continuous daemon background loop.
- The paper-trade table does not store `data_mode`; live analytics now avoid merging paper analytics instead of backfilling a migration.
- Browser-level frontend refresh was not verified from the tool environment because `curl` could not connect to the fresh Next dev listener despite `lsof` showing the port open.

## Next Commands

Backend:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=simulation
export USE_FIXTURES=false
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
export NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
export NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws/opportunities
npm run dev
```

Useful live checks:

```bash
curl -sS 'http://127.0.0.1:8000/health?data_mode=live'
curl -sS 'http://127.0.0.1:8000/opportunities?data_mode=live'
curl -sS 'http://127.0.0.1:8000/scanner/status?data_mode=live'
curl -sS 'http://127.0.0.1:8000/analytics/opportunities?data_mode=live'
```
