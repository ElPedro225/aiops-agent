"""
drift_monitor/evidently_runner.py
===================================
Phase 4 — Evidently AI Drift Monitor

Periodically compares the live feature distribution (current window)
against the training reference window using Evidently's report suite.

Reports generated:
  - DataDriftPreset    → detects distribution shift (KS test, PSI, etc.)
  - DataQualityPreset  → missing values, outliers, type issues

Outputs:
  - reports/drift_report.html   (interactive visual)
  - reports/drift_report.json   (machine-parseable for policy engine)

Key extracted signal:
  - dataset_drift: bool       → did overall drift occur?
  - share_drifted: float      → % of features that drifted
  - drift_score: float        → severity of drift
"""

# TODO (Phase 4): Implement DriftMonitor
#
# from evidently.report import Report
# from evidently.metric_preset import DataDriftPreset, DataQualityPreset
#
# class DriftMonitor:
#     def __init__(self, report_dir="reports/"):
#         ...
#
#     def run(self, reference_df, current_df) -> dict:
#         """Run Evidently report and return parsed drift signal."""
#         ...
#
#     def _parse_drift_signal(self, json_path) -> dict:
#         """Extract key drift metrics from JSON output."""
#         # Returns: { dataset_drift: bool, share_drifted: float, drift_score: float }
#         ...
