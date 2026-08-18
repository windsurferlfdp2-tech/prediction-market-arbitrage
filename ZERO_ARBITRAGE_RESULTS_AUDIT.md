# Zero Live Arbitrage Results Audit

Audit timestamp: 2026-07-31T02:57:32Z

## Summary

The live scanner is fetching live Polymarket and Kalshi markets successfully, and direct read-only order-book probes work for both exchanges. The live arbitrage funnel reaches zero at the manually verified market-pair gate:

`verified_pairs_total = 0`

Because the scanner is configured to evaluate only manually verified cross-platform equivalent pairs, it correctly refuses to fetch order books for arbitrary unmatched markets and returns zero live arbitrage opportunities.

Zero current live arbitrage results are therefore legitimate under the current safety rules. The system had no verified live Polymarket/Kalshi pair to scan.

## Funnel Counts

Latest tested scanner run:

- Latest completed scan timestamp: 2026-07-31T02:57:09.010537Z
- Data mode: live
- Markets fetched: 50
- Markets normalized: 50
- Polymarket normalized: 25
- Kalshi normalized: 25
- Verified equivalent pairs total: 0
- Verified pairs active on both exchanges: 0
- Executable markets from verified pairs: 0
- Usable order books loaded by scanner: 0
- Verified pairs with fresh books: 0
- Raw pricing discrepancies detected: 0
- Opportunities after fees: 0
- Opportunities after slippage: 0
- Opportunities after liquidity checks: 0
- Opportunities after freshness checks: 0
- Final opportunities persisted: 0
- Final opportunities returned by API: 0
- First zero stage: `verified_pairs_total`

## Live Exchange Checks

### Polymarket

- Endpoint used: `https://gamma-api.polymarket.com/markets`
- Order-book endpoint probed: `https://clob.polymarket.com/book`
- Latest successful market fetch: 2026-07-31T02:57:08.664978Z
- Active markets received in scanner run: 25
- Normalized: 25
- Rejected: 0
- Scanner order books requested: 0 because no verified pairs existed
- Separate read-only order-book probe:
  - Markets probed: 2
  - Book requests: 4
  - Books returned: 4
  - Fresh books: 4
  - Markets with both YES and NO books: 2
  - Sample best prices: YES bid 0.5, YES ask 0.51, NO bid 0.49, NO ask 0.5

### Kalshi

- Endpoint used: `https://external-api.kalshi.com/trade-api/v2/markets`
- Order-book endpoint probed: `https://external-api.kalshi.com/trade-api/v2/markets/{ticker}/orderbook`
- Latest successful market fetch: 2026-07-31T02:57:08.993388Z
- Active markets received in scanner run: 25
- Normalized: 25
- Rejected: 0
- Authentication status: not required for configured market-data requests
- Scanner order books requested: 0 because no verified pairs existed
- Separate read-only order-book probe:
  - Markets probed: 2
  - Book requests: 2
  - Books returned: 4
  - Fresh books: 4
  - Markets with both YES and NO books: 2
  - Sample best prices: YES bid 0.0800, YES ask 0.1000, NO bid 0.9000, NO ask 0.9200

## Market Matching

- Market-match review records after live generation: 35
- Status counts:
  - `pending_review`: 30
  - legacy `Pending review`: 5
- Verified equivalent pairs: 0
- Rejected pairs: 0
- Related-but-not-equivalent pairs: 0

Live candidate generation works, but the generated examples were all pending and had explicit mismatches such as unrelated entities and outcome direction differences. None were approved automatically.

## Order-Book Availability

The scanner does not load order books without verified pairs. This is intentional. A separate live adapter probe verified that both exchange adapters can fetch fresh books and normalize both sides.

Kalshi price conversion was audited and tested:

- Kalshi prices are treated as decimal dollars.
- YES bids remain YES bids.
- NO bids remain NO bids.
- YES asks are derived from NO bids as `1 - NO bid`.
- NO asks are derived from YES bids as `1 - YES bid`.
- No double division by 100 was detected in the tested conversion helpers.

## Arbitrage Calculation Strategy

Active strategy:

- Cross-platform manually verified equivalent pairs only.

Inactive strategies:

- Polymarket YES + Polymarket NO
- Kalshi YES + Kalshi NO
- Multi-outcome complete-set arbitrage

The deterministic engine test with a verified fixture pair and fresh books detects:

- Polymarket YES ask: 0.45
- Kalshi NO ask: 0.50
- Quantity: 10
- Total cost: 9.50
- Payout: 10
- Gross profit: 0.50
- Fees: 0.00
- Slippage: 0.00
- Net profit: 0.50
- ROI: 0.50 / 9.50

This proves the calculation path works when a verified pair and executable books exist.

## Thresholds

- Minimum net profit: 0.01
- Minimum ROI: 0.001
- Maximum order-book age: 30 seconds
- Fee rate: 0.0000
- Slippage rate: 0.0000
- Live scan market limit: 25 per exchange
- Paper max position: 100

No thresholds were lowered.

## Database Findings

SQLite database: `backend/prediction_market_arb.db`

- `market_pair_reviews`: 35
- `opportunity_history`: 243
- `opportunities`: 0
- `opportunity_history` by data mode:
  - `live`: 243
- Latest historical opportunity detected timestamp: 2026-07-20 16:09:39.237570
- Active historical opportunity rows: 0

The 243 old rows are closed historical records from July 20, 2026. They are not current executable opportunities. Current live analytics excluded those historical rows from today’s metrics:

- `historical_records_excluded`: 243
- Current-day raw detections: 0
- Current-day unique opportunities: 0
- Current-day median ROI: 0
- Current-day maximum theoretical profit: 0

## Bugs Found

1. The scanner status did not expose enough funnel diagnostics to distinguish legitimate zero results from broken ingestion.
2. Individual malformed live order-book responses could abort the full adapter book fetch.
3. The frontend did not display the scanner’s zero-result reason or rejection counters.
4. The scanner is request-driven, not a startup background loop. It runs when `/opportunities` or the websocket path requests a refresh. It does not continuously scan unless something is polling it.

## Bugs Fixed

1. Added detector rejection counters and raw discrepancy counts.
2. Added scanner funnel diagnostics and `/scanner/diagnostics`.
3. Added exchange adapter fetch/order-book diagnostics.
4. Made per-market order-book failures non-fatal and visible in diagnostics.
5. Added dashboard fields for first zero stage, live markets fetched, usable books, active verified pairs, pairs evaluated, raw discrepancies, and top rejection reasons.
6. Added a clear healthy-zero dashboard message.
7. Added deterministic tests for Kalshi price conversion, rejection counters, and verified-pair persistence through the history recorder.

## Files Changed In This Audit

- `backend/app/arbitrage/detector.py`
- `backend/app/exchanges/kalshi.py`
- `backend/app/exchanges/polymarket.py`
- `backend/app/services/scanner.py`
- `backend/app/main.py`
- `backend/tests/test_adapters.py`
- `backend/tests/test_arbitrage.py`
- `backend/tests/test_market_matching.py`
- `frontend/app/components/OpportunityDashboard.tsx`
- `frontend/app/globals.css`
- `frontend/lib/types.ts`
- `ZERO_ARBITRAGE_RESULTS_AUDIT.md`

No database migrations were added.

## Commands Run

Backend and live route checks:

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS 'http://127.0.0.1:8000/markets?data_mode=live'
curl -sS 'http://127.0.0.1:8000/opportunities?data_mode=live'
curl -sS 'http://127.0.0.1:8000/scanner/status?data_mode=live'
curl -sS 'http://127.0.0.1:8000/scanner/diagnostics?data_mode=live'
curl -sS -X POST 'http://127.0.0.1:8000/market-matches/generate?data_mode=live'
curl -sS 'http://127.0.0.1:8000/analytics/opportunities?data_mode=live'
```

Tests and checks:

```bash
cd backend
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy app

cd ../frontend
npm run test
npm run lint
npm run build
```

## Test Results

- Backend pytest: 76 passed, 0 failed, 0 skipped
- Backend ruff: passed
- Backend mypy: passed
- Frontend tests/typecheck: 12 passed, 0 failed, 0 skipped
- Frontend lint: passed
- Frontend production build: passed

Warnings:

- Pydantic V2 `json_encoders` deprecation warnings.
- Starlette `httpx` TestClient deprecation warning.
- joblib physical-core detection warning during one model paper trade route test.

## Remaining Limitations

1. No manually verified live equivalent pairs exist, so the live arbitrage engine has no safe pairs to evaluate.
2. The scanner is request-driven rather than a continuous background loop. Continuous observation requires the frontend/websocket or an external poller to keep requesting scans.
3. The matching candidate generator can produce low-quality pending candidates when the limited live sample contains unrelated markets. Manual approval remains required.
4. Current arbitrage support is cross-platform only for verified pairs. Same-platform complete-set strategies are not implemented.
5. The local database still contains 243 closed historical records from July 20, 2026; live current-day analytics exclude them.

## Conclusion

The absence of current live arbitrage results is not caused by failed live market ingestion, failed order-book parsing, or a broken arbitrage calculation engine. The current blocker is that there are zero manually verified active equivalent Polymarket/Kalshi pairs, so the scanner has no approved cross-platform contracts to evaluate.

The system now reports this explicitly through `/scanner/diagnostics` and the frontend diagnostics panel.
