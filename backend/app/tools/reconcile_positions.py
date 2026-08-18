import argparse
import asyncio
import json
from typing import Any, cast

from app.config import SwitchableDataMode, settings
from app.persistence.database import AsyncSessionLocal, init_db
from app.services.position_reconciliation import PositionReconciliationService


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile open model paper-trading positions.")
    parser.add_argument("--position-id", help="Only reconcile one model paper-trade position.")
    parser.add_argument("--market-id", help="Only reconcile positions for one exchange market ID.")
    parser.add_argument("--all-open", action="store_true", help="Reconcile all open positions.")
    parser.add_argument(
        "--data-mode",
        choices=["live", "test"],
        default=settings.effective_data_mode,
        help="Only reconcile positions from this data mode.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show proposed changes without committing.",
    )
    parser.add_argument("--apply", action="store_true", help="Commit settlement changes.")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        parser.error("--apply and --dry-run are mutually exclusive")
    if not args.position_id and not args.market_id and not args.all_open:
        parser.error("provide --position-id, --market-id, or --all-open")

    asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> None:
    await init_db()
    service = PositionReconciliationService(settings, AsyncSessionLocal)
    results = await service.reconcile(
        position_id=args.position_id,
        market_id=args.market_id,
        data_mode=cast(SwitchableDataMode, args.data_mode),
        apply=args.apply,
    )
    print(json.dumps([_json_safe(result.as_dict()) for result in results], indent=2))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


if __name__ == "__main__":
    main()
