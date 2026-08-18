CREATE TABLE IF NOT EXISTS opportunity_history (
    id INTEGER PRIMARY KEY,
    opportunity_id VARCHAR(64) NOT NULL,
    data_mode VARCHAR(32) NOT NULL,
    same_market_key VARCHAR(256) NOT NULL,
    yes_exchange VARCHAR(32) NOT NULL,
    no_exchange VARCHAR(32) NOT NULL,
    yes_market_id VARCHAR(256) NOT NULL,
    no_market_id VARCHAR(256) NOT NULL,
    market_title TEXT NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL,
    disappeared_at TIMESTAMP,
    duration_seconds NUMERIC NOT NULL,
    disappearance_reason VARCHAR(128),
    yes_price NUMERIC NOT NULL,
    yes_available_size NUMERIC NOT NULL,
    no_price NUMERIC NOT NULL,
    no_available_size NUMERIC NOT NULL,
    combined_cost NUMERIC NOT NULL,
    estimated_fees NUMERIC NOT NULL,
    estimated_slippage NUMERIC NOT NULL,
    net_edge NUMERIC NOT NULL,
    net_roi NUMERIC NOT NULL,
    maximum_executable_quantity NUMERIC NOT NULL,
    order_book_age_seconds NUMERIC NOT NULL,
    is_active BOOLEAN NOT NULL,
    payload JSON NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_opportunity_history_opportunity_id
    ON opportunity_history (opportunity_id);
CREATE INDEX IF NOT EXISTS ix_opportunity_history_data_mode
    ON opportunity_history (data_mode);
CREATE INDEX IF NOT EXISTS ix_opportunity_history_detected_at
    ON opportunity_history (detected_at);
CREATE INDEX IF NOT EXISTS ix_opportunity_history_is_active
    ON opportunity_history (is_active);
