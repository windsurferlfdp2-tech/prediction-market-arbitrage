# YES Direction Failure Audit

Audit date: 2026-08-03

## Executive summary

Model paper trading remains paused. New model paper trades are disabled by default through `MODEL_PAPER_TRADING_ENABLED=false`; prediction generation, live market ingestion, resolution reconciliation, deterministic arbitrage scanning, and historical recording remain enabled.

The local database contains 26 model paper trades. All 26 selected `yes`. Of the 16 resolved trades, 15 resolved `no` and lost, and 1 resolved `yes` and won. The remaining 10 are open legacy/simulation-labeled technology trades and are excluded from resolved win-rate calculations.

The repeated YES selection was not caused by a frontend default button or a database default. Stored predictions were not universally bullish: across 195 stored predictions, mean calibrated YES probability was 0.4521, median was 0.4665, and only 5.13% were above 0.50. The YES-only trades happened because generated model opportunities found low executable YES prices and treated them as positive EV under a weak calibrated model. The approved model had only 48 training rows, 24 unique resolved markets, Brier score 0.1828 versus raw-market baseline Brier 0.1301, and calibration error 0.4275. It should not have been paper-trading eligible.

## Controls applied

- New model paper trade creation remains paused.
- Model opportunities are research-only while the pause is active.
- Deterministic arbitrage paper trading was not changed.
- Historical predictions and trades were preserved; no losing trades were deleted or rewritten.
- The opportunity selector now evaluates both YES and NO using side-specific executable price, quantity, fees, slippage, uncertainty buffer, net EV, and ROI before selecting the higher positive EV side.
- Probability extraction now explicitly maps class label `1` to YES and class label `0` to NO for models and Platt calibration. It rejects missing or incompatible binary classes instead of assuming probability column 1 is YES.

## Resolved trade audit

Only 16 resolved model paper trades exist locally, so there are not 20 losing resolved trades to audit. All resolved trades are listed.

`est_no_px` is reconstructed from stored prediction market probability because old records did not preserve the unselected-side order-book execution trace. The selected YES side uses the persisted trade/opportunity values.

| trade | title | raw YES | calibrated YES | NO prob | YES px | est NO px | YES net EV | est NO net EV | side | outcome | realized P&L |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---:|
| b10aefcdbad925693a914605 | LIVE: Will over 6.5 goals be scored? | 0.25 | 0.4136991461541613 | 0.5863008538458387 | 0.07 | 0.75 | 541.5202360105086731600000000 | -358.2496492960619964400000000 | yes | no | -135.520000 |
| d101dc995a02b907544ca492 | LIVE: Will there be extra innings in Cleveland vs Cincinnati? | 0.25 | 0.3787847943565351 | 0.6212152056434649 | 0.11 | 0.905 | 562.4600967105324432900000000 | -698.5037047326937531100000000 | yes | no | -251.020000 |
| d9f3321397e25e7988c68bd5 | LIVE: SILVER above 59.449 on July 31, 2026 12:00 AM ET? | 0.25 | 0.36776638436486236 | 0.63223361563513764 | 0.06 | 0.955 | 584.7366969748363498900000000 | -704.7028150774507025100000000 | yes | no | -122.700000 |
| e08e6bc31ac67c5155c27911 | LIVE: SILVER above 59.399 on July 31, 2026 12:00 AM ET? | 0.25 | 0.36886224685123525 | 0.63113775314876475 | 0.07 | 0.95 | 565.3931838202372819375000000 | -697.8534058013148905625000000 | yes | no | -143.150000 |
| 923e3c40e91a09866310f81b | LIVE: SILVER above 59.349 on July 31, 2026 12:00 AM ET? | 0.25 | 0.37105802600832355 | 0.62894197399167645 | 0.08 | 0.94 | 549.2090337776705767625000000 | -682.1182925963727427375000000 | yes | no | -163.600000 |
| 772dc1772f9abb7a185cacca | LIVE: SILVER above 59.299 on July 31, 2026 12:00 AM ET? | 0.25 | 0.3732591459402122 | 0.6267408540597878 | 0.09 | 0.93 | 533.4028032853472515500000000 | -666.0271036101206464500000000 | yes | no | -184.050000 |
| 84d9f9786bbe19f92e3bd166 | LIVE: SILVER above 59.249 on July 31, 2026 12:00 AM ET? | 0.25 | 0.37767709324031984 | 0.62232290675968016 | 0.11 | 0.91 | 504.1899169261585655250000000 | -633.7746432094097867750000000 | yes | no | -224.950000 |
| fc358a51354686e519aa3957 | LIVE: SILVER above 59.449 on July 31, 2026 12:00 AM ET? | 0.25 | 0.36776638436486236 | 0.63223361563513764 | 0.06 | 0.955 | 585.1314862698363498900000000 | -704.3080257824507025100000000 | yes | no | -122.700000 |
| 4057f689f63ec68fd6749aaa | LIVE: SILVER above 59.399 on July 31, 2026 12:00 AM ET? | 0.25 | 0.36886224685123525 | 0.63113775314876475 | 0.07 | 0.95 | 565.7879731152372819375000000 | -697.4586165063148905625000000 | yes | no | -143.150000 |
| 287cb24ad084244099e7c17a | LIVE: SILVER above 59.349 on July 31, 2026 12:00 AM ET? | 0.25 | 0.37105802600832355 | 0.62894197399167645 | 0.08 | 0.94 | 549.6038230726705767625000000 | -681.7235033013727427375000000 | yes | no | -163.600000 |
| 0d145ee0978dea76ebd052a4 | LIVE: New York vs Las Vegas women's Pro Basketball over 200.5? | 0.25 | 0.39329633196902597 | 0.60670366803097403 | 0.17 | 0.84 | 557.79445963081010036458020 | -710.16464658461916356085180 | yes | yes | 2304.912324 |
| 48481c89e874311408d39813 | LIVE: SILVER above 59.449 on July 31, 2026 3:00 AM ET? | 0.25 | 0.36886224685123525 | 0.63113775314876475 | 0.07 | 0.95 | 565.8654540752372819375000000 | -697.3811355463148905625000000 | yes | no | -143.150000 |
| 045838ad10761c13c2a9ee8f | LIVE: SILVER above 59.399 on July 31, 2026 3:00 AM ET? | 0.25 | 0.37105802600832355 | 0.62894197399167645 | 0.08 | 0.94 | 549.6813040326705767625000000 | -681.6460223413727427375000000 | yes | no | -163.600000 |
| 30bf2ccf6dccb1c0b178c80a | LIVE: SILVER above 59.349 on July 31, 2026 3:00 AM ET? | 0.25 | 0.3732591459402122 | 0.6267408540597878 | 0.09 | 0.93 | 533.5075297803472515500000000 | -665.9223771151206464500000000 | yes | no | -184.050000 |
| c9d882907cafa88359588b38 | LIVE: SILVER above 59.249 on July 31, 2026 3:00 AM ET? | 0.25 | 0.37989376106435657 | 0.62010623893564343 | 0.12 | 0.9 | 488.5049855614666609350000000 | -617.6309014824758520150000000 | yes | no | -245.400000 |
| 741a2c8b60aaec2ca8879ae6 | LIVE: SILVER above 59.299 on July 31, 2026 3:00 AM ET? | 0.25 | 0.37767709324031984 | 0.62232290675968016 | 0.11 | 0.91 | 501.4691700701313691600000000 | -634.2301412827767764400000000 | yes | no | -224.950000 |

## Performance counts

- Total model predictions: 195
- Total model opportunities: 21
- Total attempted model paper trades: 26
- Filled trades: 26
- Resolved trades: 16
- Open trades: 10
- Wins among resolved trades: 1
- Losses among resolved trades: 15
- Voids: 0
- Win rate among resolved trades: 6.25%
- Total realized paper P&L: -310.677676
- Total unrealized paper P&L: 4.28417465666794404
- Return on deployed paper capital: -8.66%
- Direction count: YES 26, NO 0

## Class-probability mapping findings

Bug fixed: model and Platt calibration probability extraction previously depended on probability column position. The code now explicitly finds class label `1` for YES and class label `0` for NO. It supports numeric and string labels and fails safely when either binary class is missing.

No local artifact evidence proved that the stored losing trades were caused by reversed class columns; the active scikit-learn artifacts appear consistent with the generated probabilities. The old implementation was still unsafe and could silently reverse future artifacts with `classes_ = [1, 0]`.

## Label-encoding findings

The dataset uses `YES = 1` and `NO = 0`. The local training dataset contains 48 rows from 24 unique resolved markets with balanced labels: 24 YES rows and 24 NO rows. No confirmed label inversion was found in the stored dataset.

## Direction-selection findings

Before this audit, the model opportunity path could select direction from a side comparison that did not fully isolate side-specific executable quantity, fees, slippage, uncertainty buffer, net EV, and ROI. That is now fixed.

Current logic:

- YES net EV = calibrated YES probability - executable YES ask - fees - slippage - uncertainty buffer.
- NO net EV = `1 - calibrated YES probability` - executable NO ask - fees - slippage - uncertainty buffer.
- Both sides are evaluated.
- The side with the higher positive net EV is selected.
- No trade is produced when the selected side fails edge, ROI, liquidity, or freshness checks.
- The selected side is no longer implicitly YES.

## Model output distribution

Stored predictions do not show a universally YES-biased model:

- Prediction count: 195
- Mean calibrated YES probability: 0.4521
- Median calibrated YES probability: 0.4665
- Percentage above 0.50: 5.13%
- Percentage above 0.60: 0%
- Percentage above 0.70: 0%

Stored opportunities were YES-only because the model assigned enough probability to very cheap YES contracts to pass the expected-value filter, while the reconstructed NO executable price was high.

## Training-balance and approval findings

Active model:

- ID: `f03c9c31759e786990f3057d`
- Name: `phase3_market_anchored_ensemble`
- Version: `phase3-f03c9c31759e786990f3057d`
- Status in DB: `approved_for_paper`
- Training rows: 48
- Unique resolved markets: 24
- Validation rows: 16
- Unique validation markets: 8
- Training date range: 2026-01-24 to 2026-02-18
- Calibration: Platt
- Brier score: 0.18277652680543519
- Raw-market baseline Brier score: 0.13011874999999998
- Calibration error: 0.4275224800105817

This model should not have been approved for paper trading. It underperformed the market baseline and was trained/validated on too little data. Approval thresholds now require minimum unique resolved training markets, minimum validation markets, maximum calibration error, and improvement over the market baseline.

## Calibration findings

Platt calibration had a large calibration error of 0.4275. The calibration table shows sparse buckets and severe gaps:

- 40-50 bucket: count 8, average predicted 0.4275, actual rate 0.0
- 50-60 bucket: count 8, average predicted 0.5725, actual rate 1.0

Calibration class mapping now uses explicit positive-class lookup. The existing calibration quality is not acceptable evidence for paper trading.

## Inverse diagnostic

For the 16 resolved trades:

- Original side win rate: 6.25%
- Opposite side hypothetical win rate: 93.75%
- Original realized P&L: -310.677676
- Opposite-side hypothetical P&L: 310.677676, using simplified payout inversion

This is diagnostic only. No inverted strategy was deployed or approved. The result is consistent with a poor, poorly calibrated model and/or direction pipeline weakness, but it is not enough to prove a profitable inverse strategy.

## Historical preservation

No historical predictions or trades were deleted or rewritten. No realized P&L was corrected because settlement arithmetic matched the stored side/outcome for the resolved records. Old records remain limited by their original payload: they do not preserve the full unselected-side order-book execution trace.

## Code changes

- `backend/app/services/prediction.py`
  - Explicit class-label mapping for YES/NO probabilities.
  - Artifact validation for required model/calibration keys.
  - Side-specific model opportunity evaluation for YES and NO.
  - No-trade reasons now control paper eligibility.
  - Model paper trading remains paused by configuration unless explicitly re-enabled after audit.
- `backend/tests/test_prediction_phase3.py`
  - Added class-ordering tests for `[0, 1]` and `[1, 0]`.
  - Added missing-class and string-class tests.
  - Added incompatible artifact test.
  - Added Platt calibration class-label test.
  - Added BUY_YES, BUY_NO, no-trade, and greater-net-EV direction tests.

## Commands run

- `cd backend && .venv/bin/pytest tests/test_prediction_phase3.py -q`
- `cd backend && .venv/bin/ruff check app/services/prediction.py tests/test_prediction_phase3.py`
- `cd backend && .venv/bin/mypy app/services/prediction.py tests/test_prediction_phase3.py`
- `cd backend && .venv/bin/pytest -q`
- `cd backend && .venv/bin/ruff check .`
- `cd backend && .venv/bin/mypy app tests`
- `cd frontend && npm run test`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run typecheck`

## Test results

- Backend focused prediction tests: 29 passed, 0 failed, 48 warnings.
- Backend full tests: 103 passed, 0 failed, 48 warnings.
- Backend ruff: passed.
- Backend mypy: passed on 39 source files.
- Frontend tests: 12 passed, 0 failed.
- Frontend lint: passed.
- Frontend typecheck: passed.
- Frontend production build: passed.

Warnings observed:

- Pydantic V2 `json_encoders` deprecation warnings.
- Starlette/httpx TestClient deprecation warning.
- joblib physical-core detection warning.

## Criteria required before model paper trading resumes

- At least the configured minimum unique resolved training markets and validation markets.
- Grouped chronological validation with no market ID overlap between train and validation.
- Model Brier/log-loss/calibration must beat the raw market and executable-price baselines on out-of-sample data.
- Calibration error must be below the configured threshold.
- Direction tests must continue passing for BUY_YES and BUY_NO.
- A manual audit approval must be recorded; training completion alone must not approve a model.
- Model paper trading should resume only by explicitly setting `MODEL_PAPER_TRADING_ENABLED=true` after review.

