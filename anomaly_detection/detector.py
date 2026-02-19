"""
anomaly_detection/detector.py
==============================
Phase 3 — Two-Stage Anomaly Detector

Stage 1: Statistical baseline
  - Rolling mean + standard deviation
  - Z-score thresholding (default: z > 3.0 = anomaly)

Stage 2: ML-based detection
  - Isolation Forest via PyOD
  - Trained on reference window
  - Produces anomaly score 0.0 → 1.0 per observation

Output: DataFrame with added columns:
  - z_score        (per feature)
  - stage1_flag    (bool)
  - anomaly_score  (float, 0→1)
  - is_anomaly     (bool, Stage 2)
"""

# TODO (Phase 3): Implement AnomalyDetector
#
# class AnomalyDetector:
#     def __init__(self, z_threshold=3.0, contamination=0.05):
#         ...
#
#     def fit(self, reference_df: pd.DataFrame):
#         """Train the Isolation Forest on normal baseline data."""
#         ...
#
#     def predict(self, current_df: pd.DataFrame) -> pd.DataFrame:
#         """Score incoming data. Returns df with anomaly_score column."""
#         ...
#
#     def save_model(self, path="models/isolation_forest.pkl"):
#         ...
#
#     def load_model(self, path="models/isolation_forest.pkl"):
#         ...
