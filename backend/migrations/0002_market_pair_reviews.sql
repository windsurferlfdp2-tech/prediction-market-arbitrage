CREATE TABLE IF NOT EXISTS market_pair_reviews (
    id VARCHAR(64) PRIMARY KEY,
    polymarket_market_id VARCHAR(256) NOT NULL,
    kalshi_market_id VARCHAR(256) NOT NULL,
    polymarket_title TEXT NOT NULL,
    kalshi_title TEXT NOT NULL,
    polymarket_resolution_criteria TEXT NOT NULL,
    kalshi_resolution_criteria TEXT NOT NULL,
    polymarket_close_date VARCHAR(64),
    kalshi_close_date VARCHAR(64),
    polymarket_settlement_date VARCHAR(64),
    kalshi_settlement_date VARCHAR(64),
    polymarket_resolution_sources JSON NOT NULL,
    kalshi_resolution_sources JSON NOT NULL,
    polymarket_entities JSON NOT NULL,
    kalshi_entities JSON NOT NULL,
    polymarket_numbers JSON NOT NULL,
    kalshi_numbers JSON NOT NULL,
    similarity_score NUMERIC NOT NULL,
    mismatches JSON NOT NULL,
    status VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_market_pair_reviews_polymarket_market_id
    ON market_pair_reviews (polymarket_market_id);
CREATE INDEX IF NOT EXISTS ix_market_pair_reviews_kalshi_market_id
    ON market_pair_reviews (kalshi_market_id);
CREATE INDEX IF NOT EXISTS ix_market_pair_reviews_status
    ON market_pair_reviews (status);
