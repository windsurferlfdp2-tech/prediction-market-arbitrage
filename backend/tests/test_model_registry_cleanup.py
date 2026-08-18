from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.tools.cleanup_duplicate_models import _apply_cleanup, _duplicate_groups


def test_duplicate_model_cleanup_preserves_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanup.db"
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    _create_tables(con)
    _insert_model(con, "old-model", "2026-07-20T00:00:00Z")
    _insert_model(con, "new-model", "2026-07-21T00:00:00Z")
    for table in ("model_predictions", "model_opportunities", "model_paper_trades"):
        con.execute(
            f"INSERT INTO {table} (id, model_id, payload) VALUES (?, ?, ?)",
            (
                f"{table}-row",
                "old-model",
                json.dumps({"model_id": "old-model", "nested": {"model_id": "old-model"}}),
            ),
        )
    con.commit()

    groups = _duplicate_groups(con)
    _apply_cleanup(con, groups)
    con.commit()

    assert groups == [
        {
            "fingerprint": "same-fingerprint",
            "canonical_id": "new-model",
            "duplicate_ids": ["old-model"],
            "record_count": 2,
        }
    ]
    assert con.execute("SELECT COUNT(*) FROM prediction_models").fetchone()[0] == 1
    for table in ("model_predictions", "model_opportunities", "model_paper_trades"):
        row = con.execute(f"SELECT model_id, payload FROM {table}").fetchone()
        assert row["model_id"] == "new-model"
        payload = json.loads(row["payload"])
        assert payload["model_id"] == "new-model"
        assert payload["nested"]["model_id"] == "new-model"


def _create_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE prediction_models (
            id TEXT PRIMARY KEY,
            name TEXT,
            category TEXT,
            version TEXT,
            status TEXT,
            model_type TEXT,
            training_timestamp TEXT,
            training_start TEXT,
            training_end TEXT,
            feature_schema_version TEXT,
            training_sample_count INTEGER,
            validation_metrics TEXT,
            calibration_method TEXT,
            calibration_metrics TEXT,
            artifact_path TEXT,
            source_identifier TEXT,
            training_fingerprint TEXT,
            artifact_hash TEXT,
            dataset_version TEXT,
            resolved_market_count INTEGER,
            validation_sample_count INTEGER,
            baseline_score TEXT,
            model_score TEXT,
            metadata_payload TEXT
        )
        """
    )
    for table in ("model_predictions", "model_opportunities", "model_paper_trades"):
        con.execute(f"CREATE TABLE {table} (id TEXT PRIMARY KEY, model_id TEXT, payload TEXT)")


def _insert_model(con: sqlite3.Connection, model_id: str, training_timestamp: str) -> None:
    con.execute(
        """
        INSERT INTO prediction_models (
            id, name, category, version, status, model_type, training_timestamp,
            training_start, training_end, feature_schema_version, training_sample_count,
            validation_metrics, calibration_method, calibration_metrics, artifact_path,
            source_identifier, training_fingerprint, artifact_hash, dataset_version,
            resolved_market_count, validation_sample_count, baseline_score, model_score,
            metadata_payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            model_id,
            "phase3_market_anchored_ensemble",
            "general",
            f"phase3-{model_id}",
            "approved_for_paper",
            "ensemble",
            training_timestamp,
            "2026-01-24T00:00:00Z",
            "2026-02-18T00:00:00Z",
            "phase3.v1",
            48,
            json.dumps({"brier_score": 0.1828}),
            "platt",
            json.dumps({"calibration_version": "phase3.calibration.v1"}),
            f"model_artifacts/{model_id}.pkl",
            "phase3_prediction_service",
            "same-fingerprint",
            "hash",
            "dataset",
            6,
            12,
            "0.1301",
            "0.1828",
            json.dumps({"seed": 42}),
        ),
    )
