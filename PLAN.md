# Phase 1 Implementation Plan

## Scope

Build a read-only prediction-market arbitrage scanner that fetches active binary markets and order books from Polymarket and Kalshi, normalizes exchange-specific responses, detects same-market YES+NO ask arbitrage, and displays opportunities in a dashboard.

Out of scope: live trading, wallet access, private keys, authenticated order routes, or order submission.

## Source-of-Truth API Notes

- Polymarket CLOB public order books are read with `GET https://clob.polymarket.com/book?token_id=...`. The response includes `market`, `asset_id`, `timestamp`, `bids`, `asks`, `min_order_size`, `tick_size`, `neg_risk`, and `hash`.
- Polymarket market discovery can use public CLOB market endpoints such as sampling markets and CLOB market info. Phase 1 supports documented fixture-backed discovery and a live adapter path limited to documented fields.
- Kalshi market discovery uses `GET https://external-api.kalshi.com/trade-api/v2/markets` with `status=open`.
- Kalshi order books use `GET https://external-api.kalshi.com/trade-api/v2/markets/orderbooks?tickers=...`. The docs state this returns YES and NO bid books, not asks. A bid for YES at `X` is equivalent to a NO ask at `1-X`; a bid for NO at `X` is equivalent to a YES ask at `1-X`.

## Architecture

1. Backend package under `backend/app`.
2. Define a typed `ExchangeAdapter` abstract interface.
3. Keep raw exchange response models in `app/exchanges/raw.py`.
4. Keep normalized Pydantic v2 domain models in `app/models/domain.py`.
5. Implement `PolymarketAdapter` and `KalshiAdapter` with configurable timeout, retry count, and exponential backoff.
6. Store fetch timestamps on normalized market/order-book objects and preserve raw response payloads.
7. Reject stale order books before arbitrage detection.
8. Use `Decimal` for prices, quantities, fees, slippage, PnL, and ROI.
9. Provide FastAPI routes:
   - `GET /health`
   - `GET /markets`
   - `GET /opportunities`
   - `GET /opportunities/{id}`
   - `WS /ws/opportunities`
10. Add SQLAlchemy 2 models for persisted snapshots and opportunities; Phase 1 can run without live persistence when DB is unavailable.
11. Add Redis-ready cache abstraction; Phase 1 can run without Redis when unavailable.
12. Add pytest unit tests with stored fixtures only.
13. Build Next.js TypeScript dashboard with opportunity table, filters, detail page, platform health indicators, and WebSocket refresh.

## Vertical Slice

1. Load fixture-backed Polymarket and Kalshi normalized markets/order books.
2. Match markets by configured canonical `same_market_key`.
3. Detect arbitrage by walking YES ask and NO ask levels.
4. Return opportunities from FastAPI.
5. Render opportunities and detail views in Next.js.
6. Verify unit tests for normalization, staleness rejection, and arbitrage calculations.

## Assumptions and Limitations

- Same-market matching is configuration-driven via `same_market_key`; Phase 1 does not perform semantic market matching.
- Live Polymarket and Kalshi endpoint usage is read-only and unauthenticated where available. If an exchange requires authentication for a public-looking endpoint in production, the adapter reports degraded health rather than inventing fields.
- Kalshi ask levels are explicitly derived from documented bid equivalence.
- Fees and slippage are configurable flat rates in Phase 1. Exchange-specific fee curves are preserved in raw data but not fully modeled.
- All dashboard values are estimates and read-only.
