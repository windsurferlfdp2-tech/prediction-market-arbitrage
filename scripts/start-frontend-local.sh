#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../frontend"

npm install

export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:8000}"
export NEXT_PUBLIC_WS_URL="${NEXT_PUBLIC_WS_URL:-ws://localhost:8000/ws/opportunities}"

npm run dev
