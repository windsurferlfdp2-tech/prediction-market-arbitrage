# System Audit

Audit date: 2026-07-21 00:00:40 CST

## Architecture Summary

The project is a read-only prediction-market arbitrage scanner with a FastAPI backend and Next.js
frontend. Local development runs without Docker using SQLite and in-memory caching. Production
support remains available for PostgreSQL and Redis through `DATABASE_URL` and `REDIS_URL`.

Core backend components:

- Exchange adapters: Polymarket and Kalshi REST market/order-book normalization.
- Realtime order-book service: in-memory normalized book state, snapshot/delta application,
  sequence-gap checks, stale-book filtering, reconnect helper, and REST fallback.
- Market matching: candidate generation and manual review statuses.
- Arbitrage detector: Decimal-based cross-platform YES/NO order-book walking.
- Paper trading: simulated fills only, labeled `PAPER TRADING`.
- Persistence: SQLAlchemy models with SQLite/PostgreSQL-compatible migrations.

Core frontend components:

- Main scanner dashboard with opportunities, analytics, and PAPER TRADING panel.
- Market-match review page with manual status controls and mismatch display.
- Detail page for opportunity economics and captured execution levels.

## Commands Executed

Backend:

```bash
python -m compileall -q app tests
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy app tests
```

Frontend:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

Runtime and route checks:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
npm run dev
curl http://127.0.0.1:8000/health?data_mode=simulation
curl http://127.0.0.1:8000/markets?data_mode=simulation
curl http://127.0.0.1:8000/opportunities?data_mode=simulation
curl http://127.0.0.1:8000/docs
curl http://127.0.0.1:8000/analytics/opportunities?data_mode=simulation
curl http://127.0.0.1:8000/paper-trades?limit=5
curl http://127.0.0.1:8000/order-books/status
curl -X POST http://127.0.0.1:8000/market-matches/generate?data_mode=simulation
curl -X PATCH http://127.0.0.1:8000/market-matches/{id}
curl http://localhost:3000/
curl http://localhost:3000/market-matches
```

Clean database verification used `/private/tmp/pma_audit_clean.db` and
`/private/tmp/pma_audit_reset.db` to avoid deleting the working local database.

## Test Results

- Backend unit/integration tests: 43 passed, 0 failed, 0 skipped.
- Backend type checking: passed.
- Backend linting: passed.
- Frontend linting: passed.
- Frontend type checking: passed.
- Frontend test script: passed; currently aliases to `npm run typecheck`.
- Frontend production build: passed.

Warnings:

- Pydantic `json_encoders` deprecation warnings from Pydantic v2.
- Starlette/FastAPI TestClient warning about future `httpx2`.

No tests in the committed suite require live external services. Separate live read-only probes were
run manually during the audit.

## Routes Verified

- `GET /health` -> 200
- `GET /markets` -> 200
- `GET /opportunities` -> 200
- `GET /opportunities/{id}` -> covered by tests
- `GET /analytics/opportunities` -> 200
- `GET /paper-trades` -> 200
- `GET /order-books/status` -> 200
- `POST /market-matches/generate` -> 200
- `GET /market-matches` -> 200
- `PATCH /market-matches/{id}` -> 200 with valid status, 422 with invalid status
- `GET /docs` -> 200
- `WS /ws/opportunities` -> covered by server startup and frontend configuration, not browser-console inspected

Invalid query/body validation was verified:

- Invalid `data_mode` returns 422 with allowed values.
- Invalid market-match status returns 422 with allowed values.

## Live Exchange Checks

Official documentation checked:

- Polymarket public market WebSocket endpoint:
  `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Polymarket CLOB book endpoint:
  `https://clob.polymarket.com/book`
- Kalshi REST base:
  `https://external-api.kalshi.com/trade-api/v2`
- Kalshi single-market orderbook:
  `GET /markets/{ticker}/orderbook`
- Kalshi recommended WebSocket:
  `wss://external-api-ws.kalshi.com/trade-api/ws/v2`

Live adapter results:

- Polymarket: 25 normalized markets, 0 rejected in capped sample.
- Kalshi: 25 normalized markets, 0 rejected in capped sample.
- Polymarket order books: 2 normalized books for one market; best YES ask/bid observed.
- Kalshi order books: 2 normalized books for one market; YES/NO bids converted to executable asks.

Limitations:

- No authenticated Kalshi WebSocket was tested because no credentials were provided.
- Live exchange behavior depends on public API availability and current market listings.

## Bugs Found

- Kalshi WebSocket default used an older supported host instead of the current recommended
  `external-api-ws.kalshi.com` host.
- Market-matching mismatch detection did not explicitly flag outcome direction, inclusive versus
  exclusive threshold wording, timezone, or resolution-source differences.
- Existing server processes could hold ports while not accepting sandboxed connections.
- README lacked several requested local setup, reset, and troubleshooting commands.

## Bugs Fixed

- Updated Kalshi WebSocket default URL in `backend/app/config.py` and `.env.example`.
- Added mismatch detection for direction, threshold wording, timezone, and resolution source.
- Added deterministic tests for those mismatch cases.
- Added deterministic arbitrage test for Kalshi YES + Polymarket NO.
- Added paper-trading max-position and duplicate-prevention test.
- Expanded README local setup, SQLite initialization, reset, CORS, connectivity, exchange failure,
  and stale-book troubleshooting sections.

## Files Changed During Audit

- `.env.example`
- `README.md`
- `SYSTEM_AUDIT.md`
- `backend/app/config.py`
- `backend/app/services/market_matching.py`
- `backend/tests/test_arbitrage.py`
- `backend/tests/test_market_matching.py`
- `backend/tests/test_paper_trading.py`

The repository already contained many Phase 1/Phase 2 modified and untracked files before this
audit. Those were treated as the working baseline and were not reverted.

## Configuration Findings

- `.env.example` documents local SQLite, in-memory local mode, exchange URLs, realtime settings,
  paper-trading settings, frontend API URL, and frontend WebSocket URL.
- `.gitignore` excludes `.env`, virtual environments, caches, build output, `node_modules`, SQLite
  database files, and Postgres data directories.
- `git ls-files` showed no tracked `.env`, local SQLite DB, `.next`, `node_modules`, or virtualenv.
- Local development uses SQLite and memory cache only when `LOCAL_DEVELOPMENT=true`.
- PostgreSQL and Redis remain configured for non-local and Docker Compose modes.
- Docker-only hostnames are present only in Docker Compose/tests/production examples, not in local
  startup commands.

## Security Findings

- No private keys, wallet seed phrases, hardcoded exchange secrets, bearer tokens, or API keys were
  found in repository scans.
- No live order-submission, wallet-signing, deposit, or withdrawal code was found in backend app
  code.
- Frontend code exposes only `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_WS_URL`.
- Kalshi credential settings are backend-only and are not returned by health or frontend APIs.
- CORS is limited by `BACKEND_CORS_ORIGINS`, defaulting to `http://localhost:3000`.
- Writable internal endpoints are limited to local database writes for market-match reviews and
  generated candidates; FastAPI/Pydantic validation rejects invalid status values.

## Performance Findings

- Frontend home page returned 200 in approximately 0.90s under dev server.
- Backend simulation route timings observed:
  - `/health`: ~0.04s
  - `/markets`: ~0.20s
  - `/opportunities`: ~0.16s
  - `/analytics/opportunities`: ~0.03s
  - `/paper-trades`: ~0.02s
  - `/order-books/status`: ~0.01s
- TestClient stress: 50 `/opportunities?data_mode=simulation` calls in 2.49s.
- Arbitrage detector stress: 1000 simulation detections in 0.52s.
- Observed backend RSS during audit:
  - Uvicorn reloader: ~7.8 MB
  - Clean-db backend worker: ~48.7 MB

Reliability concerns:

- Market-match review list has no pagination yet.
- Paper-trade list has a limit, but analytics query currently loads all paper records.
- Realtime WebSocket ingestors are present but local mode defaults to REST snapshots.
- No browser-console automation was available in this audit, so console-error verification is
  limited to frontend lint/build and HTTP page checks.

## End-to-End Workflow

Completed with simulated fixture data:

1. Started clean backend with `/private/tmp/pma_audit_clean.db`.
2. Verified startup and migration initialization.
3. Loaded simulation markets.
4. Generated 3 market-match candidates.
5. Manually marked one pair `verified_equivalent`.
6. Loaded simulation order books.
7. Detected 3 simulated arbitrage opportunities.
8. Created 3 PAPER TRADING simulations.
9. Verified analytics included PAPER TRADING metrics.
10. Restarted backend against the same clean DB.
11. Confirmed 1 verified match and 3 paper trades remained visible.
12. Verified frontend outage fallback while backend was stopped.
13. Restarted backend and confirmed frontend recovered and rendered PAPER TRADING content.

## Remaining Limitations

- Long-running live WebSocket ingestion was not run for several hours/days.
- Authenticated Kalshi WebSocket ingestion was not tested without credentials.
- Browser console errors were not inspected with a real browser automation tool during this audit.
- Date/category/ROI/liquidity/freshness filters are frontend-side for displayed opportunities;
  analytics API does not yet expose full server-side filter parameters.
- Market matching is still heuristic and reviewer-dependent; it does not prove legal/economic
  equivalence.
- External API schema/rate-limit changes can still break live adapters.
- The frontend table can grow large because market matches are not paginated.

## Known External API Risks

- Polymarket Gamma and CLOB endpoints can change payload fields or throttle requests.
- Kalshi market/orderbook responses can change field availability, especially around newer
  fixed-point dollar fields.
- Live market samples may contain sports or multivariate markets that normalize differently than
  current fixtures.
- Network latency can make paper-trading simulations diverge from displayed projections.

## Recommended Next Steps

- Run the app in simulation mode for a few hours and monitor paper-trade/history table growth.
- Add server-side pagination for market-match reviews and paper-trade analytics.
- Add Playwright browser checks for console errors, empty states, and backend outage recovery.
- Add authenticated Kalshi WebSocket tests only after server-side credentials are available.
- Replace deprecated Pydantic `json_encoders` before Pydantic v3.
- Add retention or compaction for historical order-book snapshots.
