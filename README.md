# Prediction Market Arbitrage Scanner

Phase 1 production-quality, read-only scanner for same-market binary prediction-market arbitrage across Polymarket and Kalshi.

The app does not trade, connect wallets, handle private keys, or submit orders. All displayed opportunities are estimates.

## What It Does

- Retrieves active binary markets and order books through exchange adapters.
- Normalizes Polymarket and Kalshi data into common Pydantic v2 models.
- Preserves raw exchange payloads for debugging.
- Rejects stale order books.
- Detects YES ask plus NO ask cost below the guaranteed `$1` payout.
- Walks all executable order-book levels and calculates matched quantity, weighted average entry, gross profit, fees, slippage, net profit, ROI, freshness, and confidence.
- Serves results through FastAPI and a WebSocket.
- Displays opportunities in a Next.js TypeScript dashboard with filters and detail pages.

## Official API References Used

- Polymarket CLOB order book: `GET https://clob.polymarket.com/book?token_id=...`
- Polymarket market/order-book overview: `https://docs.polymarket.com/market-data/overview`
- Kalshi markets: `GET https://external-api.kalshi.com/trade-api/v2/markets`
- Kalshi multiple order books: `GET https://external-api.kalshi.com/trade-api/v2/markets/orderbooks`
- Kalshi environments: `https://docs.kalshi.com/getting_started/api_environments`

## Project Layout

```text
backend/
  app/
    arbitrage/       Decimal arbitrage engine
    exchanges/       ExchangeAdapter, PolymarketAdapter, KalshiAdapter, raw models
    models/          Normalized entities
    persistence/     SQLAlchemy 2 records
    services/        Scanner and Redis cache hooks
  tests/
    fixtures/        Stored API fixtures
frontend/
  app/               Next.js dashboard and opportunity detail route
  lib/               API client and TypeScript types
docker-compose.yml
PLAN.md
.env.example
```

## Local Setup

Backend:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Frontend:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

Docker Compose:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner
cp .env.example .env
docker compose up --build
```

## Quality Commands

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
ruff format .
ruff check .
mypy app tests
pytest

cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
npm run lint
npm run typecheck
npm run build
```

## API

- `GET /health`
- `GET /markets`
- `GET /opportunities`
- `GET /opportunities/{id}`
- `WS /ws/opportunities`

## Important Assumptions

- Same-market matching is explicit and configuration/metadata driven by `same_market_key`. Phase 1 does not attempt semantic market matching.
- Stored fixtures are the default (`USE_FIXTURES=true`) so tests and first-run development do not depend on live network calls.
- Live market discovery is limited to documented public endpoints and documented fields.
- Missing prices or quantities raise errors; the scanner does not silently infer missing values.
- `Decimal` is used for all price, quantity, fee, slippage, profit, and ROI calculations.
- Flat `FEE_RATE` and `SLIPPAGE_RATE` settings are used in Phase 1. More exact venue-specific fee curves can be added later using preserved raw payloads.

## Exchange-Specific Differences

- Polymarket CLOB returns explicit bids and asks for each token/outcome.
- Kalshi’s documented order-book endpoint returns YES and NO bid books only. The adapter derives executable asks using the documented binary equivalence:
  - YES bid at `X` equals NO ask at `1-X`.
  - NO bid at `X` equals YES ask at `1-X`.
- Kalshi markets use tickers; Polymarket CLOB books use token IDs and condition IDs.
- Polymarket timestamps may appear as ISO strings or numeric timestamps depending on endpoint/client path. The adapter handles both documented forms.

## Current Limitations

- No live trading, no authenticated private endpoints, no wallet integration.
- No semantic deduplication or NLP matching across exchanges.
- Persistence models are present, but Phase 1 serves snapshots from the scanner service cache.
- WebSocket refresh currently polls the scanner every five seconds.
