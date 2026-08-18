# Phase 2 Plan

## Goal

Add a read-only Phase 2 vertical slice that connects manually verified Polymarket/Kalshi pairs to
fresh normalized order books, cross-platform arbitrage calculations, paper-trading simulation, and
historical analytics. No live order submission, wallets, private keys, deposits, withdrawals, or
autonomous trading are in scope.

## Reusable Phase 1 Components

- `Market`, `OrderBook`, `PriceLevel`, `ArbitrageOpportunity`, and `UsedLevel` domain models.
- Polymarket and Kalshi REST adapters and their exchange-specific price normalization.
- Decimal arbitrage level walking in `ArbitrageDetector`.
- Manual market-pair review queue and verified-pair gating in `MarketMatchingService`.
- SQLite local mode, PostgreSQL-compatible SQLAlchemy models, and migration tracking.
- Simulation-mode deterministic markets and books for dashboard/end-to-end tests.
- Opportunity history recorder and dashboard analytics shell.

## Schema Changes

Additive migrations only:

- `paper_trade_simulations`
  - Stores PAPER TRADING executions linked to opportunity IDs and verified market-pair keys.
  - Captures projected P&L, realized simulated P&L, latency, fills, partial-fill/hedge-failure
    flags, and execution status.
- `order_book_snapshots`
  - Stores normalized observed order books used by Phase 2 analytics.
  - Captures exchange, market, side, timestamps, age, staleness, levels, and raw payload.

These use portable `VARCHAR`, `TEXT`, `NUMERIC`, `BOOLEAN`, `TIMESTAMP`, and `JSON` columns so local
SQLite and production PostgreSQL remain supported.

## Implementation Order

1. Vertical slice
   - Use only manually `Verified equivalent` market pairs.
   - Maintain in-memory normalized books through a realtime order-book service with REST fallback.
   - Calculate cross-platform opportunities from those verified books.
   - Simulate PAPER TRADING fills for detected opportunities.
   - Persist paper-trade and book snapshot records.
   - Show paper-trading results and analytics in the dashboard.

2. Realtime ingestion
   - Add exchange-specific public WebSocket clients.
   - Support Polymarket public market WebSocket ingestion.
   - Support Kalshi WebSocket ingestion only when server-side credentials are configured.
   - Preserve REST polling fallback.
   - Apply snapshot/delta messages in sequence-aware in-memory stores.
   - Mark books stale after `ORDERBOOK_MAX_AGE_SECONDS`.
   - Reconnect with exponential backoff and refresh full REST snapshots after reconnect.

3. Matching review hardening
   - Normalize review status values to Phase 2 snake_case.
   - Store reviewer action timestamps.
   - Expand extracted contract specs: title, entities, dates, timezones, thresholds, direction,
     sources, and resolution rules.
   - Keep similarity as candidate generation only; never auto-approve.

4. Paper trading and analytics
   - Simulate leg latency, complete/partial fills, second-leg failure, and opportunity
     disappearance using subsequent observed books.
   - Enforce maximum simulated position limits.
   - Add analytics for projected ROI, executable ROI, fill rate, partial-fill rate,
     hedge-failure rate, cumulative simulated P&L, category/platform breakdowns, and filters.

5. Reliability
   - Unit tests for matching specs, price conversions, deterministic arbitrage, WebSocket
     snapshot/delta processing, reconnect/stale handling, and paper fills.
   - Full backend tests, mypy, ruff, frontend lint/typecheck/build before completion.

## Current Vertical Slice Boundary

The first implemented slice will be:

manual verified pair -> normalized live/simulation books -> calculated cross-platform opportunity
-> PAPER TRADING simulation -> stored record -> dashboard/API result.

REST fallback remains the default transport locally. WebSocket clients are implemented as
read-only ingestion components and covered with deterministic fixture tests before being enabled
as a long-running production transport.
