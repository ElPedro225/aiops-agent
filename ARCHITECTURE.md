# AIOps Agent Architecture

## 1. Data Ingestion
The ingestion layer generates synthetic microservice telemetry so the rest of the agent can be exercised without a live observability stack. It creates timestamped rows with service name, CPU utilization, latency, error rate, and memory utilization. The simulator can inject controlled anomalies to mimic spikes and drops seen during incidents. It writes both a stable reference window and a current window, which gives the downstream layers a clean baseline-vs-live comparison.

## 2. Anomaly Detection + Drift Monitor
The detector uses a two-stage approach: statistical z-score checks plus an Isolation Forest model score. Z-scores catch direct deviations from the baseline mean and variance, while Isolation Forest captures less obvious multivariate outliers. These signals are combined into a single anomaly score used by policy decisions. In parallel, Evidently reports act as a watchdog over feature behavior by checking drift and data quality indicators, so the system can lower trust when input distributions move.

## 3. Decision / Action Engine
The decision engine maps incident confidence to three tiers: `AUTO`, `CONFIRM`, and `ESCALATE`. `AUTO` is reserved for high anomaly confidence when drift and missingness are within tolerance. `CONFIRM` asks for human approval before remediation when confidence is moderate or safety gates require review. `ESCALATE` creates a human-facing incident path when risk, uncertainty, or trust constraints make automation inappropriate.

## 4. Feedback Loop
Human confirmations, denials, and escalations are operational feedback signals that can be captured for policy tuning. Drift outcomes add another feedback channel that indicates when baseline assumptions are becoming stale. Over time, these signals can drive threshold calibration and retraining schedules for detection models. This closes the loop from detection and action back to model and policy improvement.

```text
                 AIOps Agent (Three-Layer Architecture)

  +--------------------------------------------------------------+
  | Layer 1: Data Ingestion                                      |
  | - Synthetic telemetry generator                              |
  | - Reference window + Current window                          |
  +-------------------------------+------------------------------+
                                  |
                                  v
  +--------------------------------------------------------------+
  | Layer 2: Anomaly Detection + Drift Monitor                   |
  | - Two-stage detector (Z-score + Isolation Forest)            |
  | - Evidently watchdog (drift + data quality signals)          |
  +-------------------------------+------------------------------+
                                  |
                                  v
  +--------------------------------------------------------------+
  | Layer 3: Decision / Action Engine                            |
  | - Policy tiers: AUTO / CONFIRM / ESCALATE                   |
  | - Remediation stubs + human approval + ticket escalation     |
  +-------------------------------+------------------------------+
                                  |
                                  v
                    Feedback loop to thresholds/retraining
```
