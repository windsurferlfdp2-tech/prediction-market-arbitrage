-- Add deterministic model-registry metadata used to prevent duplicate registrations.
-- Local SQLite databases are repaired by app.persistence.database during init because the
-- project uses SQLAlchemy create_all for Docker-free local development.
ALTER TABLE prediction_models ADD COLUMN IF NOT EXISTS training_fingerprint VARCHAR(128);
ALTER TABLE prediction_models ADD COLUMN IF NOT EXISTS artifact_hash VARCHAR(128);
ALTER TABLE prediction_models ADD COLUMN IF NOT EXISTS dataset_version VARCHAR(128);
ALTER TABLE prediction_models ADD COLUMN IF NOT EXISTS resolved_market_count INTEGER;
ALTER TABLE prediction_models ADD COLUMN IF NOT EXISTS validation_sample_count INTEGER;
ALTER TABLE prediction_models ADD COLUMN IF NOT EXISTS baseline_score NUMERIC(38, 18);
ALTER TABLE prediction_models ADD COLUMN IF NOT EXISTS model_score NUMERIC(38, 18);
CREATE INDEX IF NOT EXISTS ix_prediction_models_training_fingerprint
    ON prediction_models (training_fingerprint);
