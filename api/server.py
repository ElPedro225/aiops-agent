"""
File: api/server.py
Purpose: FastAPI REST backend exposing timeline data and agent control endpoints.
Layer: API layer — sits between main.py pipeline and the dashboard frontend.

Run with:
    uvicorn api.server:app --reload --host 0.0.0.0 --port 8000

Endpoints:
    GET  /           → health check
    GET  /timeline   → latest timeline events from SQLite (falls back to timeline.json)
    GET  /history    → all historical events from SQLite, paginated
    GET  /runs       → summary of each distinct agent run
    GET  /drift      → latest drift report JSON
    POST /run        → trigger run_agent() in a background thread
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="AIOps Agent API", version="1.0.0")

# Intent: open CORS so the vanilla HTML dashboard served from any origin can reach this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPORT_DIR = _PROJECT_ROOT / "reports"
_DB_PATH = _PROJECT_ROOT / "reports" / "aiops.db"

_agent_lock = threading.Lock()
_agent_running = False


def _get_db():
    from storage.db import init_db
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    return init_db(_DB_PATH)


@app.get("/")
def health():
    """Health check — confirms the API server is running."""
    timeline_path = _REPORT_DIR / "timeline.json"
    return {
        "status": "ok",
        "agent_running": _agent_running,
        "timeline_exists": timeline_path.exists(),
        "db_exists": _DB_PATH.exists(),
    }


@app.get("/timeline")
def get_timeline(limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    """Return the most recent timeline events.

    Prefers SQLite if the DB exists, falls back to timeline.json for compatibility.
    """
    if _DB_PATH.exists():
        try:
            conn = _get_db()
            from storage.db import query_events
            events = query_events(conn, limit=limit)
            conn.close()
            # Intent: normalize SQLite INTEGER booleans to JSON booleans so JS === comparisons work correctly.
            for e in events:
                e["executed"] = bool(e.get("executed", 0))
                e["z_anomaly"] = bool(e.get("z_anomaly", 0))
            return events
        except Exception:
            pass

    # Fallback: read from timeline.json
    timeline_path = _REPORT_DIR / "timeline.json"
    if not timeline_path.exists():
        return []
    try:
        return json.loads(timeline_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read timeline: {exc}")


@app.get("/history")
def get_history(
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """Return historical events from SQLite with pagination."""
    if not _DB_PATH.exists():
        raise HTTPException(status_code=404, detail="No database found. Run the agent first.")
    try:
        conn = _get_db()
        cursor = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        for r in rows:
            r["executed"] = bool(r.get("executed", 0))
            r["z_anomaly"] = bool(r.get("z_anomaly", 0))
        return rows
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/runs")
def get_runs() -> list[dict[str, Any]]:
    """Return a summary of each distinct agent run."""
    if not _DB_PATH.exists():
        return []
    try:
        conn = _get_db()
        from storage.db import query_runs
        runs = query_runs(conn)
        conn.close()
        return runs
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/drift")
def get_drift() -> dict[str, Any]:
    """Return the latest drift report JSON."""
    # Intent: serve the most recently written drift report file.
    report_files = sorted(_REPORT_DIR.glob("drift_report_*.json"), reverse=True)
    if not report_files:
        fallback = _REPORT_DIR / "drift_report.json"
        if fallback.exists():
            report_files = [fallback]

    if not report_files:
        return {"error": "No drift report found. Run the agent first."}
    try:
        return json.loads(report_files[0].read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _run_agent_background() -> None:
    global _agent_running
    try:
        _agent_running = True
        from main import run_agent
        run_agent()
    finally:
        _agent_running = False


@app.post("/run")
def trigger_run(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Trigger a full agent run in the background.

    Returns immediately; poll GET / to check agent_running status.
    """
    global _agent_running
    with _agent_lock:
        if _agent_running:
            raise HTTPException(status_code=409, detail="Agent is already running.")
        background_tasks.add_task(_run_agent_background)
    return {"status": "started", "message": "Agent run started in background. Poll GET / to check status."}
