# AIOps Agent (Prototype)

A Python prototype that simulates service telemetry, detects anomalies, monitors data drift, and routes incidents through confidence-based actions (`AUTO`, `CONFIRM`, `ESCALATE`).

## What This Project Does

The agent runs a three-layer flow:

1. Data ingestion: generate baseline and current telemetry windows.
2. Detection and watchdog: compute anomaly scores and run drift/quality checks.
3. Decision and action: apply policy tiers (`AUTO`, `CONFIRM`, `ESCALATE`) and execute action stubs.

Outputs include machine-readable artifacts for demos and debugging:

- `data/reference/metrics.csv`
- `data/current/metrics.csv`
- `reports/drift_report*.html`
- `reports/drift_report*.json`
- `reports/timeline.json`

This project is intentionally safe for demos: remediation methods are stubs and do not call real infrastructure APIs.

## Architecture

See `ARCHITECTURE.md` for the plain-language architecture and ASCII diagram.

Core modules:

- `data_ingestion/simulator.py`: synthetic telemetry generation.
- `anomaly_detection/detector.py`: two-stage anomaly detector (`z-score` + `IForest`).
- `drift_monitor/evidently_runner.py`: Evidently runner + drift metric extraction.
- `policy_engine/policy.py`: decision thresholds and policy routing.
- `actions/remediation.py`: action stubs, human confirmation, escalation behavior.
- `main.py`: orchestrator and incident timeline writer.

## Repository Layout

```text
aiops-agent/
|-- actions/
|-- anomaly_detection/
|-- data/
|   |-- current/
|   `-- reference/
|-- data_ingestion/
|-- drift_monitor/
|-- policy_engine/
|-- reports/
|-- ui/
|   `-- dashboard.html
|-- .env.example
|-- .env.demo
|-- ARCHITECTURE.md
|-- main.py
|-- README.md
`-- requirements.txt
```

## Requirements

- Python 3.10+
- pip

## Setup

1. Create and activate a virtual environment.

```bash
python -m venv venv
venv\Scripts\activate
```

2. Install dependencies.

```bash
python -m pip install -r requirements.txt
```

3. Create environment config.

```bash
cp .env.example .env
```

Optional demo presets:

```bash
cp .env.demo .env
```

Then keep one scenario block active in `.env`.

## Run Commands

Run these in order from repo root:

```bash
python -m data_ingestion.simulator
python -m anomaly_detection.detector
python -m drift_monitor.evidently_runner
python main.py
```

What you should see:

- Simulator prints dataset paths and row counts.
- Detector prints top anomalies sorted by `anomaly_score`.
- Drift runner prints `drift_share`, `drifted_columns`, and `share_missing`.
- Main prints an end-of-run summary and path to `reports/timeline.json`.

## Dashboard (Vanilla HTML)

The dashboard is a single file at `ui/dashboard.html` and fetches:

- `../reports/timeline.json`
- `../reports/drift_report.json`

Run a local static server from repo root:

```bash
python -m http.server
```

Open:

```text
http://localhost:8000/ui/dashboard.html
```

Dashboard includes:

- Summary bar (total anomalies and decision counts).
- Scrollable incident table with color-coded decision badges.
- Drift status panel (`drift_share`, `drifted_columns`, `share_missing`).
- Incident detail panel (row click) with animated decision-flow SVG.
- Plain-English "What happened?" summary for non-technical users.
- Rule-based "Recommended Actions" cards with priority/category/effort tags.
- "Confirm Action" component for pending `CONFIRM` incidents:
  - `Approve & Execute` sets the incident to executed and updates table + summary counts.
  - `Escalate to Human` converts `CONFIRM -> ESCALATE` and refreshes summary counts.
  - Panel decisions persist in-session by `timestamp|service` key while the page remains open.

## End-to-End Demo Flow

1. Generate data (`simulator`) and run `main.py` to create `reports/timeline.json`.
2. Start `python -m http.server` from repo root.
3. Open `http://localhost:8000/ui/dashboard.html`.
4. Click an incident row to inspect diagram, summary, and recommendations.
5. For pending `CONFIRM` incidents, use the confirmation card to approve or escalate.
6. Observe immediate UI updates to row state and summary counters.

## Timeline JSON Schema

`reports/timeline.json` contains one entry per processed event with:

- `timestamp`
- `service`
- `anomaly_score`
- `z_score`
- `decision` (`AUTO`, `CONFIRM`, `ESCALATE`)
- `action`
- `executed`
- `drift_share`

## Key Environment Variables

- Detection:
  - `Z_SCORE_THRESHOLD`
  - `ANOMALY_HIGH_THRESHOLD`
  - `ANOMALY_LOW_THRESHOLD`
  - `IFOREST_CONTAMINATION` (optional)
- Drift:
  - `DRIFT_TOLERANCE`
  - `DRIFT_CHECK_INTERVAL_MINUTES`
  - `DRIFT_REPORT_DIR`
- Simulation:
  - `SIM_REFERENCE_SAMPLES`
  - `SIM_CURRENT_SAMPLES`
  - `SIM_RANDOM_SEED`
  - `SIM_INJECT_ANOMALY`
- Actions:
  - `ENABLE_AUTO_ACTIONS`
  - `HUMAN_APPROVAL_REQUIRED`

## Notes

- Action methods are safe stubs (no real infrastructure calls).
- In non-interactive runs, `CONFIRM` paths auto-escalate to ticket creation.
- Evidently and numerical libraries may emit warnings in some environments; the pipeline still completes.
