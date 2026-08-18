CREATE TABLE IF NOT EXISTS order_book_snapshots (
    id INTEGER PRIMARY KEY,
    exchange VARCHAR(32) NOT NULL,
    market_id VARCHAR(256) NOT NULL,
    outcome_id VARCHAR(256) NOT NULL,
    side VARCHAR(16) NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    exchange_timestamp TIMESTAMP,
    age_seconds NUMERIC NOT NULL,
    stale BOOLEAN NOT NULL,
    sequence INTEGER,
    transport VARCHAR(32) NOT NULL,
    asks JSON NOT NULL,
    bids JSON NOT NULL,
    raw JSON NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_order_book_snapshots_exchange
    ON order_book_snapshots (exchange);
CREATE INDEX IF NOT EXISTS ix_order_book_snapshots_market_id
    ON order_book_snapshots (market_id);
CREATE INDEX IF NOT EXISTS ix_order_book_snapshots_side
    ON order_book_snapshots (side);
CREATE INDEX IF NOT EXISTS ix_order_book_snapshots_observed_at
    ON order_book_snapshots (observed_at);
CREATE INDEX IF NOT EXISTS ix_order_book_snapshots_stale
    ON order_book_snapshots (stale);

CREATE TABLE IF NOT EXISTS paper_trade_simulations (
    id VARCHAR(64) PRIMARY KEY,
    opportunity_id VARCHAR(64) NOT NULL,
    same_market_key VARCHAR(256) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    direction VARCHAR(64) NOT NULL,
    yes_exchange VARCHAR(32) NOT NULL,
    no_exchange VARCHAR(32) NOT NULL,
    yes_market_id VARCHAR(256) NOT NULL,
    no_market_id VARCHAR(256) NOT NULL,
    requested_quantity NUMERIC NOT NULL,
    filled_quantity NUMERIC NOT NULL,
    projected_gross_profit NUMERIC NOT NULL,
    projected_net_profit NUMERIC NOT NULL,
    realized_pnl NUMERIC NOT NULL,
    latency_ms INTEGER NOT NULL,
    partial_fill BOOLEAN NOT NULL,
    hedge_failure BOOLEAN NOT NULL,
    status VARCHAR(64) NOT NULL,
    fills JSON NOT NULL,
    payload JSON NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_opportunity_id
    ON paper_trade_simulations (opportunity_id);
CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_same_market_key
    ON paper_trade_simulations (same_market_key);
CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_created_at
    ON paper_trade_simulations (created_at);
CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_direction
    ON paper_trade_simulations (direction);
CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_yes_market_id
    ON paper_trade_simulations (yes_market_id);
CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_no_market_id
    ON paper_trade_simulations (no_market_id);
CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_partial_fill
    ON paper_trade_simulations (partial_fill);
CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_hedge_failure
    ON paper_trade_simulations (hedge_failure);
CREATE INDEX IF NOT EXISTS ix_paper_trade_simulations_status
    ON paper_trade_simulations (status);
