-- Add model paper-trade settlement metadata.
-- SQLite local databases are repaired by app.persistence.database during init.
ALTER TABLE model_paper_trades ADD COLUMN IF NOT EXISTS resolved_outcome VARCHAR(16);
ALTER TABLE model_paper_trades ADD COLUMN IF NOT EXISTS resolution_timestamp TIMESTAMP;
ALTER TABLE model_paper_trades ADD COLUMN IF NOT EXISTS last_resolution_check_timestamp TIMESTAMP;
ALTER TABLE model_paper_trades ADD COLUMN IF NOT EXISTS settlement_value NUMERIC(38, 18);
