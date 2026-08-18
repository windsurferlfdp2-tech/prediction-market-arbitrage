# Next Model Steps

Audit date: 2026-08-03

## Safety State

Model paper trading is paused and must remain paused. Verification:

- `GET /model-analytics` returned `model_paper_trading_paused: true`.
- `POST /model-paper-trades/run?data_mode=live` returned HTTP 400 with `MODEL PAPER TRADING PAUSED`.
- No live-money trading, wallet signing, deposits, withdrawals, or live order submission were added.
- Deterministic arbitrage scanning was not changed.
- Historical losing trades and prediction records were preserved.

## Bugs Found

- Previous model redevelopment work left one `candidate` model available for research predictions even though it did not meet evidence requirements. This was not paper-approved, but the current instruction required retiring every model without valid chronological out-of-sample evidence.
- No duplicate model-registry rows were present in the current database.
- No confirmed settlement arithmetic bug was found in the historical model paper trades.
- No confirmed label inversion was found.
- No confirmed class-order reversal was found in the stored artifact, but the code previously had unsafe class-column assumptions. That was already fixed and is now covered by tests.

## Bugs Fixed

- Retired all models lacking valid chronological out-of-sample evidence:
  - `f03c9c31759e786990f3057d`
  - `e744ed9f1c0fa120e01fee99`
- Confirmed deterministic training fingerprints are stored and duplicate registration is guarded by the application.
- Created a SQLite backup before retirement changes:
  - `backend/prediction_market_arb.db.next-model-backup-20260803T204700Z`

## Direction Pipeline Status

Verified by deterministic tests:

- Historical labels use `YES = 1`, `NO = 0`.
- `predict_proba` explicitly maps class label `1` to YES.
- `classes_ = [0, 1]` and `classes_ = [1, 0]` both map correctly.
- Missing class `0`, missing class `1`, and incompatible artifacts fail safely.
- Platt calibration preserves the positive-class direction.
- Strong YES edge creates BUY_YES.
- Strong NO edge creates BUY_NO.
- Neither side trades when both EV values are negative.
- BUY_NO uses `1 - calibrated_yes_probability`.
- Selected side matches the greater positive net EV.
- Exchange outcome mapping and paper settlement are covered for YES/NO, partial fill, voided market, postponed market, repeated reconciliation, and no settlement based solely on last price.

Current conclusion: the YES/NO pipeline is correct under deterministic tests.

## Stored Prediction Audit

Current local database:

- Stored model predictions: 237
- Predictions above 50% YES: 4.22%
- BUY_YES model opportunities: 21
- BUY_NO model opportunities: 0
- No-trade predictions: 222

Interpretation:

- The model did not generally predict YES above 50%.
- Historical BUY_YES concentration came from cheap YES prices plus weak expected-value/calibration behavior, not from a universal >50% YES probability distribution.
- BUY_NO is reachable in deterministic tests, but no stored historical model opportunity selected BUY_NO.

## Registry Cleanup

Duplicate cleanup dry-run:

- Duplicate groups: 0
- Duplicate model rows: 0
- References requiring reassignment: 0
- Unique actual models before final retirement: 2

Canonical records:

| model ID | status | reason |
|---|---|---|
| `f03c9c31759e786990f3057d` | retired | prior failed approved model, worse than market baseline, insufficient sample |
| `e744ed9f1c0fa120e01fee99` | retired | candidate only, failed approval checks, insufficient sample |

No rows were deleted. Foreign-key relationships to predictions, opportunities, and trades were preserved.

## Dataset Readiness

Historical resolved-market snapshot dataset:

- Prediction rows: 48
- Unique markets: 24
- Unique resolved markets: 24
- YES outcomes: 24
- NO outcomes: 24
- Training date range: 2026-01-24T06:00:00Z to 2026-02-18T06:00:00Z
- Snapshots per market: exactly 2 for each market

Resolved rows by category:

- politics: 8
- economics: 8
- crypto: 8
- sports: 8
- technology: 8
- general: 8

Exchange distribution:

- Polymarket: 24
- Kalshi: 24

## Chronological Splits

Grouped chronological split:

| split | rows | unique markets | timestamp range |
|---|---:|---:|---|
| train | 28 | 14 | 2026-01-24T06:00:00Z to 2026-02-08T06:00:00Z |
| calibration | 10 | 5 | 2026-02-07T06:00:00Z to 2026-02-13T06:00:00Z |
| final test | 10 | 5 | 2026-02-12T06:00:00Z to 2026-02-18T06:00:00Z |

All snapshots from one market remain in one split. No random row-level split is used.

## Market Baseline Metrics

Raw market-price baseline on resolved final-test markets:

- Final-test rows: 10
- Final-test markets: 5
- Brier score: 0.13183
- Log loss: 0.451060443805296
- Calibration error: 0.36300000000000004

## Current Model Evidence

The most recent candidate ensemble failed against the raw market baseline:

- Ensemble Brier: 0.18203483558419545
- Ensemble log loss: 0.5527036724935529
- Ensemble calibration error: 0.4181073762876494
- Brier improvement versus baseline: -0.05020483558419545
- Log-loss improvement versus baseline: -0.1016432286882569

Logistic regression looked better than baseline on the tiny final test:

- Logistic Brier: 0.1037357506964753
- Logistic log loss: 0.3837376802035589
- Logistic calibration error: 0.3155698358153102

This is not enough evidence to resume training or approve paper trading because the final test has only 5 unique markets.

Gradient boosting was not eligible:

- Required unique training markets: 30
- Available unique training markets: 14

## Missing Data Requirements

Training should not resume until the configured minimum unique-market requirements are met:

- At least 100 unique resolved training markets.
- At least 30 unique calibration/validation markets.
- At least 30 unique final-test markets.
- No market ID overlap between train, calibration, and final test.
- Calibration error no greater than 0.05.
- Brier improvement over raw market baseline of at least 0.01.
- Log-loss improvement over raw market baseline of at least 0.01.
- Valid post-fix paper simulation evidence with at least 100 trades.
- Paper drawdown within configured limits.
- Explicit manual approval after review.

## Tests Run

- `cd backend && .venv/bin/pytest tests/test_prediction_phase3.py tests/test_position_reconciliation.py -q`
  - 46 passed, 0 failed, 48 warnings
- `cd backend && .venv/bin/pytest tests/test_model_registry_cleanup.py -q`
  - 1 passed, 0 failed
- `cd backend && .venv/bin/pytest -q`
  - 105 passed, 0 failed, 48 warnings
- `cd backend && .venv/bin/ruff check .`
  - passed
- `cd backend && .venv/bin/mypy app tests`
  - passed on 39 source files
- `cd frontend && npm run test`
  - 12 passed, 0 failed
- `cd frontend && npm run lint`
  - passed
- `cd frontend && npm run build`
  - passed

Warnings:

- Pydantic V2 `json_encoders` deprecation warning.
- Starlette/httpx TestClient deprecation warning.
- joblib physical-core detection warning.

## Criteria Before Training Resumes

Do not train a new model until the dataset readiness endpoint shows enough resolved markets:

```bash
curl http://127.0.0.1:8000/models/readiness
```

Training may resume only when:

- `unique_resolved_markets >= 100`
- calibration split has at least 30 unique markets
- final-test split has at least 30 unique markets
- splits have `market_overlap: false`
- only resolved markets are included

Even after training resumes, do not approve a model for paper trading unless it beats the raw market baseline on the untouched final chronological test set and passes every approval check.

