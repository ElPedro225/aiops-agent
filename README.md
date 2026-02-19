# 🤖 AIOps Agent — Autonomous IT Operations Prototype

> **Solo project by [Juan Naranjo](https://www.juanpnaranjo.com)**  
> Built as part of an AI Challenge exploring AI-driven autonomous cloud operations.  
> Developed with AI pair-programming assistance from **Claude (Anthropic)** and **ChatGPT (OpenAI)** — see [AI Collaboration Notes](#-ai-collaboration-notes) for how each was used.

---

## 📌 What This Is

A working prototype of an **AIOps agent** that autonomously monitors simulated microservice telemetry, detects anomalies using machine learning, watches its own model health with Evidently AI, and makes intelligent remediation decisions — escalating to a human only when confidence is low.

Inspired by [Microsoft AIOpsLab](https://github.com/microsoft/AIOpsLab) and the broader AIOps research landscape.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                  LAYER 1 — DATA INGESTION               │
│  Simulated telemetry (CPU, latency, error rate, memory) │
│  → Python generator → pandas DataFrames / CSV           │
└────────────────────────┬────────────────────────────────┘
                         │ normalised metric stream
┌────────────────────────▼────────────────────────────────┐
│          LAYER 2 — ANOMALY DETECTION + DRIFT WATCHDOG   │
│                                                         │
│  ┌─────────────────────┐   ┌────────────────────────┐   │
│  │  Two-Stage Detector  │   │   Evidently AI Monitor │   │
│  │  1. Z-score baseline │   │   - Data drift report  │   │
│  │  2. Isolation Forest │   │   - Quality checks     │   │
│  │  → anomaly score 0→1 │   │   - Drift signal out   │   │
│  └──────────┬──────────┘   └────────────┬───────────┘   │
└─────────────┼──────────────────────────┼───────────────┘
              │ anomaly score             │ drift confidence
┌─────────────▼──────────────────────────▼───────────────┐
│              LAYER 3 — DECISION / ACTION ENGINE         │
│                                                         │
│  Policy Engine (rule-based + optional LLM reasoning)    │
│  ┌────────────────────────────────────────────────────┐ │
│  │ High confidence + no drift  → autonomous action    │ │
│  │ Medium confidence           → suggest + confirm    │ │
│  │ Low confidence / drift      → escalate to human   │ │
│  └────────────────────────────────────────────────────┘ │
│                                                         │
│  AUTO ACTIONS             │  HUMAN-IN-THE-LOOP          │
│  - Restart service        │  - CLI approval prompt      │
│  - Scale up replica       │  - Incident ticket (stub)   │
│  - Run runbook            │  - Retrain trigger          │
│  - Annotate incident      │                             │
└─────────────────────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │   FEEDBACK LOOP     │
              │  Human labels →     │
              │  threshold update / │
              │  model retrain      │
              └─────────────────────┘
```

---

## 🧠 AI Concepts Used

| Concept | Implementation |
|---|---|
| Anomaly detection | Z-score thresholding + Isolation Forest (PyOD) |
| Data drift detection | Evidently AI — KS test, PSI, 20+ methods |
| Autonomous decision-making | Rule-based policy engine with confidence tiers |
| Human-in-the-loop | CLI approval flow + escalation on low confidence |
| Feedback loop | Human labels feed threshold recalibration |
| Optional LLM reasoning | Chain-of-thought via Claude API (ReAct pattern) |

---

## 📁 Repository Structure

```
aiops-agent/
│
├── data_ingestion/
│   ├── __init__.py
│   └── simulator.py          # Synthetic telemetry generator
│
├── anomaly_detection/
│   ├── __init__.py
│   └── detector.py           # Z-score + Isolation Forest detector
│
├── drift_monitor/
│   ├── __init__.py
│   └── evidently_runner.py   # Evidently drift reports + JSON extraction
│
├── policy_engine/
│   ├── __init__.py
│   └── policy.py             # Rule-based decision logic
│
├── actions/
│   ├── __init__.py
│   └── remediation.py        # Stub auto-actions + human approval CLI
│
├── ui/                       # (Phase 5) Next.js dashboard
│
├── data/
│   ├── reference/            # Baseline training data
│   └── current/              # Live / incoming metric windows
│
├── reports/                  # Evidently HTML + JSON outputs
│
├── main.py                   # Agent entry point / orchestrator
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🚀 Setup Instructions

### Prerequisites
- Python 3.10+
- pip
- (Optional) Docker + Docker Compose

### 1. Clone the repo
```bash
git clone https://github.com/Pedriux0/aiops-agent.git
cd aiops-agent
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env with your settings (LLM API key optional)
```

### 5. Run the agent
```bash
python main.py
```

### Optional — Run with Docker
```bash
docker-compose up --build
```

---

## 📦 Dependencies

```
pandas
numpy
scikit-learn
pyod
evidently
matplotlib
python-dotenv
requests
```

---

## 📈 Development Phases

Each phase is committed as a tagged release on GitHub so you can follow the build progression:

| Phase | Tag | Description | Status |
|---|---|---|---|
| 1 | `v0.1-skeleton` | Repo structure + README | ✅ Done |
| 2 | `v0.2-ingestion` | Telemetry simulator (synthetic metrics) | 🔜 Next |
| 3 | `v0.3-detector` | Z-score + Isolation Forest detector | 🔜 |
| 4 | `v0.4-evidently` | Evidently drift monitor integration | 🔜 |
| 5 | `v0.5-policy` | Policy engine + action stubs | 🔜 |
| 6 | `v0.6-feedback` | Feedback loop + threshold recalibration | 🔜 |
| 7 | `v1.0-demo` | UI dashboard + video demo | 🔜 |

---

## 🤖 AI Collaboration Notes

This project was built using AI pair-programming as a deliberate development strategy — not to generate code blindly, but to accelerate design thinking, explore implementation options, and validate architectural decisions.

### Claude (Anthropic) — used for:
- System architecture design and layer decomposition
- Explaining ML concepts (Isolation Forest, data drift, ReAct agent pattern)
- Reviewing code for correctness and edge cases
- Writing structured documentation and README drafts
- Debugging and explaining error messages

### ChatGPT (OpenAI) — used for:
- Brainstorming alternative implementation approaches
- Generating boilerplate code for modules
- Cross-validating architectural decisions
- Exploring library options (PyOD vs sklearn directly, Evidently vs Whylogs)

> **Philosophy:** AI tools were used like a senior engineer pair — they suggested, explained, and reviewed. All final decisions, integrations, and understanding are the developer's own. Every line of code committed was read, understood, and intentionally chosen.

---

## 🧪 Assumptions

- Telemetry is **simulated** — no real Prometheus/Loki/OTel infrastructure required for the prototype
- Auto-actions (restart, scale) are **stubbed** as Python functions printing mock output
- The LLM reasoning layer is **optional** — the agent works fully with rule-based logic alone
- Evidently runs in **batch mode** (periodic checks), not true real-time streaming

---

## 🔭 Future Improvements

- Connect to a real Prometheus datasource via the HTTP API
- Replace stub auto-actions with actual Kubernetes API calls (`kubectl rollout restart`)
- Add a Next.js dashboard for live decision log visualization
- Implement online learning so the Isolation Forest updates incrementally
- Add multi-service support (currently single-service telemetry stream)
- Integrate PagerDuty or Opsgenie for real alert routing
- Containerize each module as a separate microservice

---

## 📹 Video Demo

> 📎 *Link will be added here once recorded (Phase 7)*

**Demo covers:**
- What was built and why
- AI concepts incorporated
- How the agent makes decisions
- Challenges and lessons learned

---

## 📄 License

MIT — free to use, modify, and learn from.

---

*Built with curiosity, Python, and a lot of AI collaboration. — Juan Naranjo, 2025*
#   a i o p s - a g e n t  
 