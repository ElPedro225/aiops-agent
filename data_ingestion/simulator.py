"""
data_ingestion/simulator.py
============================
Phase 2 — Synthetic Telemetry Generator

Generates realistic metric streams mimicking OpenTelemetry exports.
Produces a REFERENCE window (normal behaviour) and a CURRENT window
(potentially anomalous) as pandas DataFrames.

Metrics simulated:
  - cpu_usage (%)
  - memory_mb (MB)
  - request_latency_ms (ms)
  - error_rate (%)
  - request_count (requests/min)
"""

# TODO (Phase 2): Implement TelemetrySimulator
# 
# class TelemetrySimulator:
#     def __init__(self, seed=42, n_reference=500, n_current=100):
#         ...
#
#     def generate(self) -> tuple[pd.DataFrame, pd.DataFrame]:
#         """Returns (reference_df, current_df)"""
#         ...
#
#     def inject_anomaly(self, df, feature="cpu_usage", spike_factor=3.0):
#         """Inject a synthetic spike into a metric column."""
#         ...
