# AIOps Agent

A Python prototype that simulates microservice telemetry, detects anomalies, routes incidents through confidence-based policy tiers (`AUTO`, `CONFIRM`, `ESCALATE`), sends real mobile push notifications, and exposes a live REST API with a browser dashboard.
# Link to the video : https://youtu.be/aRi1Jj5Dbv0
# AI tools were used for brainstorming, code review, and documentation assistance; final design, implementation decisions, testing, and explanation are my own


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
# 1. Clone the repository
git clone https://github.com/ElPedro225/aiops-agent.git
cd aiops-agent

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create environment config
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

1. Install the **ntfy** app.
2. Subscribe to a topic of your choice (e.g. `aiops-alerts-yourname`).
3. Set `NTFY_TOPIC=aiops-alerts-yourname` in `.env`.
4. Run `python main.py` — notifications arrive within 1–2 seconds.

Notification priority maps to decision tier: `ESCALATE` = urgent · `CONFIRM` = high · `AUTO` = default.
Set `NTFY_TOPIC=` (blank) to disable notifications entirely.

Notifications are also sent when you **Approve** or **Escalate** an incident from the dashboard confirm panel.

## Dashboard Features

- **Summary bar** — total anomalies, decision counts, executed ratio.
- **Incident table** — color-coded `AUTO` / `CONFIRM` / `ESCALATE` badges, executed status.
- **Incident Detail Diagram** — animated SVG pipeline showing where the incident was routed.
- **Plain-English explainer** — "What happened / Why / What was done / What to do next."
- **AI Explanation card** — Claude-generated SRE insight (shown when `ANTHROPIC_API_KEY` is set).
- **Recommended Actions** — priority/category/effort cards for each decision tier.
- **Confirm Action panel** — for `CONFIRM` incidents: approve or escalate with one click; table and summary update immediately; phone notification sent on both actions.
- **Auto-refresh** — fetches new events every 30 seconds when the API backend is running.

## REST API Endpoints

The FastAPI backend runs on `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check — returns server status and agent state |
| `GET` | `/timeline` | Latest anomaly events from SQLite (param: `limit`) |
| `GET` | `/history` | All historical events paginated (params: `limit`, `offset`) |
| `GET` | `/runs` | Summary of each agent run (run_id, event count, decisions) |
| `GET` | `/drift` | Latest KS-test drift report JSON |
| `POST` | `/confirm` | Called by dashboard buttons — sends phone notification on human approve/escalate |
| `POST` | `/run` | Trigger a full agent run in the background |

## How to Test Each Feature

### 1. Agent + Phone Notifications

```bash
python main.py
```

**Expected terminal output:**
```
[ntfy] #1 sent → auth ESCALATE score=0.123
[ntfy] #2 sent → payments AUTO score=0.891
...
notifications_sent=N
```

**Expected on phone:** notifications grouped by ntfy app — expand the group to see all.
To receive all decision tiers set `NOTIFY_MIN_SCORE=0.0` in `.env`.

---

### 2. API Backend

```bash
# Start the server
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
```

Open in browser:
- `http://localhost:8000/` — health check JSON
- `http://localhost:8000/timeline` — live events JSON
- `http://localhost:8000/docs` — interactive Swagger UI (try each endpoint live)

---

### 3. Dashboard — Live Data + Auto-refresh

```bash
python -m http.server 5500
# Open: http://localhost:5500/ui/dashboard.html
```

**Expected:** log bar shows `API backend detected — using live data.`

Run `python main.py` again — dashboard auto-refreshes within 30 seconds without reloading the page.

---

### 4. Dashboard — Incident Detail

- Click any row in the incident table.
- **Expected:** SVG pipeline diagram animates, explainer panel shows headline / what happened / why / action taken / next steps.

---

### 5. Dashboard — Confirm Action + Phone Notification

- Click a **CONFIRM** (yellow) row.
- **Expected:** "Confirm Action" card appears with Approve and Escalate buttons.
- Click **Approve & Execute**:
  - Row badge changes to AUTO (green).
  - Summary counters update.
  - Phone notification arrives: `[AUTO] human-approved on {service}`.
- Click **Escalate to Human** on another CONFIRM row:
  - Row badge changes to ESCALATE (red).
  - Phone notification arrives: `[ESCALATE] human-escalated on {service}`.

---

### 6. Continuous Loop Mode

```bash
python main.py --loop
```

**Expected:** agent runs, prints `[main] Sleeping 60s before next run...`, then runs again automatically. Phone receives a new batch of notifications each cycle. Stop with `Ctrl+C`.

---

### 7. SQLite Persistence

After running `python main.py` at least twice:

```bash
python -c "
import sqlite3
conn = sqlite3.connect('reports/aiops.db')
rows = conn.execute('SELECT COUNT(*), COUNT(DISTINCT run_id) FROM events').fetchone()
print(f'Total events: {rows[0]}, Distinct runs: {rows[1]}')
conn.close()
"
```

**Expected:** `Total events: N, Distinct runs: 2+` — proves data accumulates across runs rather than overwriting.

---

### 8. API Interactive Test (Swagger)

Open `http://localhost:8000/docs`:

1. Click `POST /run` → **Try it out** → **Execute** — triggers an agent run via HTTP.
2. Click `GET /timeline` → **Try it out** → **Execute** — returns live event JSON.
3. Watch `GET /` → `agent_running` flip to `true` during the run then back to `false`.

---

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
NOTIFY_MIN_SCORE=0.0            # 0.0 = notify on all decisions
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
