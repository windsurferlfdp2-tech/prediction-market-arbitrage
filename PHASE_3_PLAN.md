# Phase 3 Plan

## Goal

Add a calibrated, market-anchored prediction layer that estimates fair binary-market
probabilities, compares them with executable prices, identifies positive expected-value
opportunities, and records clearly labeled model paper trades. The system remains read-only and
paper-trading only.

## Reused Phase 1-2 Components

- `Market`, `OrderBook`, `PriceLevel`, and exchange adapters for normalized market and book data.
- `ScannerService` simulation/live switching and local SQLite configuration.
- `PaperTradingSimulator` fill-walking concepts for partial fills and slippage.
- `OrderBookSnapshotRecord` as the historical market data source when enough observations exist.
- Existing analytics/dashboard patterns and additive SQLAlchemy schema initialization.

## Proposed Schema Changes

All Phase 3 tables are additive and use portable SQLAlchemy types for SQLite and PostgreSQL:

- `historical_training_snapshots`: reproducible, point-in-time feature rows and labels.
- `prediction_models`: local model registry entries, metadata, metrics, artifact paths, and status.
- `model_predictions`: stored prediction results with feature snapshots and no-trade reasons.
- `model_opportunities`: model-based positive expected-value opportunities, separate from arbitrage.
- `model_paper_trades`: model paper-trade fills, mark-to-market state, and realized simulated P&L.

JSON columns store feature schemas, calibration tables, risk settings, and payloads to avoid
database-specific array or JSONB behavior.

## Vertical Slice

1. Build deterministic historical fixture snapshots with only point-in-time features.
2. Train market baseline, logistic regression, and histogram-gradient boosted models.
3. Split by market ID and chronology so snapshots from one market never cross splits.
4. Calibrate held-out model predictions using Platt scaling or isotonic regression when sample size
   permits.
5. Register a candidate model with validation metrics and artifacts.
6. Manually approve the model for paper trading.
7. Generate a fixture current prediction.
8. Detect a positive expected-value model opportunity.
9. Create a directional `MODEL PAPER TRADE`.
10. Surface predictions, opportunities, trades, and analytics through API and frontend pages.

## Leakage Protections

- Feature timestamps must be less than or equal to prediction timestamps.
- Market close timestamps must be after prediction timestamps.
- Resolution outcomes are stored only as labels, never in feature payloads.
- Train/validation split is grouped by market ID.
- Calibration is fitted only on held-out validation predictions.
- Stacker metadata records that component predictions came from held-out rows; when insufficient
  data exists, fallback weights are explicitly labeled.

## Minimum Sample Thresholds

- Category-specific model: at least 20 snapshots and 6 markets for the category.
- General logistic model: at least 12 snapshots, 6 markets, and both outcomes represented.
- Gradient-boosted model: at least 16 snapshots, 8 markets, and both outcomes represented.
- Stacker: at least 8 held-out predictions and both outcomes represented.
- Calibration: Platt scaling from 6 held-out predictions; isotonic from 40 held-out predictions.

If thresholds are not met, prediction generation falls back to market-implied baseline or no-trade
with explicit no-trade reasons.

## Financial Boundaries

Trading and expected-value calculations use `Decimal`. Conversion to `float` occurs only inside
the model training and inference boundary, where scikit-learn requires numeric arrays.

## Initial Limitations

- The first implementation uses deterministic fixture data for a complete local workflow.
- Live model opportunities require sufficient stored historical snapshots and a manually approved
  model.
- External structured data and LLM forecaster interfaces are scaffolded but disabled by default.
- Model performance is reported, not treated as evidence of profitability.
