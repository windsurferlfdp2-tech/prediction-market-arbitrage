# Model Registry Duplicate Audit

Audit date: 2026-07-31 UTC

## Exact Root Cause

`PredictionService.train_model()` generated `model_id` from the current timestamp and then inserted a
new `PredictionModelRecord` unconditionally. The historical dataset builder is idempotent, but model
registration was not. Re-running the same training command repeatedly produced visually identical
registry rows with different ids and artifact filenames.

The duplicate rows were not created by backend startup, database initialization, fixture seeding,
prediction generation, model-opportunity generation, frontend refresh, or paper-trade execution.
They were created after repeated model-training commands.

## Registry Creation Points

The only runtime code path found that creates `prediction_models` records is:

- `backend/app/services/prediction.py`, `PredictionService.train_model()`

Related paths checked:

- Backend startup: calls `init_db()` only; no model registration.
- Database initialization: creates/repairs schema and records migration versions only.
- Historical dataset builder: inserts `historical_training_snapshots` idempotently, not models.
- Prediction generation: reads the latest approved model and writes `model_predictions`.
- Model opportunity generation: writes `model_opportunities`.
- Frontend refresh: calls read endpoints only.

## Duplicate Analysis

Before cleanup:

- Registry rows: 29
- Displayed model name: `phase3_market_anchored_ensemble`
- Displayed status: `approved_for_paper`
- Training sample count: 48
- Displayed Brier score: approximately `0.1828`
- Calibration: `platt`

The rows shared the same deterministic training inputs:

- Model type: `ensemble`
- Effective category: `general`
- Feature schema: `phase3.v1`
- Calibration version: `phase3.calibration.v1`
- Random seed: `42`
- Training date range: `2026-01-24` to `2026-02-18`
- Training snapshots: 48
- Validation snapshots: 16
- Resolved market count: 24
- Train/validation market ids: equivalent

Some artifact file hashes differed because the pickle artifacts were written in separate runs.
Those byte differences did not correspond to meaningfully different training configuration,
dataset, feature schema, seed, or validation setup.

Final conclusion: 29 registry rows represented 1 actual model configuration.

## Cleanup Performed

Cleanup command added:

```bash
python -m app.tools.cleanup_duplicate_models --dry-run
python -m app.tools.cleanup_duplicate_models --apply
```

Dry-run/apply behavior:

- Identifies duplicate groups.
- Keeps a canonical model record.
- Creates a SQLite backup before apply.
- Reassigns `model_predictions.model_id`.
- Reassigns `model_opportunities.model_id`.
- Reassigns `model_paper_trades.model_id`.
- Updates nested `payload.model_id` references.
- Deletes duplicate `prediction_models` rows.
- Backfills canonical registry metadata.

Cleanup backups created:

- `backend/prediction_market_arb.db.model-registry-backup-20260731T022751Z`
- `backend/prediction_market_arb.db.model-registry-backup-20260731T023121Z`
- `backend/prediction_market_arb.db.model-registry-backup-20260731T023158Z`
- `backend/prediction_market_arb.db.model-registry-backup-20260731T023250Z`

Final cleanup state:

- Registry rows: 1
- Duplicate groups: 0
- Duplicate rows: 0
- Unique actual models: 1
- Orphaned model prediction references: 0
- Orphaned model opportunity references: 0
- Orphaned model paper-trade references: 0

Canonical model kept:

- `f03c9c31759e786990f3057d`

Canonical metadata after cleanup:

- Training fingerprint: `legacy-273afc8669f44ae36dd2e22a1936f0662d87c1828c34ad1ffac040d5b7713b41`
- Artifact hash: `77dc462c67c3e3738afd3b0d319df49c41e330a76460fc4b9d80eb5c3057e250`
- Dataset version: `dataset-f116f7b19a91d9a3e1f0d0a2`
- Training date range: `2026-01-24` to `2026-02-18`
- Resolved market count: 24
- Validation sample count: 16
- Baseline Brier score: `0.13011874999999998`
- Model Brier score: `0.18277652680543519`

## Future Prevention

`PredictionService.train_model()` now computes a deterministic training fingerprint before
registering a model. The fingerprint uses:

- Model type
- Requested category
- Effective category
- Dataset version
- Training date range
- Feature schema version
- Hyperparameters
- Random seed
- Calibration settings
- Source-code identifier
- Fallback reason

If an equivalent non-retired registry row exists, training returns the existing model summary and
does not create a new row or artifact. Retired rows remain auditable; retraining the same config
after retirement creates a new candidate with a unique id.

## Schema Changes

Migration added:

- `backend/migrations/0005_model_registry_fingerprint.sql`

New model registry metadata columns:

- `training_fingerprint`
- `artifact_hash`
- `dataset_version`
- `resolved_market_count`
- `validation_sample_count`
- `baseline_score`
- `model_score`

SQLite local databases are also repaired at initialization because the project uses
SQLAlchemy-managed local schema creation.

## Frontend Fixes

The model registry now:

- Shows approved models as `Approved`.
- Hides the approve button for already-approved models.
- Hides approve/retire actions for retired models as appropriate.
- Displays training window.
- Displays dataset version.
- Displays resolved market count.
- Displays validation sample count.
- Displays baseline score and model score.
- Displays artifact hash and fingerprint.

## Files Changed

- `backend/app/main.py`
- `backend/app/models/domain.py`
- `backend/app/persistence/database.py`
- `backend/app/services/prediction.py`
- `backend/app/tools/cleanup_duplicate_models.py`
- `backend/migrations/0005_model_registry_fingerprint.sql`
- `backend/tests/test_api.py`
- `backend/tests/test_history.py`
- `backend/tests/test_model_registry_cleanup.py`
- `backend/tests/test_prediction_phase3.py`
- `frontend/app/models/ModelDashboardClient.tsx`
- `frontend/lib/modelRegistryView.d.ts`
- `frontend/lib/modelRegistryView.js`
- `frontend/lib/modelRegistryView.test.mjs`
- `frontend/lib/types.ts`
- `frontend/package.json`

## Tests Run

Backend:

- `pytest -q tests/test_prediction_phase3.py tests/test_model_registry_cleanup.py tests/test_api.py`
  - 28 passed
- `pytest -q`
  - 71 passed
  - 47 warnings
- `ruff check app tests`
  - passed
- `mypy app tests`
  - passed

Frontend:

- `npm run test`
  - 12 passed
- `npm run lint`
  - passed
- `npm run build`
  - passed

Warnings remaining:

- Pydantic `json_encoders` deprecation warnings.
- FastAPI/Starlette `TestClient` deprecation warning.
- joblib CPU-count warning in the local environment.

## Current Limitations

- Existing old artifact files were not deleted from `model_artifacts`; registry rows were cleaned and
  references were preserved. Artifact-file garbage collection can be handled separately.
- The application-level guard prevents duplicate non-retired registrations. A physical unique
  database constraint should only be added after all environments have been cleaned.
