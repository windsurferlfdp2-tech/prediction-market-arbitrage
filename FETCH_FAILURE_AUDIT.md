# Fetch Failure Audit

Audit date: 2026-07-22 UTC

## Summary

The backend endpoints were reachable and did not crash. The browser failures were caused by local frontend-to-backend integration configuration:

1. The backend CORS allowlist only allowed `http://localhost:3000`, while Next was actually running on `http://localhost:3001`. It also rejected `http://127.0.0.1:3000`.
2. The frontend used `NEXT_PUBLIC_API_BASE_URL`, while the local contract is now standardized on `NEXT_PUBLIC_API_URL`.
3. Frontend API errors were generic, so CORS/network failures appeared only as `Failed to fetch`.

No live trading, wallet, signing, deposit, withdrawal, or order-submission code was added.

## Affected Actions

### Generate Live Market-Match Candidates

Frontend page: `/market-matches?data_mode=live`

Button: `Generate candidates`

Backend route from OpenAPI:

```text
POST /market-matches/generate
```

Frontend request after fix:

```text
POST http://127.0.0.1:8000/market-matches/generate?data_mode=live
Content-Type: application/json
Origin: http://127.0.0.1:3001
Body: empty
```

Before fix:

```text
OPTIONS /market-matches/generate?data_mode=live
Origin: http://localhost:3001
Status: 400
Body: Disallowed CORS origin
```

After fix:

```text
POST /market-matches/generate?data_mode=live
Origin: http://127.0.0.1:3001
Status: 200
Body: []
```

Earlier before backend restart, a live read-only generation request returned two pending-review candidates. After restart it returned `[]`, which is a valid structured no-new-candidates response, not a fetch failure.

Latest live market source counts:

| Exchange | Count | Latest source timestamp |
| --- | ---: | --- |
| Polymarket | 25 | `2026-07-22T01:25:02.751167Z` |
| Kalshi | 25 | `2026-07-22T01:25:03.247084Z` |

Backend log evidence:

```text
GET https://gamma-api.polymarket.com/markets?... HTTP/1.1 200 OK
GET https://external-api.kalshi.com/trade-api/v2/markets?... HTTP/1.1 200 OK
request_completed method=POST path=/market-matches/generate status=200 duration_ms=1481.9
```

### Run Paper Trades

Frontend page: `/models`

Button: `Run paper trades`

Backend route from OpenAPI:

```text
POST /model-paper-trades/run
```

Frontend request after fix:

```text
POST http://127.0.0.1:8000/model-paper-trades/run?data_mode=simulation
Content-Type: application/json
Origin: http://localhost:3001 or http://127.0.0.1:3001
Body: empty
```

Before fix:

```text
OPTIONS /model-paper-trades/run?data_mode=simulation
Origin: http://localhost:3001
Status: 400
Body: Disallowed CORS origin
```

After fix:

```text
POST /model-paper-trades/run?data_mode=simulation
Origin: http://localhost:3001
Status: 200
Label: MODEL PAPER TRADE
```

Persisted after backend restart:

```text
GET /model-paper-trades
Status: 200
Returned MODEL PAPER TRADE id 42e37c133957f408bf358463
```

This remains simulation-only and does not call exchange order endpoints.

## Backend Availability

Verified:

```text
GET /health       200
GET /docs         200
GET /openapi.json 200
```

The backend remained alive before and after both failed-action reproductions. Neither endpoint crashed the backend worker. The backend now emits request logs with request ID, method, path, status, and duration.

## CORS Findings

Before fix:

| Origin | Endpoint | Result |
| --- | --- | --- |
| `http://localhost:3000` | market matches | 200 preflight |
| `http://localhost:3001` | market matches | 400 `Disallowed CORS origin` |
| `http://127.0.0.1:3000` | market matches | 400 `Disallowed CORS origin` |
| `http://localhost:3001` | model paper trades | 400 `Disallowed CORS origin` |

After fix:

| Origin | Endpoint | Result |
| --- | --- | --- |
| `http://localhost:3000` | market matches | 200 preflight |
| `http://127.0.0.1:3000` | market matches | 200 preflight |
| `http://localhost:3001` | market matches | 200 preflight |
| `http://127.0.0.1:3001` | model paper trades | 200 preflight |

Allowed headers include `content-type`. Allowed methods include `GET`, `POST`, `PATCH`, and `OPTIONS`.

## Endpoint And Schema Findings

Endpoint paths were correct:

- `POST /market-matches/generate`
- `POST /model-paper-trades/run`

There was no `/api` prefix mismatch and no singular/plural mismatch.

Request bodies were not the cause:

- Candidate generation uses query parameter `data_mode`; no body is required.
- Model paper-trade run uses query parameter `data_mode`; no body is required.

The frontend now sends `Content-Type: application/json` for action POSTs and the backend allows the corresponding preflight.

## Frontend Error Handling

Replaced generic API failures with structured errors that include:

- request method
- sanitized endpoint URL
- HTTP status when available
- backend `detail` or validation payload
- timeout message
- network/CORS/backend-unreachable message

The frontend now validates `NEXT_PUBLIC_API_URL`. If it is missing, the user sees:

```text
Missing NEXT_PUBLIC_API_URL. Set NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 before starting the frontend.
```

Development-mode API logging now emits sanitized request method, URL, status, duration, and structured errors.

## Files Changed In This Fix

- `.env`
- `.env.example`
- `README.md`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/tests/test_api.py`
- `frontend/lib/api.ts`
- `scripts/start-backend-local.sh`
- `scripts/start-frontend-local.sh`
- `FETCH_FAILURE_AUDIT.md`

The worktree also contains earlier Phase 1-3 changes unrelated to this specific fetch-failure fix.

## Tests Run

| Command | Result |
| --- | --- |
| `pytest tests/test_api.py` | 10 passed |
| `pytest` | 58 passed, 47 warnings |
| `ruff check .` | passed |
| `mypy app tests` | passed |
| `npm run typecheck` | passed |
| `npm run lint` | passed |
| `npm run build` | passed |

Warnings:

- Pydantic V2 `json_encoders` deprecation warnings
- Starlette `TestClient` deprecation warning
- joblib CPU-count warning in model tests

## Manual Verification

Backend started with:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=simulation
export USE_FIXTURES=false
export BACKEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend started with:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
export NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
export NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/ws/opportunities
npm run dev -- -H 127.0.0.1 -p 3001
```

Verified pages:

- `GET http://127.0.0.1:3001/models` returned 200 and displayed persisted model paper trades.
- `GET http://127.0.0.1:3001/market-matches?data_mode=live` returned 200 and displayed match reviews.

Verified actions:

```bash
curl -i -sS -X POST \
  'http://127.0.0.1:8000/market-matches/generate?data_mode=live' \
  -H 'Origin: http://127.0.0.1:3001' \
  -H 'Content-Type: application/json'
```

```bash
curl -i -sS -X POST \
  'http://127.0.0.1:8000/model-paper-trades/run?data_mode=simulation' \
  -H 'Origin: http://localhost:3001' \
  -H 'Content-Type: application/json'
```

Backend restart persistence:

```bash
curl -i -sS 'http://127.0.0.1:8000/model-paper-trades'
```

returned persisted `MODEL PAPER TRADE` records after restart.

## Remaining Limitations

- I verified the actions with HTTP-level requests and rendered Next pages. I did not operate a full browser DevTools session, so browser-console text is inferred from CORS behavior and the previous UI message.
- Live candidate generation depends on external Polymarket/Kalshi public API availability and may validly return an empty candidate list.
- The model page currently displays existing approved simulation models from the local database; this is local state, not live trading.
