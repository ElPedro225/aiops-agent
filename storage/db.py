"""
File: storage/db.py
Purpose: Persist timeline events to SQLite so history survives across runs.
Layer: Storage layer — called from main.py after each decision is made.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any


_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT    NOT NULL,
    row_index     INTEGER,
    timestamp     TEXT,
    service       TEXT,
    anomaly_score REAL,
    z_score       REAL,
    iforest_score REAL,
    z_anomaly     INTEGER,
    drift_share   REAL,
    share_missing REAL,
    decision      TEXT,
    action        TEXT,
    executed      INTEGER,
    result        TEXT,
    decision_summary TEXT,
    llm_explanation  TEXT
);
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Open (or create) the SQLite database and ensure the events table exists."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE_SQL)
    conn.commit()
    return conn


def new_run_id() -> str:
    """Generate a unique run ID to group events from a single agent execution."""
    return str(uuid.uuid4())


def insert_event(conn: sqlite3.Connection, event: dict[str, Any], run_id: str) -> None:
    """Insert a single timeline event into the events table."""
    conn.execute(
        """
        INSERT INTO events (
            run_id, row_index, timestamp, service, anomaly_score, z_score,
            iforest_score, z_anomaly, drift_share, share_missing,
            decision, action, executed, result, decision_summary, llm_explanation
        ) VALUES (
            :run_id, :row_index, :timestamp, :service, :anomaly_score, :z_score,
            :iforest_score, :z_anomaly, :drift_share, :share_missing,
            :decision, :action, :executed, :result, :decision_summary, :llm_explanation
        )
        """,
        {
            "run_id": run_id,
            "row_index": int(event.get("index", 0)),
            "timestamp": str(event.get("timestamp", "")),
            "service": str(event.get("service", "")),
            "anomaly_score": float(event.get("anomaly_score", 0.0)),
            "z_score": float(event.get("z_score", 0.0)),
            "iforest_score": float(event.get("iforest_score", 0.0)),
            "z_anomaly": int(bool(event.get("z_anomaly", False))),
            "drift_share": float(event.get("drift_share", 0.0)),
            "share_missing": float(event.get("share_missing", 0.0)),
            "decision": str(event.get("decision", "")),
            "action": str(event.get("action", "")),
            "executed": int(bool(event.get("executed", False))),
            "result": str(event.get("result", "")),
            "decision_summary": str(event.get("decision_summary", "")),
            "llm_explanation": str(event.get("llm_explanation", "")),
        },
    )
    conn.commit()


def query_events(conn: sqlite3.Connection, limit: int = 500) -> list[dict[str, Any]]:
    """Return the most recent events as a list of dicts, newest first."""
    cursor = conn.execute(
        "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
    )
    return [dict(row) for row in cursor.fetchall()]


def query_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return summary info for each distinct run_id."""
    cursor = conn.execute(
        """
        SELECT run_id,
               COUNT(*) AS total_events,
               SUM(CASE WHEN decision = 'AUTO'     THEN 1 ELSE 0 END) AS auto_count,
               SUM(CASE WHEN decision = 'CONFIRM'  THEN 1 ELSE 0 END) AS confirm_count,
               SUM(CASE WHEN decision = 'ESCALATE' THEN 1 ELSE 0 END) AS escalate_count,
               MIN(timestamp) AS first_event,
               MAX(timestamp) AS last_event
        FROM events
        GROUP BY run_id
        ORDER BY last_event DESC
        LIMIT 50
        """
    )
    return [dict(row) for row in cursor.fetchall()]
