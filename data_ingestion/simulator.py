"""
File: data_ingestion/simulator.py
Purpose: Generate synthetic microservice telemetry windows for baseline and live simulation.
Layer: Data Ingestion layer in the AIOps architecture.
Attribution: AI-assisted development was used (Claude + ChatGPT Codex).
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

METRIC_COLUMNS = ["cpu_util", "request_latency_ms", "error_rate", "memory_util"]
DEFAULT_SERVICES = ["auth", "payments", "orders"]
_EPSILON = 1e-9

_BASE_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "auth": {
        "cpu_util": (0.46, 0.07),
        "request_latency_ms": (90.0, 14.0),
        "error_rate": (0.008, 0.003),
        "memory_util": (0.56, 0.08),
    },
    "payments": {
        "cpu_util": (0.63, 0.11),
        "request_latency_ms": (150.0, 30.0),
        "error_rate": (0.018, 0.008),
        "memory_util": (0.71, 0.10),
    },
    "orders": {
        "cpu_util": (0.54, 0.09),
        "request_latency_ms": (120.0, 22.0),
        "error_rate": (0.012, 0.005),
        "memory_util": (0.62, 0.09),
    },
}


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _clip_metrics(df: pd.DataFrame) -> pd.DataFrame:
    # Intent: hard bounds keep synthetic values physically plausible and prevent downstream model instability.
    clipped = df.copy()
    clipped["cpu_util"] = clipped["cpu_util"].clip(0.0, 1.0)
    clipped["memory_util"] = clipped["memory_util"].clip(0.0, 1.0)
    clipped["error_rate"] = clipped["error_rate"].clip(0.0, 1.0)
    clipped["request_latency_ms"] = clipped["request_latency_ms"].clip(lower=1.0)
    return clipped


def _get_profiles(services: list[str], seed: int) -> dict[str, dict[str, tuple[float, float]]]:
    profiles: dict[str, dict[str, tuple[float, float]]] = {}
    for idx, service in enumerate(services):
        if service in _BASE_PROFILES:
            profiles[service] = _BASE_PROFILES[service]
            continue

        # Intent: per-service distributions better mimic production heterogeneity than one global distribution.
        rng = np.random.default_rng(seed + (idx + 1) * 17)
        profiles[service] = {
            "cpu_util": (float(rng.uniform(0.45, 0.65)), float(rng.uniform(0.05, 0.12))),
            "request_latency_ms": (
                float(rng.uniform(80.0, 180.0)),
                float(rng.uniform(10.0, 35.0)),
            ),
            "error_rate": (float(rng.uniform(0.005, 0.02)), float(rng.uniform(0.002, 0.01))),
            "memory_util": (float(rng.uniform(0.50, 0.75)), float(rng.uniform(0.06, 0.12))),
        }
    return profiles


def _inject_anomalies(
    df: pd.DataFrame,
    rng: np.random.Generator,
    profiles: dict[str, dict[str, tuple[float, float]]],
    metric_names: list[str] | None = None,
    sigma_min: float = 3.0,
    sigma_max: float = 5.0,
) -> pd.DataFrame:
    if df.empty:
        return df

    metric_candidates = metric_names or METRIC_COLUMNS
    metric_candidates = [metric for metric in metric_candidates if metric in METRIC_COLUMNS]
    if not metric_candidates:
        return df

    out = df.copy()
    row_count = len(out.index)
    # Informative: 5% provides a realistic signal density for demos without overwhelming normal behavior.
    anomaly_count = max(1, int(row_count * 0.05))
    target_idx = rng.choice(row_count, size=anomaly_count, replace=False)

    for idx in target_idx:
        service_name = str(out.at[idx, "service"])
        profile = profiles.get(service_name, _BASE_PROFILES.get("orders", {}))
        metric_count = int(rng.integers(1, min(3, len(metric_candidates)) + 1))
        picked = rng.choice(metric_candidates, size=metric_count, replace=False)
        for metric in picked:
            _, metric_std = profile.get(metric, (0.0, 0.05))
            std = max(float(metric_std), _EPSILON)
            # Informative: 3-5 sigma perturbations create statistically rare events that are still plausible.
            bump = float(rng.uniform(sigma_min, sigma_max) * std)
            if metric in {"request_latency_ms", "error_rate"}:
                # Intent: latency and errors are usually the first user-visible blast radius during incidents.
                bump *= float(rng.uniform(1.2, 1.8))
            direction = float(rng.choice([-1.0, 1.0]))
            out.at[idx, metric] = float(out.at[idx, metric]) + direction * bump

    return _clip_metrics(out)


def generate_telemetry(
    num_samples: int,
    services: list[str] | None = None,
    seed: int = 42,
    inject_anomaly: bool = False,
) -> pd.DataFrame:
    """Generate synthetic microservice telemetry."""
    if num_samples <= 0:
        return pd.DataFrame(columns=["timestamp", "service", *METRIC_COLUMNS])

    chosen_services = services or DEFAULT_SERVICES
    if not chosen_services:
        raise ValueError("services must contain at least one service name")

    # WARNING: keep seed fixed in demos to preserve reproducible detector and policy behavior across runs.
    rng = np.random.default_rng(seed)
    profiles = _get_profiles(chosen_services, seed=seed)
    end_time = pd.Timestamp.utcnow().floor("min")
    timestamps = pd.date_range(end=end_time, periods=num_samples, freq="min")
    service_series = rng.choice(chosen_services, size=num_samples, replace=True)

    cpu = np.zeros(num_samples, dtype=float)
    latency = np.zeros(num_samples, dtype=float)
    err = np.zeros(num_samples, dtype=float)
    memory = np.zeros(num_samples, dtype=float)

    for service_name in chosen_services:
        mask = service_series == service_name
        service_samples = int(mask.sum())
        if service_samples == 0:
            continue
        # Intent: sampling from service-specific profile preserves distinct performance signatures per service.
        profile = profiles[service_name]
        cpu_mean, cpu_std = profile["cpu_util"]
        lat_mean, lat_std = profile["request_latency_ms"]
        err_mean, err_std = profile["error_rate"]
        mem_mean, mem_std = profile["memory_util"]
        cpu[mask] = rng.normal(cpu_mean, cpu_std, service_samples)
        latency[mask] = rng.normal(lat_mean, lat_std, service_samples)
        err[mask] = rng.normal(err_mean, err_std, service_samples)
        memory[mask] = rng.normal(mem_mean, mem_std, service_samples)

    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "service": service_series,
            "cpu_util": cpu,
            "request_latency_ms": latency,
            "error_rate": err,
            "memory_util": memory,
        }
    )
    frame = _clip_metrics(frame)
    if inject_anomaly:
        frame = _inject_anomalies(frame, rng=rng, profiles=profiles)
    return frame


class TelemetrySimulator:
    """Backward-compatible simulator wrapper."""

    def __init__(
        self,
        seed: int = 42,
        n_reference: int = 500,
        n_current: int = 100,
        services: list[str] | None = None,
        inject_anomaly: bool = True,
    ) -> None:
        self.seed = seed
        self.n_reference = n_reference
        self.n_current = n_current
        self.services = services or DEFAULT_SERVICES
        self.inject_anomaly_enabled = inject_anomaly

    def generate(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (reference_df, current_df)."""
        reference_df = generate_telemetry(
            num_samples=self.n_reference,
            services=self.services,
            seed=self.seed,
            inject_anomaly=False,
        )
        current_df = generate_telemetry(
            num_samples=self.n_current,
            services=self.services,
            seed=self.seed + 1,
            inject_anomaly=self.inject_anomaly_enabled,
        )
        return reference_df, current_df

    def inject_anomaly(
        self,
        df: pd.DataFrame,
        feature: str = "cpu_util",
        spike_factor: float = 3.0,
    ) -> pd.DataFrame:
        """Inject anomaly spikes into a dataframe and return a copy."""
        # TODO(phase-7): Replace single-metric spike injection with scenario templates — required for production-grade incident realism.
        metric_aliases = {"cpu_usage": "cpu_util", "memory_mb": "memory_util"}
        metric_name = metric_aliases.get(feature, feature)
        profiles = _get_profiles(self.services, self.seed)
        rng = np.random.default_rng(self.seed + 99)
        return _inject_anomalies(
            df,
            rng=rng,
            profiles=profiles,
            metric_names=[metric_name],
            sigma_min=max(spike_factor, 1.0),
            sigma_max=max(spike_factor + 2.0, spike_factor),
        )


def _write_csv(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _summary_row(label: str, df: pd.DataFrame, path: Path) -> str:
    services = ",".join(sorted(df["service"].dropna().unique().tolist()))
    return f"{label}: rows={len(df)} services=[{services}] path={path.as_posix()}"


def main() -> int:
    """CLI entrypoint for dataset generation."""
    try:
        load_dotenv()
        project_root = Path(__file__).resolve().parents[1]
        reference_path = project_root / "data" / "reference" / "metrics.csv"
        current_path = project_root / "data" / "current" / "metrics.csv"

        # Intent: environment-driven generation keeps demo scenarios switchable without editing source code.
        services_env = os.getenv("SIM_SERVICES", "")
        services = [svc.strip() for svc in services_env.split(",") if svc.strip()] or DEFAULT_SERVICES
        ref_samples = _env_int("SIM_REFERENCE_SAMPLES", 500)
        cur_samples = _env_int("SIM_CURRENT_SAMPLES", 100)
        seed = _env_int("SIM_RANDOM_SEED", 42)
        inject_current = _parse_bool(os.getenv("SIM_INJECT_ANOMALY"), default=True)

        reference_df = generate_telemetry(
            num_samples=ref_samples,
            services=services,
            seed=seed,
            inject_anomaly=False,
        )
        current_df = generate_telemetry(
            num_samples=cur_samples,
            services=services,
            seed=seed + 1,
            inject_anomaly=inject_current,
        )
        _write_csv(reference_df, reference_path)
        _write_csv(current_df, current_path)

        print("Generated synthetic telemetry datasets:")
        print(f"  inject_anomaly_current={inject_current} seed={seed}")
        print(f"  {_summary_row('reference', reference_df, reference_path)}")
        print(f"  {_summary_row('current', current_df, current_path)}")
        return 0
    except Exception as exc:  # pragma: no cover - CLI guardrail
        print(f"[simulator] Failed to generate telemetry: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
