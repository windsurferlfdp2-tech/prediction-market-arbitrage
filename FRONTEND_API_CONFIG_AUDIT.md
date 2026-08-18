# Frontend API Config Audit

Audit date: 2026-07-25

## Exact root cause

The frontend did not have a local Next.js environment file in `frontend/.env.local`, and there was no `frontend/.env.example` to copy from. Next.js only loads environment files from the active Next project directory at startup, so values exported in another shell, placed in the backend directory, or placed at the repository root were not reliable for `frontend`.

The previous dev server also needed a restart after the environment file was created because `NEXT_PUBLIC_*` values are compiled into the Next.js runtime at startup.

## Environment files inspected

- `frontend/.env.local`: missing before the fix, created during the audit.
- `frontend/.env`: not present.
- `frontend/.env.development`: not present.
- `frontend/.env.example`: missing before the fix, created during the audit.
- `frontend/next.config.mjs`: valid project-local Next config; no API URL override found.
- `frontend/package.json`: `npm run dev` runs `next dev` and works when started from `frontend`.

## Variable names found

- Canonical frontend variable: `NEXT_PUBLIC_API_URL`.
- Optional frontend WebSocket variable: `NEXT_PUBLIC_WS_URL`.
- No active `NEXT_PUBLIC_BACKEND_URL` references were found.
- No active `http://backend:8000` Docker hostname references were found in frontend API calls.

## Files changed

- `.gitignore`
- `README.md`
- `frontend/.env.example`
- `frontend/.env.local` locally created; intentionally ignored by Git.
- `frontend/app/page.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/apiConfig.js`
- `frontend/lib/apiConfig.d.ts`
- `frontend/lib/apiConfig.test.mjs`
- `frontend/package.json`

## API configuration changes

- Added one centralized API URL utility in `frontend/lib/apiConfig.js`.
- Reads `process.env.NEXT_PUBLIC_API_URL`.
- Removes a trailing slash.
- Validates that the value is a valid `http://` or `https://` URL.
- Throws a clear development configuration error when missing.
- Prevents accidental request URLs containing `undefined`.
- Reused the centralized URL builder from `frontend/lib/api.ts`.

Required local file:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_WS_URL=ws://127.0.0.1:8000/ws/opportunities
```

## Backend connectivity results

- `GET http://127.0.0.1:8000/health`: 200 OK.
- `GET http://127.0.0.1:8000/openapi.json`: 200 OK.
- Backend remained alive after checking candidate generation and model paper-trade endpoints.

## CORS findings

- `OPTIONS http://127.0.0.1:8000/market-matches/generate` from `http://localhost:3000`: 200 OK.
- `Access-Control-Allow-Origin: http://localhost:3000`.
- `Access-Control-Allow-Methods: GET, POST, PATCH, OPTIONS`.
- `Access-Control-Allow-Headers: content-type`.
- `OPTIONS http://127.0.0.1:8000/model-paper-trades/run` from `http://127.0.0.1:3000`: 200 OK.
- `Access-Control-Allow-Origin: http://127.0.0.1:3000`.

## Actual request URLs verified

- Dashboard health URL: `http://127.0.0.1:8000/health?data_mode=live`.
- Dashboard opportunities URL: `http://127.0.0.1:8000/opportunities?data_mode=live`.
- Dashboard analytics URL: `http://127.0.0.1:8000/analytics/opportunities?data_mode=live`.
- Candidate generation URL: `http://127.0.0.1:8000/market-matches/generate?data_mode=live`.
- Model paper-trade run URL: `http://127.0.0.1:8000/model-paper-trades/run?data_mode=live`.

Frontend render verified at:

- `http://localhost:3000`

Next.js startup verified:

- `Next.js 16.2.10`
- `Environments: .env.local`

## Tests run

From `frontend`:

```bash
npm run lint
npm test
npm run build
```

Results:

- ESLint: passed.
- TypeScript typecheck: passed.
- API config tests: 8 passed, 0 failed, 0 skipped.
- Production build: passed.

API config tests cover:

- Missing `NEXT_PUBLIC_API_URL`.
- Valid `NEXT_PUBLIC_API_URL`.
- Trailing slash removal.
- Invalid URL rejection.
- Non-HTTP URL rejection.
- Health request URL construction.
- Candidate-generation request URL construction.
- Paper-trade request URL construction.

## Manual verification steps completed

1. Created `frontend/.env.local`.
2. Cleared stale Next.js state with `rm -rf .next`.
3. Restarted the frontend from `/Users/luciodelpin/prediction-market-arb-scanner/frontend`.
4. Confirmed Next.js loaded `.env.local`.
5. Rendered the dashboard with `curl http://localhost:3000`.
6. Confirmed the missing `NEXT_PUBLIC_API_URL` message was not present.
7. Confirmed no frontend request path uses a Docker-only backend hostname.

## Exact commands to run next

Backend:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/backend
source .venv/bin/activate
export LOCAL_DEVELOPMENT=true
export DATABASE_URL=sqlite+aiosqlite:///./prediction_market_arb.db
export DATA_MODE=live
export USE_FIXTURES=false
export MODEL_LIVE_MARKET_LIMIT=5
export LIVE_SCAN_MARKET_LIMIT=25
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd /Users/luciodelpin/prediction-market-arb-scanner/frontend
cp .env.example .env.local
npm install
rm -rf .next
npm run dev
```

If `frontend/.env.local` already exists, confirm it contains:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Restart the frontend after changing any `NEXT_PUBLIC_*` value.
