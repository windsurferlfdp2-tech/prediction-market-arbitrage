# Model Failure Audit

Audit date: 2026-08-03

## Emergency Freeze

Model paper-trade creation is now paused by default.

- Freeze enabled at: `2026-08-03T00:00:00Z`
- Setting: `MODEL_PAPER_TRADING_ENABLED=false`
- Reason: `Emergency Phase 3 audit: model paper trading paused after poor observed performance`
- Verified endpoint behavior: `POST /model-paper-trades/run?data_mode=live` returns HTTP 400 with
  `MODEL PAPER TRADING PAUSED`.

Preserved behavior:

- Live market ingestion remains available.
- Prediction generation remains available.
- Model opportunities remain visible for research.
- Model opportunities are labeled `NOT ELIGIBLE FOR PAPER EXECUTION` while paused.
- Deterministic arbitrage scanning and deterministic paper trading were not changed.
- Existing paper positions, losing trades, and audit history were not deleted.
- No live-money trading, wallets, signing, deposits, withdrawals, or real order submission were
  added.

## True Performance

Current local SQLite database:

- Total model predictions: 195
- Total model opportunities: 21
- Total attempted model paper trades: 26
- Total filled trades: 26
- Total resolved trades: 16
- Total open trades: 10
- Wins among resolved trades: 1
- Losses among resolved trades: 15
- Voids: 0
- Unresolved: 10
- Resolved win rate: 6.25%
- Resolved loss rate: 93.75%
- Average entry price: 0.2284615384615384615384615385
- Total realized paper P&L: -310.677676
- Total unrealized paper P&L: 4.28417465666794404
- Return on deployed paper capital: -8.660858532078804280344508988%
- Largest trade: 472.090476
- Largest loss: -251.02

The reported “approximately 90% losing” claim is directionally correct for resolved model paper
trades. The exact resolved loss rate in the local database is 15/16, or 93.75%.

Open positions are excluded from the resolved win-rate calculation.

## Results Breakdown

By model:

| Model ID | Trades | Resolved | Wins | Losses | P&L |
|---|---:|---:|---:|---:|---:|
| `f03c9c31759e786990f3057d` | 26 | 16 | 1 | 15 | -306.39350134333205596 |

By category:

| Category | Trades | Resolved | Wins | Losses | P&L |
|---|---:|---:|---:|---:|---:|
| technology | 10 | 0 | 0 | 0 | 4.28417465666794404 |
| sports | 1 | 1 | 0 | 1 | -135.52 |
| general | 2 | 2 | 1 | 1 | 2053.892324 |
| economics | 13 | 13 | 0 | 13 | -2229.05 |

By exchange:

| Exchange | Trades | Resolved | Wins | Losses | P&L |
|---|---:|---:|---:|---:|---:|
| polymarket | 10 | 0 | 0 | 0 | 4.28417465666794404 |
| kalshi | 16 | 16 | 1 | 15 | -310.677676 |

By direction:

| Direction | Trades | Resolved | Wins | Losses | P&L |
|---|---:|---:|---:|---:|---:|
| yes | 26 | 16 | 1 | 15 | -306.39350134333205596 |

No resolved NO-side model paper trades exist in the local database.

## Losing Trade Review

Only 15 resolved losing model paper trades exist, so the requested 20-trade losing sample is not
available. All 15 resolved losing trades are listed here.

| Trade ID | Market | Exchange | Side | Entry | Qty | Pred YES | Cal YES | Resolution | P&L | Correct P&L | Discrepancy | Suspected Cause |
|---|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|---|
| `b10aefcdbad925693a914605` | Will over 6.5 goals be scored? | kalshi | YES | 0.07 | 1936 | 0.25 | 0.4136991461541613 | NO | -135.52 | -135.52 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `d101dc995a02b907544ca492` | Cleveland vs Cincinnati extra innings | kalshi | YES | 0.11 | 2282 | 0.25 | 0.3787847943565351 | NO | -251.02 | -251.02 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `84d9f9786bbe19f92e3bd166` | SILVER above 59.249 at 00:00 ET | kalshi | YES | 0.11 | 2045 | 0.25 | 0.37767709324031984 | NO | -224.95 | -224.95 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `772dc1772f9abb7a185cacca` | SILVER above 59.299 at 00:00 ET | kalshi | YES | 0.09 | 2045 | 0.25 | 0.3732591459402122 | NO | -184.05 | -184.05 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `fc358a51354686e519aa3957` | SILVER above 59.449 at 00:00 ET | kalshi | YES | 0.06 | 2045 | 0.25 | 0.36776638436486236 | NO | -122.70 | -122.70 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `4057f689f63ec68fd6749aaa` | SILVER above 59.399 at 00:00 ET | kalshi | YES | 0.07 | 2045 | 0.25 | 0.36886224685123525 | NO | -143.15 | -143.15 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `287cb24ad084244099e7c17a` | SILVER above 59.349 at 00:00 ET | kalshi | YES | 0.08 | 2045 | 0.25 | 0.37105802600832355 | NO | -163.60 | -163.60 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `d9f3321397e25e7988c68bd5` | SILVER above 59.449 at 00:00 ET | kalshi | YES | 0.06 | 2045 | 0.25 | 0.36776638436486236 | NO | -122.70 | -122.70 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `e08e6bc31ac67c5155c27911` | SILVER above 59.399 at 00:00 ET | kalshi | YES | 0.07 | 2045 | 0.25 | 0.36886224685123525 | NO | -143.15 | -143.15 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `923e3c40e91a09866310f81b` | SILVER above 59.349 at 00:00 ET | kalshi | YES | 0.08 | 2045 | 0.25 | 0.37105802600832355 | NO | -163.60 | -163.60 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `30bf2ccf6dccb1c0b178c80a` | SILVER above 59.349 at 03:00 ET | kalshi | YES | 0.09 | 2045 | 0.25 | 0.3732591459402122 | NO | -184.05 | -184.05 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `741a2c8b60aaec2ca8879ae6` | SILVER above 59.299 at 03:00 ET | kalshi | YES | 0.11 | 2045 | 0.25 | 0.37767709324031984 | NO | -224.95 | -224.95 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `c9d882907cafa88359588b38` | SILVER above 59.249 at 03:00 ET | kalshi | YES | 0.12 | 2045 | 0.25 | 0.37989376106435657 | NO | -245.40 | -245.40 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `48481c89e874311408d39813` | SILVER above 59.449 at 03:00 ET | kalshi | YES | 0.07 | 2045 | 0.25 | 0.36886224685123525 | NO | -143.15 | -143.15 | 0.00 | Model/trade chose YES; exchange finalized NO |
| `045838ad10761c13c2a9ee8f` | SILVER above 59.399 at 03:00 ET | kalshi | YES | 0.08 | 2045 | 0.25 | 0.37105802600832355 | NO | -163.60 | -163.60 | 0.00 | Model/trade chose YES; exchange finalized NO |

Winning trade reviewed:

| Trade ID | Market | Exchange | Side | Entry | Qty | Pred YES | Cal YES | Resolution | P&L | Correct P&L | Discrepancy |
|---|---|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| `0d145ee0978dea76ebd052a4` | New York vs Las Vegas WNBA over 200.5 | kalshi | YES | 0.17 | 2777.0028 | 0.25 | 0.39329633196902597 | YES | 2304.912324 | 2304.912324 | 0.000000 |

## Resolution And Settlement Findings

Live read-only Kalshi checks were performed for all unique resolved Kalshi markets after retrying
outside the sandbox. All 13 unique markets returned `state=resolved` and
`exchange_status=finalized`.

- 12 unique resolved Kalshi markets resolved NO.
- 1 unique resolved Kalshi market resolved YES.
- Local normalized outcomes matched the exchange outcomes.
- Recorded P&L matched expected settlement arithmetic for every resolved trade checked.
- No loss or win was corrected during this audit.

Settlement was not the cause of the losses.

## Label And YES/NO Mapping Findings

Historical labels in the fixture training dataset are balanced:

- YES labels: 24
- NO labels: 24
- YES resolution is stored as `1`.
- NO resolution is stored as `0`.

Bug fixed:

- `SklearnBinaryModel.predict_proba` previously returned probability column `item[1]`.
- `CalibrationLayer.apply` also read `item[1]` for Platt scaling.
- This assumed class order `[0, 1]`.
- Tests now cover model class order `[0, 1]` and `[1, 0]`.
- The implementation now selects the probability column by explicit class label `1`.

For the currently stored sklearn models, this is a critical latent inversion bug. It may not fully
explain the existing loss set if the trained sklearn artifacts used the normal `[0, 1]` order, but
the previous implementation was unsafe and could invert YES probabilities for any model exposing
classes in a different order.

## Trade Direction Findings

All model paper trades in the local database are YES trades. No NO-side model paper trades exist.

The direction logic is:

- Compute `YES edge = calibrated_yes_probability - executable_yes_price`.
- Compute `NO edge = (1 - calibrated_yes_probability) - executable_no_price`.
- Select the larger edge.

The losing trades were low-priced YES contracts where calibrated YES probability was far above the
executable YES price. The selected side follows the implemented formula, but the model probabilities
were badly wrong for the resolved sample.

## Inverse-Side Diagnostic

This is diagnostic only. No inverted model was deployed.

- Original resolved side win rate: 1/16 = 6.25%
- Inverse side win rate: 15/16 = 93.75%
- Original resolved P&L: -310.677676
- Inverse hypothetical P&L: 310.677676

This is consistent with either a serious model anti-signal or a probability/direction defect. The
class-order bug is fixed. Current evidence also points to model approval and calibration failure.

## Model Approval Findings

Approved model:

- Model ID: `f03c9c31759e786990f3057d`
- Version: `phase3-f03c9c31759e786990f3057d`
- Status: `approved_for_paper`
- Training rows: 48
- Resolved markets: 24
- Validation rows: 16
- Validation markets: 8
- Training date range: 2026-01-24 to 2026-02-18
- Calibration: Platt
- Brier score: 0.18277652680543519
- Raw market baseline Brier score: 0.13011874999999998
- Calibration error: 0.4275224800105817

The model did not beat the market baseline. Its Brier score was worse than the raw market baseline
by about 0.05266, and calibration error was extremely high.

Root cause:

- Previous approval logic allowed manual approval solely by status transition.
- It did not enforce minimum unique resolved training markets.
- It did not enforce minimum validation markets or validation rows.
- It did not require calibration quality.
- It did not require out-of-sample improvement versus the market baseline.

Fix:

- Manual approval now fails unless the model meets configurable thresholds:
  - `MODEL_MIN_APPROVAL_TRAINING_MARKETS=100`
  - `MODEL_MIN_APPROVAL_VALIDATION_MARKETS=30`
  - `MODEL_MIN_APPROVAL_VALIDATION_ROWS=100`
  - `MODEL_MAX_APPROVAL_CALIBRATION_ERROR=0.05`
  - `MODEL_REQUIRED_BRIER_IMPROVEMENT=0.01`

No approved model should remain eligible for paper trading based on the current evidence. Existing
approved records were not deleted or automatically rewritten; execution is blocked by the freeze.

## Dataset Findings

Historical training snapshots:

- Rows: 48
- Unique markets: 24
- Snapshots per market: 2 maximum
- Resolved markets: 24
- Label balance: 24 YES, 24 NO
- Category distribution: 8 per category
- Exchange distribution: 24 Polymarket, 24 Kalshi
- Duplicate IDs: 0
- Duplicate market timestamps: 0
- Train/validation market overlap: 0
- Training markets: 16
- Validation markets: 8
- Date range: 2026-01-24 to 2026-02-18

Leakage tests passed, but the dataset is far too small and too synthetic-looking to approve a model
for paper trading. The validation split has only 8 markets and 16 rows.

## Calibration Findings

Validation calibration table in the approved model:

| Bucket | Count | Average predicted probability | Actual resolution rate | Gap |
|---|---:|---:|---:|---:|
| 40-50 | 8 | 0.4275069028848555 | 0 | 0.4275069028848555 |
| 50-60 | 8 | 0.5724619428636921 | 1 | -0.4275380571363079 |

Calibration error: 0.4275224800105817.

This is not acceptable for paper trading. The calibrator was trained on too little data and did not
produce reliable probabilities.

Bug fixed:

- Platt scaling now reads the probability column by `classes_` instead of assuming column 1.

## Expected-Value Findings

For the losing trades:

- Costs are in decimal dollar units.
- Settlement arithmetic is correct.
- Fees and slippage were zero in current settings, so they did not block trades.
- The uncertainty buffer was subtracted.
- Trades passed because calibrated YES probabilities around 0.37-0.41 were compared with low YES
  executable prices around 0.06-0.12.

Risk:

- `expected_edge` stored on trades is total net expected value, not per-contract edge.
- The EV filter accepted a cluster of correlated low-priced YES trades in Silver threshold markets.
- No future trades may execute while the freeze is active.

## Timing And Staleness Findings

The losing trade drilldown exposed an audit-history defect:

- Prediction IDs were stable by `model_id + market_id`.
- Repeated prediction generation overwrote previous prediction records for the same model/market.
- Some trades now point to prediction rows with timestamps after the trade `created_at`.

Fix:

- New prediction IDs now include prediction timestamp.
- Repeated prediction generation now preserves timestamped history instead of overwriting older
  records.
- A regression test verifies that two prediction runs create separate persisted records.

Existing historical records were not rewritten. For already-created trades, the original prediction
snapshot may not be recoverable from `model_predictions` when it was overwritten.

## Risk-Control Findings

Previous documented defaults allowed up to 5% of paper bankroll per model paper trade. In practice,
the largest trade in this local database was 472.090476, close to the user-requested former $500
cap.

Fix:

- Normal model trade cap default: 0.25% of bankroll.
- Highest-confidence model trade cap default: 0.5% of bankroll.
- Event exposure cap default: 1%.
- Category exposure cap default: 3%.
- Daily paper-loss limit remains configurable at 2%.
- Model paper trading remains paused; these defaults apply only after a future manual audit approval
  explicitly re-enables execution.

## Bugs Fixed

- Disabled model paper-trade creation by default.
- Added visible research-only execution status to model opportunities.
- Added pause status and resolved win-rate fields to model analytics.
- Added frontend pause banner and disabled model paper-trade button.
- Added class-order-safe YES probability extraction for sklearn models and Platt calibration.
- Added model approval thresholds for sample size, calibration quality, and market-baseline
  improvement.
- Reduced future model paper risk defaults.
- Prevented future prediction runs from overwriting earlier prediction history.
- Updated `.env.example` and README model workflow/risk settings.

## Tests Run

Backend:

- `.venv/bin/pytest -q`: 95 passed
- `.venv/bin/ruff check .`: passed
- `.venv/bin/mypy app tests`: passed

Frontend:

- `npm run test`: 12 passed
- `npm run lint`: passed
- `npm run build`: passed

Warnings remaining:

- Pydantic `json_encoders` deprecation warnings.
- Starlette/httpx test-client deprecation warning.
- Joblib CPU-count warning.
- Existing intermittent aiosqlite thread cleanup warnings in async tests.

## Criteria Before Resuming Model Paper Trading

Do not resume model paper trading until all are true:

- Existing approved model is retired or demoted from paper eligibility.
- Training dataset contains at least 100 unique resolved training markets.
- Validation contains at least 30 unique validation markets and 100 validation rows.
- Validation is grouped by market ID and chronological.
- Calibration error is at or below 0.05 on held-out predictions.
- Brier score beats the raw market baseline by at least 0.01.
- Strictly out-of-sample paper simulation has positive return with acceptable drawdown.
- YES/NO mapping tests pass for both exchanges.
- Class-order tests pass for `[0, 1]` and `[1, 0]`.
- Prediction and opportunity records preserve immutable timestamps.
- A human explicitly sets `MODEL_PAPER_TRADING_ENABLED=true` after reviewing the audit.

## Bottom Line

The current approved Phase 3 model should not be used for paper trading. The observed losses are
real in the resolved sample, settlement is correct, and model paper trading is now paused.
