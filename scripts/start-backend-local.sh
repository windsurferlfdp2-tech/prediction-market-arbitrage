#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -e ".[dev]"

export LOCAL_DEVELOPMENT=true
export DATA_MODE="${DATA_MODE:-live}"
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./prediction_market_arb.db}"
export USE_FIXTURES="${USE_FIXTURES:-false}"
export BACKEND_CORS_ORIGINS="${BACKEND_CORS_ORIGINS:-http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001}"

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
