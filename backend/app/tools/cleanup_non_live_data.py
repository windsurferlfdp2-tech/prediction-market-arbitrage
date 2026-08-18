from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings

NON_LIVE_VALUES = {"simulation", "fixtures", "fixture", "test", "mock", "demo", "synthetic"}
PAYLOAD_TABLES = [
    "opportunities",
    "paper_trade_simulations",
    "model_predictions",
    "model_opportunities",
    "model_paper_trades",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Report or remove non-live runtime records.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up SQLite DB and delete records.",
    )
    args = parser.parse_args()
    if args.apply == args.dry_run:
        parser.error("pass exactly one of --dry-run or --apply")

    db_path = _sqlite_path()
    if db_path is None:
        raise SystemExit("cleanup currently supports local SQLite DATABASE_URL only")
    if not db_path.exists():
        raise SystemExit(f"database does not exist: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        report = audit(conn)
        print(json.dumps(report, indent=2, sort_keys=True))
        if args.dry_run:
            return

        backup = db_path.with_name(
            f"{db_path.name}.backup-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        )
        shutil.copy2(db_path, backup)
        deleted = apply_cleanup(conn)
        print(json.dumps({"backup": str(backup), "deleted": deleted}, indent=2, sort_keys=True))


def audit(conn: sqlite3.Connection) -> dict[str, object]:
    report: dict[str, object] = {"database": str(_sqlite_path()), "non_live_records": {}}
    non_live: dict[str, object] = {}
    if _table_exists(conn, "opportunity_history"):
        rows = conn.execute(
            "SELECT data_mode, COUNT(*) AS count FROM opportunity_history "
            "WHERE data_mode != 'live' GROUP BY data_mode ORDER BY data_mode"
        ).fetchall()
        non_live["opportunity_history"] = {row["data_mode"]: row["count"] for row in rows}
    if _table_exists(conn, "order_book_snapshots"):
        transport_values = "'simulation','test','fixture','fixtures','mock','demo','synthetic'"
        rows = conn.execute(
            "SELECT transport, COUNT(*) AS count FROM order_book_snapshots "
            f"WHERE transport IN ({transport_values}) "
            "GROUP BY transport ORDER BY transport"
        ).fetchall()
        non_live["order_book_snapshots"] = {row["transport"]: row["count"] for row in rows}
    for table in PAYLOAD_TABLES:
        if not _table_exists(conn, table):
            continue
        non_live[table] = _payload_non_live_counts(conn, table)
    report["non_live_records"] = non_live
    return report


def apply_cleanup(conn: sqlite3.Connection) -> dict[str, int]:
    deleted: dict[str, int] = {}
    if _table_exists(conn, "opportunity_history"):
        deleted["opportunity_history"] = conn.execute(
            "DELETE FROM opportunity_history WHERE data_mode != 'live'"
        ).rowcount
    if _table_exists(conn, "order_book_snapshots"):
        transport_values = "'simulation','test','fixture','fixtures','mock','demo','synthetic'"
        deleted["order_book_snapshots"] = conn.execute(
            "DELETE FROM order_book_snapshots "
            f"WHERE transport IN ({transport_values})"
        ).rowcount
    for table in PAYLOAD_TABLES:
        if not _table_exists(conn, table):
            continue
        ids = _payload_non_live_ids(conn, table)
        if not ids:
            deleted[table] = 0
            continue
        placeholders = ",".join("?" for _ in ids)
        deleted[table] = conn.execute(
            f"DELETE FROM {table} WHERE id IN ({placeholders})",
            ids,
        ).rowcount
    conn.commit()
    return deleted


def _payload_non_live_counts(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in conn.execute(f"SELECT id, payload FROM {table}"):
        source = _payload_source(row["payload"])
        if source in NON_LIVE_VALUES:
            counts[source] = counts.get(source, 0) + 1
    return counts


def _payload_non_live_ids(conn: sqlite3.Connection, table: str) -> list[str]:
    ids: list[str] = []
    for row in conn.execute(f"SELECT id, payload FROM {table}"):
        if _payload_source(row["payload"]) in NON_LIVE_VALUES:
            ids.append(str(row["id"]))
    return ids


def _payload_source(payload_text: str | bytes | None) -> str:
    if not payload_text:
        return "unknown"
    try:
        payload = json.loads(payload_text)
    except (TypeError, json.JSONDecodeError):
        return "unknown"
    candidates = [
        payload.get("data_source"),
        payload.get("data_mode"),
        payload.get("label"),
        payload.get("market_title"),
        payload.get("title"),
    ]
    nested = payload.get("simulation")
    if isinstance(nested, dict):
        candidates.extend([nested.get("data_source"), nested.get("label")])
    for value in candidates:
        if not isinstance(value, str):
            continue
        lower = value.lower()
        for source in NON_LIVE_VALUES:
            if source in lower:
                return source
    if isinstance(nested, dict) and nested.get("data_source") is None:
        return "simulation"
    return "live"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _sqlite_path() -> Path | None:
    url = settings.effective_database_url
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url.removeprefix(prefix)
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


if __name__ == "__main__":
    main()
