from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings

REFERENCE_TABLES = (
    "model_predictions",
    "model_opportunities",
    "model_paper_trades",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find and optionally remove duplicate prediction model registry rows."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Report duplicate groups only.")
    mode.add_argument("--apply", action="store_true", help="Backup DB and remove duplicate rows.")
    args = parser.parse_args()

    db_path = _sqlite_path(settings.effective_database_url)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        groups = _duplicate_groups(con)
        report = _build_report(con, groups, dry_run=args.dry_run)
        print(json.dumps(report, indent=2, sort_keys=True))
        if args.apply:
            backup = _backup_database(db_path)
            print(json.dumps({"backup": str(backup)}, indent=2))
            _apply_cleanup(con, groups)
            con.commit()
            print(json.dumps({"cleanup_applied": True}, indent=2))
    finally:
        con.close()


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        raise SystemExit("duplicate model cleanup currently supports SQLite local databases only")
    path = database_url.removeprefix(prefix)
    return Path(path).resolve()


def _duplicate_groups(con: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = con.execute("SELECT * FROM prediction_models ORDER BY training_timestamp").fetchall()
    by_fingerprint: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        by_fingerprint[_fingerprint(row)].append(row)
    groups: list[dict[str, Any]] = []
    for fingerprint, records in by_fingerprint.items():
        if len(records) < 2:
            continue
        canonical = _canonical_record(records)
        duplicate_ids = [record["id"] for record in records if record["id"] != canonical["id"]]
        groups.append(
            {
                "fingerprint": fingerprint,
                "canonical_id": canonical["id"],
                "duplicate_ids": duplicate_ids,
                "record_count": len(records),
            }
        )
    return groups


def _canonical_record(records: list[sqlite3.Row]) -> sqlite3.Row:
    def sort_key(row: sqlite3.Row) -> tuple[int, str]:
        approved = 1 if row["status"] == "approved_for_paper" else 0
        return (approved, str(row["training_timestamp"]))

    return sorted(records, key=sort_key)[-1]


def _build_report(
    con: sqlite3.Connection,
    groups: list[dict[str, Any]],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    duplicate_ids = [duplicate_id for group in groups for duplicate_id in group["duplicate_ids"]]
    references: dict[str, int] = {}
    for table in REFERENCE_TABLES:
        if not duplicate_ids:
            references[table] = 0
            continue
        placeholders = ",".join("?" for _ in duplicate_ids)
        references[table] = int(
            con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE model_id IN ({placeholders})",
                duplicate_ids,
            ).fetchone()[0]
        )
    return {
        "database": str(_sqlite_path(settings.effective_database_url)),
        "duplicate_group_count": len(groups),
        "duplicate_row_count": len(duplicate_ids),
        "unique_actual_models": int(
            con.execute("SELECT COUNT(*) FROM prediction_models").fetchone()[0]
        )
        - len(duplicate_ids),
        "groups": groups,
        "references_to_reassign": references,
        "dry_run": dry_run,
    }


def _apply_cleanup(con: sqlite3.Connection, groups: list[dict[str, Any]]) -> None:
    for group in groups:
        canonical_id = group["canonical_id"]
        for duplicate_id in group["duplicate_ids"]:
            for table in REFERENCE_TABLES:
                _reassign_table(con, table, duplicate_id, canonical_id)
            con.execute("DELETE FROM prediction_models WHERE id = ?", (duplicate_id,))
    _backfill_model_metadata(con)


def _reassign_table(
    con: sqlite3.Connection,
    table: str,
    duplicate_id: str,
    canonical_id: str,
) -> None:
    rows = con.execute(
        f"SELECT id, payload FROM {table} WHERE model_id = ?",
        (duplicate_id,),
    ).fetchall()
    for row in rows:
        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        updated_payload = _replace_model_id(payload, duplicate_id, canonical_id)
        con.execute(
            f"UPDATE {table} SET model_id = ?, payload = ? WHERE id = ?",
            (canonical_id, json.dumps(updated_payload), row["id"]),
        )


def _replace_model_id(value: Any, old: str, new: str) -> Any:
    if isinstance(value, dict):
        return {
            key: (new if key == "model_id" and item == old else _replace_model_id(item, old, new))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_model_id(item, old, new) for item in value]
    return value


def _backup_database(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = db_path.with_name(f"{db_path.name}.model-registry-backup-{stamp}")
    shutil.copy2(db_path, backup)
    return backup


def _backfill_model_metadata(con: sqlite3.Connection) -> None:
    rows = con.execute("SELECT * FROM prediction_models").fetchall()
    for row in rows:
        metadata = _json(row["metadata_payload"])
        validation_metrics = _json(row["validation_metrics"])
        artifact_path = Path(str(row["artifact_path"]))
        artifact_hash = (
            _file_hash(artifact_path) if artifact_path.exists() else row["artifact_hash"]
        )
        train_ids = set(metadata.get("train_market_ids", []))
        validation_ids = set(metadata.get("validation_market_ids", []))
        con.execute(
            """
            UPDATE prediction_models
            SET training_fingerprint = ?,
                artifact_hash = ?,
                dataset_version = ?,
                resolved_market_count = ?,
                validation_sample_count = ?,
                baseline_score = ?,
                model_score = ?
            WHERE id = ?
            """,
            (
                _fingerprint(row),
                artifact_hash,
                _dataset_version(row),
                len(train_ids | validation_ids) or None,
                validation_metrics.get("prediction_count") or len(validation_ids) or None,
                validation_metrics.get("market_baseline_brier_score"),
                validation_metrics.get("brier_score"),
                row["id"],
            ),
        )


def _file_hash(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(row: sqlite3.Row) -> str:
    if _has_value(row, "training_fingerprint"):
        return str(row["training_fingerprint"])
    metadata = _json(row["metadata_payload"])
    calibration_metrics = _json(row["calibration_metrics"])
    payload = {
        "name": row["name"],
        "category": row["category"],
        "model_type": row["model_type"],
        "training_start": _canonical_time(row["training_start"]),
        "training_end": _canonical_time(row["training_end"]),
        "feature_schema_version": row["feature_schema_version"],
        "training_sample_count": row["training_sample_count"],
        "seed": metadata.get("seed"),
        "requested_category": metadata.get("requested_category", row["category"]),
        "effective_category": metadata.get("effective_category", row["category"]),
        "fallback_reason": metadata.get("fallback_reason"),
        "feature_names": metadata.get("feature_names"),
        "train_market_ids": sorted(metadata.get("train_market_ids", [])),
        "validation_market_ids": sorted(metadata.get("validation_market_ids", [])),
        "calibration_method": row["calibration_method"],
        "calibration_version": calibration_metrics.get("calibration_version"),
    }
    import hashlib

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return f"legacy-{hashlib.sha256(encoded).hexdigest()}"


def _dataset_version(row: sqlite3.Row) -> str:
    metadata = _json(row["metadata_payload"])
    payload = {
        "feature_schema_version": row["feature_schema_version"],
        "training_start": _canonical_time(row["training_start"]),
        "training_end": _canonical_time(row["training_end"]),
        "train_market_ids": sorted(metadata.get("train_market_ids", [])),
        "validation_market_ids": sorted(metadata.get("validation_market_ids", [])),
    }
    import hashlib

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return f"dataset-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _has_value(row: sqlite3.Row, column: str) -> bool:
    return column in row.keys() and row[column] not in {None, ""}


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


def _canonical_time(value: str) -> str:
    return value[:10] if value else ""


if __name__ == "__main__":
    main()
