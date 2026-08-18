# Prediction Market Arbitrage Scanner

Read-only prediction-market arbitrage and forecasting platform for Polymarket and Kalshi.

Normal runtime uses live exchange market data only. Fixture and generated data are reserved for
automated tests with `DATA_MODE=test`; they must not appear in the normal dashboard.

The app does not trade real money, connect wallets, sign orders, manage deposits, or submit live
exchange orders. Paper trades are simulated executions based on observed market data.

## What It Does

- Fetches active markets and order books from live Polymarket and Kalshi public endpoints.
- Normalizes exchange-specific binary markets, outcome identifiers, prices, quantities, and
  timestamps into shared Pydantic models.
- Requires manually verified Polymarket/Kalshi market pairs before cross-platform arbitrage scans.
- Calculates deterministic arbitrage only from fresh executable live order-book asks.
- Generates model predictions and model expected-value opportunities from live market features.
- Records `LIVE-DATA PAPER TRADE` and `LIVE-DATA MODEL PAPER TRADE` records without submitting
  exchange orders.
- Keeps test fixtures isolated from live analytics and live dashboards.

## Data Modes

Only two runtime modes are supported:

- `DATA_MODE=live`: normal operation. Uses live Polymarket/Kalshi data only.
- `DATA_MODE=test`: automated tests and isolated deterministic test workflows.

There is no automatic fallback from live data to fixtures. If an exchange is unavailable, the API
returns an empty, degraded, stale, or offline state instead of synthetic markets.

## Local Backend

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=live
export USE_FIXTURES=false
export BACKEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Initialize the SQLite schema without starting the server:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=live
export USE_FIXTURES=false
python -c "import asyncio; from app.persistence.database import init_db; asyncio.run(init_db())"
```

Shortcut:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner
./scripts/start-backend-local.sh
```

## Local Frontend

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
cp .env.example .env.local
npm install
rm -rf .next
npm run dev
```

`frontend/.env.local` must contain:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Restart the frontend after changing `.env.local`; Next.js reads public environment variables at
startup. Open `http://localhost:3000`.

Shortcut:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner
./scripts/start-frontend-local.sh
```

## Live Checks

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/markets
curl -sS http://127.0.0.1:8000/opportunities
curl -sS http://127.0.0.1:8000/analytics/opportunities
curl -sS http://127.0.0.1:8000/order-books/status
curl -sS -X POST http://127.0.0.1:8000/market-matches/generate
```

Every market, opportunity, prediction, and paper-trade response should expose live-source metadata
such as `data_source`, `is_live_data`, timestamps, or freshness fields where applicable.

## Phase 3 Model Workflow

The model registry and prediction endpoints are live-mode by default. Model paper-trade creation is
paused by default during the Phase 3 failure audit. Predictions and model opportunities may still be
generated for research, but model opportunities are labeled not eligible for paper execution until a
separate manual audit approval explicitly re-enables `MODEL_PAPER_TRADING_ENABLED=true`.

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=live
export USE_FIXTURES=false

curl -sS http://127.0.0.1:8000/models
curl -sS -X POST http://127.0.0.1:8000/models/{model_id}/approve-paper
curl -sS -X POST "http://127.0.0.1:8000/predictions/generate?data_mode=live"
curl -sS -X POST "http://127.0.0.1:8000/model-opportunities/generate?data_mode=live"
curl -sS http://127.0.0.1:8000/model-analytics
```

Dataset building and model training from deterministic rows are test-mode workflows:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///:memory:
export DATA_MODE=test
export USE_FIXTURES=true
pytest tests/test_prediction_phase3.py
```

## Cleaning Old Non-Live Records

Report old fixture, simulation, demo, mock, synthetic, or test records:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=live
export USE_FIXTURES=false
python -m app.tools.cleanup_non_live_data --dry-run
```

Apply cleanup after reviewing the dry-run. The command creates a timestamped SQLite backup first.

```bash
python -m app.tools.cleanup_non_live_data --apply
```

## Runtime Settings

```bash
export LOCAL_DEVELOPMENT=true
export DATA_MODE=live
export USE_FIXTURES=false
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export REDIS_URL=redis://redis:6379/0
export ORDERBOOK_MAX_AGE_SECONDS=30
export LIVE_SCAN_MARKET_LIMIT=25
export MODEL_LIVE_MARKET_LIMIT=5
export PAPER_TRADING_ENABLED=true
export PAPER_MAX_POSITION=500
export MODEL_BANKROLL=10000
export MODEL_PAPER_TRADING_ENABLED=false
export MODEL_KELLY_FRACTION=0.025
export MODEL_MAX_BANKROLL_PCT_PER_TRADE=0.0025
export MODEL_HIGH_CONFIDENCE_BANKROLL_PCT=0.005
export MODEL_MAX_EVENT_EXPOSURE_PCT=0.01
export MODEL_MAX_CATEGORY_EXPOSURE_PCT=0.03
export MODEL_DAILY_LOSS_LIMIT_PCT=0.02
```

When `LOCAL_DEVELOPMENT=true`, SQLite and in-memory cache are used. PostgreSQL and Redis remain
available for production when `LOCAL_DEVELOPMENT=false` and `DATABASE_URL` / `REDIS_URL` point to
those services.

## Quality Commands

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATA_MODE=test
export USE_FIXTURES=true
export DATABASE_URL=sqlite+aiosqlite:///:memory:
ruff format .
ruff check app tests
mypy app tests
pytest

cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
npm run lint
npm run typecheck
npm run build
```

## Reset Local Data

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
rm -f prediction_market_arb.db prediction_market_arb.db-shm prediction_market_arb.db-wal
rm -rf model_artifacts
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=live
export USE_FIXTURES=false
python -c "import asyncio; from app.persistence.database import init_db; asyncio.run(init_db())"
```

## API Routes

- `GET /health`
- `GET /markets`
- `GET /opportunities`
- `GET /opportunities/{id}`
- `GET /analytics/opportunities`
- `GET /paper-trades`
- `GET /order-books/status`
- `POST /market-matches/generate`
- `GET /market-matches`
- `PATCH /market-matches/{id}`
- `GET /models`
- `GET /models/{id}`
- `POST /models/dataset`
- `POST /models/train`
- `POST /models/{id}/approve-paper`
- `POST /models/{id}/retire`
- `POST /predictions/generate`
- `GET /predictions`
- `GET /predictions/{id}`
- `POST /model-opportunities/generate`
- `GET /model-opportunities`
- `POST /model-paper-trades/run`
- `GET /model-paper-trades`
- `GET /model-analytics`
- `WS /ws/opportunities`

## Troubleshooting

Backend connectivity:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
curl -sS http://127.0.0.1:8000/health
```

CORS:

```bash
export BACKEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001
```

Frontend connectivity:

```bash
export NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
export NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/ws/opportunities
```

Exchange access:

```bash
export REQUEST_TIMEOUT_SECONDS=10
export REQUEST_RETRIES=3
export LIVE_SCAN_MARKET_LIMIT=25
```

If live exchange APIs are slow, rate-limited, or unavailable, the dashboard should show no live
results or a degraded status. It must not substitute fixture records.

Stale order books:

```bash
export ORDERBOOK_MAX_AGE_SECONDS=30
curl -sS http://127.0.0.1:8000/order-books/status
```

Books older than `ORDERBOOK_MAX_AGE_SECONDS` are excluded from opportunity detection.

Model artifacts:

```bash
ls -la backend/model_artifacts
curl -sS http://127.0.0.1:8000/models
```

Approved models load artifacts only from `MODEL_REGISTRY_DIR`. Missing or invalid artifacts should
produce a clear API error and no paper trade.

## Safety Boundaries

- No live order creation.
- No wallet integration.
- No private-key signing.
- No deposits or withdrawals.
- No autonomous live execution.
- Paper trades are simulated execution records only.
- Live-data paper trades use live observed books, but fills remain hypothetical.

## Current Limitations

- Live match generation depends on both public exchange APIs being reachable.
- Kalshi WebSocket ingestion requires server-side credentials when enabled; REST market data remains
  read-only.
- Model-based live opportunities require an approved model and fresh live order books.
- If no verified equivalent pair or no positive edge exists, the correct live result is an empty
  dashboard.
