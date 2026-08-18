# Model Redevelopment Readiness

Audit date: 2026-08-03

## Safety status

Model paper trading remains frozen. The backend is running with `MODEL_PAPER_TRADING_ENABLED=false`, and `POST /model-paper-trades/run?data_mode=live` returns:

`MODEL PAPER TRADING PAUSED. Emergency Phase 3 audit: model paper trading paused after poor observed performance.`

Live market ingestion, deterministic arbitrage scanning, prediction generation, and resolution collection were not disabled. Real-money trading, wallet signing, deposits, withdrawals, and live order submission remain absent.

## Direction Pipeline Status

The YES/NO direction pipeline now has deterministic coverage for:

- class ordering `[0, 1]`
- class ordering `[1, 0]`
- missing class `0`
- missing class `1`
- string class labels
- incompatible saved artifacts
- BUY_YES selection
- BUY_NO selection
- no-trade when both sides are negative EV
- selecting the higher net EV side
- settlement of YES and NO outcomes

The implementation explicitly maps class label `1` to YES and class label `0` to NO. The model opportunity engine evaluates YES and NO independently using executable side-specific prices, quantities, fees, slippage, uncertainty buffer, net EV, and ROI.

## Registry Cleanup Results

Duplicate model cleanup dry-run:

- Duplicate groups: 0
- Duplicate model rows: 0
- Unique actual models: 2
- References requiring reassignment: 0
- Cleanup apply: not needed

Model registry after remediation:

| model ID | status | rows | resolved markets | final/validation rows | baseline Brier | model Brier | calibration |
|---|---|---:|---:|---:|---:|---:|---|
| `f03c9c31759e786990f3057d` | retired | 48 | 24 | 16 | 0.13011875 | 0.18277653 | platt |
| `e744ed9f1c0fa120e01fee99` | candidate | 48 | 24 | 10 | 0.13183 | 0.19870731 | platt |

The previously approved model `f03c9c31759e786990f3057d` was retired through the existing API. Its row, artifact metadata, predictions, opportunities, paper trades, losses, and audit history were preserved.

The new model `e744ed9f1c0fa120e01fee99` was registered only as a candidate so live research predictions can continue. It was not approved.

## Dataset Readiness

Historical snapshot dataset:

- Total prediction rows: 48
- Unique markets: 24
- Unique resolved markets: 24
- YES rows: 24
- NO rows: 24
- Oldest prediction timestamp: 2026-01-24T06:00:00Z
- Newest prediction timestamp: 2026-02-18T06:00:00Z
- Snapshots per market: min 2, median 2, max 2

Category distribution:

- politics: 8
- economics: 8
- crypto: 8
- sports: 8
- technology: 8
- general: 8

Exchange distribution:

- Polymarket: 24
- Kalshi: 24

## Chronological Split Definitions

Grouped chronological split, with no market ID overlap:

| split | rows | unique markets | start | end |
|---|---:|---:|---|---|
| train | 28 | 14 | 2026-01-24T06:00:00Z | 2026-02-08T06:00:00Z |
| calibration | 10 | 5 | 2026-02-07T06:00:00Z | 2026-02-13T06:00:00Z |
| final test | 10 | 5 | 2026-02-12T06:00:00Z | 2026-02-18T06:00:00Z |

All snapshots from a market remain in one split. No random row-level split is used.

## Market Baseline Metrics

Raw market baseline on the untouched final chronological test set:

- Final-test rows: 10
- Final-test markets: 5
- Brier score: 0.13183
- Log loss: 0.451060443805296
- Calibration error: 0.36300000000000004
- Final-test outcomes: 4 YES, 6 NO

## Model Comparison

All comparisons below use the untouched final chronological test set.

| model | trained | Brier | log loss | calibration error | final-test markets | result |
|---|---|---:|---:|---:|---:|---|
| raw market baseline | yes | 0.13183 | 0.45106044 | 0.36300000 | 5 | baseline |
| logistic regression | yes | 0.10373575 | 0.38373768 | 0.31556984 | 5 | better than baseline, but sample too small |
| category gradient boosting | no | n/a | n/a | n/a | n/a | insufficient unique training markets |
| calibrated market-anchored ensemble | yes | 0.18203484 | 0.55270367 | 0.41810738 | 5 | worse than baseline |

The candidate registered in the model registry is the market-anchored ensemble. It does not beat the market baseline and is not eligible for approval.

## Calibration Results

Market baseline calibration table:

| bucket | count | avg predicted | actual rate | gap |
|---|---:|---:|---:|---:|
| 30-40 | 6 | 0.36333333 | 0.0 | 0.36333333 |
| 60-70 | 4 | 0.63750000 | 1.0 | -0.36250000 |

Logistic regression calibration table:

| bucket | count | avg predicted | actual rate | gap |
|---|---:|---:|---:|---:|
| 20-30 | 6 | 0.26296167 | 0.0 | 0.26296167 |
| 60-70 | 4 | 0.60551791 | 1.0 | -0.39448209 |

Market-anchored ensemble calibration table:

| bucket | count | avg predicted | actual rate | gap |
|---|---:|---:|---:|---:|
| 30-40 | 6 | 0.34873233 | 0.0 | 0.34873233 |
| 40-50 | 4 | 0.47783005 | 1.0 | -0.52216995 |

The calibration sample is too small to support paper-trading approval.

## Paper Simulation Results

No new model paper trades were created. Historical model paper trades were preserved.

Approval checks intentionally require paper drawdown and paper-trade sample evidence before a model can be approved. Current candidate status:

- Paper simulation drawdown: not available from a valid post-fix simulation
- Valid model paper-trade sample size: 0
- Result: failed approval checks

## Approval Checks

Current approval requirements and candidate result:

| check | required | actual | status |
|---|---:|---:|---|
| minimum unique resolved training markets | 100 | 24 | failed |
| minimum unique validation markets | 30 | 5 | failed |
| minimum unique final-test markets | 30 | 5 | failed |
| maximum calibration error | 0.05 | 0.4181073762876494 | failed |
| required Brier improvement | 0.01 | -0.05020483558419545 | failed |
| required log-loss improvement | 0.01 | -0.1016432286882569 | failed |
| maximum paper drawdown | 0.05 | not available | failed |
| minimum paper-trade sample size | 100 | 0 | failed |
| no random row-level split | true | true | passed |

No model is eligible for manual paper approval.

## Live Research Prediction Check

After retiring the unsafe approved model, a new candidate model generated live research predictions successfully. The latest generated prediction timestamp observed during this audit was `2026-08-03T20:40:07.633141Z`.

Every generated live prediction included `model_not_approved_for_paper`, so it can be recorded for research while remaining ineligible for paper execution.

## Files Changed

- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/services/prediction.py`
- `backend/tests/test_prediction_phase3.py`
- `frontend/app/models/ModelDashboardClient.tsx`
- `frontend/app/models/page.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `MODEL_REDEVELOPMENT_READINESS.md`

Database changes:

- Retired model `f03c9c31759e786990f3057d`.
- Registered candidate model `e744ed9f1c0fa120e01fee99`.
- Preserved historical predictions, opportunities, paper trades, losses, and audit reports.
- No duplicate registry cleanup was applied because dry-run found no duplicate groups.

## Commands Run

- `cd backend && .venv/bin/python -m app.tools.cleanup_duplicate_models --dry-run`
- `curl -sS -X POST http://127.0.0.1:8000/models/f03c9c31759e786990f3057d/retire`
- `curl -sS -X POST http://127.0.0.1:8000/models/train -H 'Content-Type: application/json' -d '{"category":"general","data_mode":"live","model_type":"ensemble"}'`
- `curl -sS -X POST 'http://127.0.0.1:8000/predictions/generate?data_mode=live'`
- `curl -sS http://127.0.0.1:8000/models/readiness`
- `curl -sS -X POST 'http://127.0.0.1:8000/model-paper-trades/run?data_mode=live'`
- `cd backend && .venv/bin/pytest tests/test_prediction_phase3.py -q`
- `cd backend && .venv/bin/pytest -q`
- `cd backend && .venv/bin/ruff check .`
- `cd backend && .venv/bin/mypy app tests`
- `cd frontend && npm run test`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run typecheck`

## Test Results

- Backend focused prediction tests: 31 passed, 0 failed, 48 warnings.
- Backend full tests: 105 passed, 0 failed, 48 warnings.
- Backend ruff: passed.
- Backend mypy: passed on 39 source files.
- Frontend tests: 12 passed, 0 failed.
- Frontend lint: passed.
- Frontend typecheck: passed.
- Frontend production build: passed.

Warnings:

- Pydantic V2 `json_encoders` deprecation warning.
- Starlette/httpx TestClient deprecation warning.
- joblib physical-core detection warning.

## Remaining Data Requirements

Before any model can be considered for manual paper approval:

- At least 100 unique resolved training markets.
- At least 30 unique calibration/validation markets.
- At least 30 unique untouched final-test markets.
- Calibration error no greater than 0.05.
- Brier improvement over market baseline of at least 0.01.
- Log-loss improvement over market baseline of at least 0.01.
- A valid post-fix paper simulation sample of at least 100 trades.
- Paper drawdown within the configured limit.
- Manual approval after audit review.

Model paper trading must remain paused until those requirements are met.

