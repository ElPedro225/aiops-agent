"""Two-stage anomaly detector (z-score + PyOD Isolation Forest)."""

from __future__ import annotations

import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

METRIC_COLUMNS = ["cpu_util", "request_latency_ms", "error_rate", "memory_util"]
_EPSILON = 1e-9


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


class TwoStageAnomalyDetector:
    """Combines statistical and model-based anomaly scoring."""

    def __init__(
        self,
        z_threshold: float = 3.0,
        contamination: float = 0.05,
        n_features: int = 4,
        random_state: int = 42,
    ) -> None:
        try:
            from pyod.models.iforest import IForest
        except ImportError as exc:  # pragma: no cover - environment guardrail
            raise ImportError(
                "pyod is required for TwoStageAnomalyDetector. Install dependencies with: pip install -r requirements.txt"
            ) from exc

        self.z_threshold = z_threshold
        self.contamination = contamination
        self.n_features = n_features
        self.random_state = random_state
        self._iforest_cls = IForest
        self.model = None
        self.means: pd.Series | None = None
        self.stds: pd.Series | None = None

    @staticmethod
    def _validate_columns(df: pd.DataFrame) -> None:
        missing = [col for col in METRIC_COLUMNS if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required metric columns: {missing}")

    def fit(self, reference_df: pd.DataFrame) -> None:
        """Train detector state using reference data."""
        if reference_df.empty:
            raise ValueError("reference_df is empty")
        self._validate_columns(reference_df)

        features = reference_df[METRIC_COLUMNS].astype(float)
        self.means = features.mean(axis=0)
        stds = features.std(axis=0, ddof=0).replace(0.0, _EPSILON).fillna(_EPSILON)
        self.stds = stds

        self.model = self._iforest_cls(
            contamination=self.contamination,
            random_state=self.random_state,
        )
        self.model.fit(features.to_numpy())

    def score(self, current_df: pd.DataFrame) -> pd.DataFrame:
        """Return anomaly scores for current observations."""
        if self.model is None or self.means is None or self.stds is None:
            raise RuntimeError("Detector is not fitted. Call fit(reference_df) first.")
        if current_df.empty:
            return current_df.copy()
        self._validate_columns(current_df)

        features = current_df[METRIC_COLUMNS].astype(float)
        z_scores = ((features - self.means) / self.stds).abs()
        max_z = z_scores.max(axis=1)
        z_anomaly = z_scores.gt(self.z_threshold).any(axis=1)
        normalized_z = (max_z / max(self.z_threshold, _EPSILON)).clip(lower=0.0, upper=1.0)

        raw_iforest = np.asarray(self.model.decision_function(features.to_numpy()), dtype=float)
        if raw_iforest.size == 0:
            iforest_score = np.zeros(len(current_df.index), dtype=float)
        else:
            min_score = float(raw_iforest.min())
            max_score = float(raw_iforest.max())
            if max_score - min_score <= _EPSILON:
                iforest_score = np.zeros_like(raw_iforest, dtype=float)
            else:
                iforest_score = (raw_iforest - min_score) / (max_score - min_score)

        anomaly_score = np.maximum(normalized_z.to_numpy(dtype=float), iforest_score)

        result = current_df.copy()
        result["z_anomaly"] = z_anomaly.astype(bool)
        result["iforest_score"] = iforest_score
        result["anomaly_score"] = anomaly_score
        return result


class AnomalyDetector:
    """Backward-compatible alias for prior phase naming."""

    def __init__(self, z_threshold: float = 3.0, contamination: float = 0.05) -> None:
        self._detector = TwoStageAnomalyDetector(
            z_threshold=z_threshold,
            contamination=contamination,
            n_features=len(METRIC_COLUMNS),
        )

    def fit(self, reference_df: pd.DataFrame) -> None:
        self._detector.fit(reference_df)

    def predict(self, current_df: pd.DataFrame) -> pd.DataFrame:
        return self._detector.score(current_df)

    def score(self, current_df: pd.DataFrame) -> pd.DataFrame:
        return self._detector.score(current_df)

    def save_model(self, path: str = "models/isolation_forest.pkl") -> None:
        if self._detector.model is None:
            raise RuntimeError("No model available to save. Fit the detector first.")

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "z_threshold": self._detector.z_threshold,
            "contamination": self._detector.contamination,
            "n_features": self._detector.n_features,
            "random_state": self._detector.random_state,
            "means": self._detector.means,
            "stds": self._detector.stds,
            "model": self._detector.model,
        }
        with output_path.open("wb") as stream:
            pickle.dump(payload, stream)

    def load_model(self, path: str = "models/isolation_forest.pkl") -> None:
        input_path = Path(path)
        if not input_path.exists():
            raise FileNotFoundError(f"Model path does not exist: {input_path}")

        with input_path.open("rb") as stream:
            payload = pickle.load(stream)

        detector = TwoStageAnomalyDetector(
            z_threshold=float(payload.get("z_threshold", 3.0)),
            contamination=float(payload.get("contamination", 0.05)),
            n_features=int(payload.get("n_features", len(METRIC_COLUMNS))),
            random_state=int(payload.get("random_state", 42)),
        )
        detector.means = payload.get("means")
        detector.stds = payload.get("stds")
        detector.model = payload.get("model")
        self._detector = detector


def main() -> int:
    """CLI smoke mode for fitting and scoring CSV datasets."""
    try:
        load_dotenv()
        project_root = Path(__file__).resolve().parents[1]
        reference_path = project_root / "data" / "reference" / "metrics.csv"
        current_path = project_root / "data" / "current" / "metrics.csv"

        if not reference_path.exists() or not current_path.exists():
            print(
                "[detector] Missing input CSV files. Run `python -m data_ingestion.simulator` first."
            )
            return 1

        reference_df = pd.read_csv(reference_path)
        current_df = pd.read_csv(current_path)

        detector = TwoStageAnomalyDetector(
            z_threshold=_env_float("Z_SCORE_THRESHOLD", 3.0),
            contamination=_env_float("IFOREST_CONTAMINATION", 0.05),
            n_features=len(METRIC_COLUMNS),
            random_state=int(os.getenv("SIM_RANDOM_SEED", "42")),
        )
        detector.fit(reference_df)
        scored = detector.score(current_df)
        top_n = int(os.getenv("DETECTOR_TOP_N", "10"))
        top = scored.sort_values("anomaly_score", ascending=False).head(top_n)

        print(f"Top {len(top)} anomalies by anomaly_score:")
        display_cols = [
            "timestamp",
            "service",
            "cpu_util",
            "request_latency_ms",
            "error_rate",
            "memory_util",
            "z_anomaly",
            "iforest_score",
            "anomaly_score",
        ]
        print(top[display_cols].to_string(index=False))
        return 0
    except FileNotFoundError as exc:
        print(f"[detector] File error: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - CLI guardrail
        print(f"[detector] Failed to score anomalies: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
