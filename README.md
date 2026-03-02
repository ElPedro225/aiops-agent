# AIOps Agent

A Python prototype that simulates microservice telemetry, detects anomalies, routes incidents through confidence-based policy tiers (`AUTO`, `CONFIRM`, `ESCALATE`), sends real mobile push notifications, and exposes a live REST API with a browser dashboard.

## What This Project Does

The agent runs a four-layer pipeline:

1. **Data ingestion** — generate baseline and current telemetry windows for `auth`, `payments`, and `orders` services.
2. **Anomaly detection** — two-stage detector: Z-score (statistical) + Isolation Forest (ML).
3. **Decision and action** — policy engine assigns `AUTO`, `CONFIRM`, or `ESCALATE` and executes action stubs.
4. **Notifications and persistence** — push alerts to your phone via ntfy.sh; every event written to SQLite; optional LLM explanation via Claude API.

All remediation methods are safe stubs — no real infrastructure calls are made.

## Architecture

```
data_ingestion/simulator.py     →  synthetic telemetry (CSV)
anomaly_detection/detector.py   →  z-score + IsolationForest scores
policy_engine/policy.py         →  AUTO / CONFIRM / ESCALATE routing
actions/remediation.py          →  action stubs (restart, scale, ticket)
notifications/notifier.py       →  ntfy.sh push alerts (phone)
storage/db.py                   →  SQLite persistence (stdlib sqlite3)
llm/claude_reasoner.py          →  Claude API SRE explanation (optional)
api/server.py                   →  FastAPI REST backend
ui/dashboard.html               →  vanilla JS live dashboard
main.py                         →  orchestrator
```

See `ARCHITECTURE.md` for the full ASCII diagram.

## Repository Layout

```text
aiops-agent/
├── actions/
├── anomaly_detection/
├── api/
│   └── server.py
├── data/
│   ├── current/
│   └── reference/
├── data_ingestion/
├── drift_monitor/          # KS-test module (kept for completeness, not used in main pipeline)
├── llm/
│   └── claude_reasoner.py
├── notifications/
│   └── notifier.py
├── policy_engine/
├── reports/                # generated at runtime
├── storage/
│   └── db.py
├── ui/
│   └── dashboard.html
├── .env.example
├── ARCHITECTURE.md
├── main.py
├── README.md
└── requirements.txt
```

## Requirements

- Python 3.10+
- pip

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create environment config
cp .env.example .env
# Edit .env with your values (see Key Environment Variables below)
```

## Run Commands

### Option A — Full stack (recommended)

```bash
# Terminal 1: start the FastAPI backend
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: run the agent (generates data, detects anomalies, sends notifications)
python main.py

# Terminal 3: serve the dashboard
python -m http.server 5500
# Open: http://localhost:5500/ui/dashboard.html
```

The dashboard auto-detects the API backend on load and auto-refreshes every 30 seconds.

### Option B — Single run without API

```bash
python main.py
python -m http.server 5500
# Open: http://localhost:5500/ui/dashboard.html
```

Dashboard falls back to reading `reports/timeline.json` directly.

### Continuous loop mode

```bash
python main.py --loop
# Runs repeatedly every AGENT_LOOP_INTERVAL_SECONDS (default: 60)
```

## Mobile Push Notifications (ntfy.sh)

Get alerts on your phone whenever an anomaly is detected:

1. Install the **ntfy** app
2. Subscribe to a topic of your choice (e.g. `aiops-alerts-yourname`).
3. Set `NTFY_TOPIC=aiops-alerts-yourname` in `.env`.
4. Run `python main.py` — notifications arrive within 1–2 seconds.

Notification priority maps to decision tier: `ESCALATE` = urgent · `CONFIRM` = high · `AUTO` = default.
Set `NTFY_TOPIC=` (blank) to disable notifications entirely.

## Dashboard Features

- **Summary bar** — total anomalies, decision counts, executed ratio.
- **Incident table** — color-coded `AUTO` / `CONFIRM` / `ESCALATE` badges, executed status.
- **Incident Detail Diagram** — animated SVG pipeline showing where the incident was routed.
- **Plain-English explainer** — "What happened / Why / What was done / What to do next."
- **AI Explanation card** — Claude-generated SRE insight (shown when `ANTHROPIC_API_KEY` is set).
- **Recommended Actions** — priority/category/effort cards for each decision tier.
- **Confirm Action panel** — for `CONFIRM` incidents: approve or escalate with one click; table and summary update immediately.
- **Auto-refresh** — fetches new events every 30 seconds when the API backend is running.

## Timeline JSON Schema

`reports/timeline.json` — one entry per processed event:

| Field | Type | Description |
|---|---|---|
| `timestamp` | string | ISO-8601 UTC |
| `service` | string | `auth`, `payments`, or `orders` |
| `anomaly_score` | float | 0–1, higher = more anomalous |
| `z_score` | float | standard deviations from baseline mean |
| `z_anomaly` | bool | true if z-score exceeded threshold |
| `decision` | string | `AUTO`, `CONFIRM`, or `ESCALATE` |
| `action` | string | action stub name |
| `executed` | bool | whether the action ran |
| `llm_explanation` | string | Claude SRE summary (empty if no API key) |
| `run_id` | string | UUID identifying the agent run |

## Key Environment Variables

```ini
# Anomaly detection
ANOMALY_HIGH_THRESHOLD=0.75
ANOMALY_LOW_THRESHOLD=0.40
Z_SCORE_THRESHOLD=3.0

# Simulation
SIM_REFERENCE_SAMPLES=500
SIM_CURRENT_SAMPLES=100
SIM_RANDOM_SEED=42
SIM_INJECT_ANOMALY=true

# Actions
ENABLE_AUTO_ACTIONS=false
HUMAN_APPROVAL_REQUIRED=true

# Mobile notifications (ntfy.sh)
NTFY_TOPIC=                     # leave blank to disable
NTFY_URL=https://ntfy.sh
NOTIFY_MIN_SCORE=0.40
NOTIFY_DECISIONS=AUTO,CONFIRM,ESCALATE
ALERT_COOLDOWN_MINUTES=5        # set 0 to fire every alert (testing)

# Continuous loop
AGENT_LOOP_INTERVAL_SECONDS=60

# LLM reasoning (optional)
ANTHROPIC_API_KEY=              # leave blank to skip LLM explanation
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

## Notes

- Action methods are safe stubs — no real infrastructure is touched.
- In non-interactive runs, `CONFIRM` incidents auto-escalate to ticket creation.
- The `drift_monitor` module uses scipy KS tests (Evidently was incompatible with Python 3.14).
- SQLite DB is written to `reports/aiops.db`; each run appends rows with a unique `run_id`.
