# Position Settlement Audit

Audit date: 2026-07-31

## Root Cause

Model paper-trading positions were created with `status=open`, but there was no
resolution reconciliation path for `model_paper_trades`. The backend did not
poll exchange finalization state for open model paper positions, did not map the
exchange winning outcome back to normalized YES/NO, and did not persist
settlement fields. The frontend was accurately displaying the stale persisted
`open` status.

No live trading path was added or used.

## Affected Position

- Position ID: `0d145ee0978dea76ebd052a4`
- Opportunity ID: `595ba2b032576d9a2c6384aa`
- Prediction ID: `a49b1c3b8de6f02892c0c9eb`
- Model ID: `f03c9c31759e786990f3057d`
- Exchange: `kalshi`
- Exchange market ID: `KXWNBATOTAL-26JUL30NYLV-201`
- Outcome/token ID: not separately stored for this model paper-trade path
- Position side: `yes`
- Entry price: `0.17`
- Filled quantity: `2777.0028`
- Entry cost: `472.090476`
- Previous local status: `open`
- Previous exit reason: `null`
- Previous realized P&L: `0`
- Previous unrealized/mark-to-market P&L: `139.4486149077025250911450500`

## Exchange Resolution State

Live read-only Kalshi market lookup:

- Endpoint: `https://external-api.kalshi.com/trade-api/v2/markets/KXWNBATOTAL-26JUL30NYLV-201`
- Exchange status: `finalized`
- Result: `yes`
- Settlement timestamp: `2026-07-31T04:27:40.954912Z`
- Settlement value: `1.0000`

This was fully finalized on Kalshi, not merely inferred from the market price.

## Pipeline Stage That Failed

The failure occurred after paper trade creation:

1. Model opportunity was converted into a paper trade.
2. The paper trade was persisted with `status=open`.
3. The exchange later finalized the market.
4. No backend worker or manual tool checked open model paper positions against
   exchange finalization.
5. The API and frontend kept returning the persisted `open` row.

## Fix Implemented

- Added model paper-trade settlement fields:
  - `resolved_outcome`
  - `resolution_timestamp`
  - `last_resolution_check_timestamp`
  - `settlement_value`
- Added migration `0006_model_paper_trade_settlement.sql`.
- Added local SQLite schema repair for existing local databases.
- Added `PositionReconciliationService`.
- Added live-mode background reconciliation worker.
- Added `POST /model-paper-trades/reconcile`.
- Added CLI:
  - `python -m app.tools.reconcile_positions --position-id POSITION_ID --dry-run`
  - `python -m app.tools.reconcile_positions --position-id POSITION_ID --apply`
- Added structured logs:
  - `position_resolution_check_start`
  - `position_resolution_check_complete`
  - `position_resolution_check_error`
- Updated frontend model paper-trade table to show:
  - closed status
  - realized P&L for closed trades
  - resolved YES/NO
  - settlement timestamp
  - exit reason
- Scoped automatic reconciliation to the active data mode so live mode does not
  poll exchanges for legacy test records.

## Settlement Behavior

For resolved binary markets:

- YES position resolving YES pays `1.00` per filled contract.
- NO position resolving NO pays `1.00` per filled contract.
- Losing side pays `0.00`.
- Voided markets use the configured paper refund behavior and set
  `exit_reason=MARKET_VOIDED`.

Implemented settlement formula:

`realized_pnl = settlement_value - filled_quantity * entry_price`

The operation is idempotent because only `open` positions are selected for
settlement.

## Final Position State

- Final status: `closed`
- Final exit reason: `MARKET_RESOLVED`
- Resolved outcome: `yes`
- Resolution timestamp: `2026-07-31T04:27:40.954912Z`
- Last resolution check timestamp: `2026-07-31T04:37:06.138584Z`
- Final settlement value: `2777.0028`
- Final realized paper P&L: `2304.912324`
- Final mark-to-market P&L: `0`

The live backend API returns this row as closed, with settlement metadata.

## Database Changes

- Added nullable settlement columns to `model_paper_trades`.
- Updated affected row `0d145ee0978dea76ebd052a4` to `closed`.
- The background reconciler also closed two older finalized Kalshi model paper
  trades it found in the local database.
- Current local model paper-trade status counts:
  - `closed`: 3
  - `open`: 18

Manual idempotency check after closure:

`python -m app.tools.reconcile_positions --position-id 0d145ee0978dea76ebd052a4 --dry-run`

returned `[]`, because the position is no longer open and was not settled again.

## Exchange-Specific Mapping

Kalshi:

- Uses `market.status` and `market.result`.
- Requires `status in {"finalized", "settled"}` and `result in {"yes", "no"}`
  before settlement.
- Uses `settlement_ts` or `updated_time` as the resolution timestamp.
- Does not infer the winner from last price.
- Voided/cancelled/refunded markets are mapped to voided settlement behavior.

Polymarket:

- Queries the Gamma market record by condition ID.
- Requires closed/inactive market state and an explicit YES/NO winner field.
- Supports winner fields on the market and token records.
- Does not infer the winner from price.
- Voided/cancelled/refunded statuses are mapped to voided settlement behavior.

## Sports-Market Handling

The reconciler follows exchange finalization and market rules, not a third-party
scoreboard. Postponed or closed-but-not-finalized markets remain open. Voided,
cancelled, or refunded markets are closed with `MARKET_VOIDED`.

## Files Changed

- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/models/domain.py`
- `backend/app/persistence/database.py`
- `backend/app/services/position_reconciliation.py`
- `backend/app/services/prediction.py`
- `backend/app/tools/reconcile_positions.py`
- `backend/migrations/0006_model_paper_trade_settlement.sql`
- `backend/tests/test_history.py`
- `backend/tests/test_position_reconciliation.py`
- `frontend/app/models/ModelDashboardClient.tsx`
- `frontend/lib/types.ts`
- `POSITION_SETTLEMENT_AUDIT.md`

## Commands Run

- `python -m app.tools.reconcile_positions --position-id 0d145ee0978dea76ebd052a4 --dry-run`
- `python -m app.tools.reconcile_positions --position-id 0d145ee0978dea76ebd052a4 --apply`
- `curl -i http://127.0.0.1:8000/health`
- `curl http://127.0.0.1:8000/model-paper-trades?data_mode=live`
- `curl http://127.0.0.1:8000/model-analytics?data_mode=live`
- `.venv/bin/pytest tests/test_position_reconciliation.py -q`
- `.venv/bin/pytest -q`
- `.venv/bin/ruff check .`
- `.venv/bin/mypy app tests`
- `npm run test`
- `npm run lint`
- `npm run build`

## Test Results

Backend:

- `tests/test_position_reconciliation.py`: 15 passed
- Full backend pytest: 91 passed, 0 failed
- Ruff: passed
- Mypy: passed

Frontend:

- `npm run test`: 12 passed, 0 failed
- `npm run lint`: passed
- `npm run build`: passed

Warnings remaining:

- Pydantic `json_encoders` deprecation warnings.
- Starlette/httpx test-client deprecation warning.
- One joblib CPU-count warning.
- Intermittent aiosqlite thread warnings from pre-existing async test cleanup.

## Remaining Exchange Limitations

- Polymarket paper positions are settled only when an explicit winning YES/NO
  outcome is present in the exchange response.
- No outcome is inferred from price, last trade, midpoint, or chart state.
- Delayed finalization remains open until the exchange reports final settlement.
- Voided-market refund behavior is a paper-accounting policy, not an exchange
  cash movement.
