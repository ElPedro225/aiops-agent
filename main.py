"""Main orchestrator for the v0.2+ AIOps agent prototype."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from actions.remediation import execute_action, open_ticket
from anomaly_detection.detector import METRIC_COLUMNS, TwoStageAnomalyDetector
from data_ingestion.simulator import DEFAULT_SERVICES, generate_telemetry
from drift_monitor.evidently_runner import run_evidently
from policy_engine.policy import AUTO, CONFIRM, ESCALATE, decide, load_thresholds, summarize_decision


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _build_paths(project_root: Path) -> dict[str, Path]:
    report_dir_env = os.getenv("DRIFT_REPORT_DIR", "reports")
    report_dir = Path(report_dir_env)
    if not report_dir.is_absolute():
        report_dir = project_root / report_dir

    return {
        "reference": project_root / "data" / "reference" / "metrics.csv",
        "current": project_root / "data" / "current" / "metrics.csv",
        "report_dir": report_dir,
    }


def _ensure_dirs(paths: dict[str, Path]) -> None:
    paths["reference"].parent.mkdir(parents=True, exist_ok=True)
    paths["current"].parent.mkdir(parents=True, exist_ok=True)
    paths["report_dir"].mkdir(parents=True, exist_ok=True)


def _ensure_data(paths: dict[str, Path]) -> None:
    if paths["reference"].exists() and paths["current"].exists():
        return

    services_env = os.getenv("SIM_SERVICES", "")
    services = [svc.strip() for svc in services_env.split(",") if svc.strip()] or DEFAULT_SERVICES
    ref_samples = _env_int("SIM_REFERENCE_SAMPLES", 500)
    cur_samples = _env_int("SIM_CURRENT_SAMPLES", 100)
    seed = _env_int("SIM_RANDOM_SEED", 42)
    inject_anomaly = _parse_bool(os.getenv("SIM_INJECT_ANOMALY"), default=True)

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
        inject_anomaly=inject_anomaly,
    )
    reference_df.to_csv(paths["reference"], index=False)
    current_df.to_csv(paths["current"], index=False)
    print("[main] Generated missing datasets.")


def _load_data(paths: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    reference_df = pd.read_csv(paths["reference"])
    current_df = pd.read_csv(paths["current"])
    if "timestamp" in reference_df.columns:
        reference_df["timestamp"] = pd.to_datetime(reference_df["timestamp"], errors="coerce")
    if "timestamp" in current_df.columns:
        current_df["timestamp"] = pd.to_datetime(current_df["timestamp"], errors="coerce")

    required = ["timestamp", "service", *METRIC_COLUMNS]
    missing_ref = [col for col in required if col not in reference_df.columns]
    missing_cur = [col for col in required if col not in current_df.columns]
    if missing_ref:
        raise ValueError(f"reference dataset is missing columns: {missing_ref}")
    if missing_cur:
        raise ValueError(f"current dataset is missing columns: {missing_cur}")
    return reference_df, current_df


def _choose_action(row: pd.Series) -> tuple[str, dict[str, Any]]:
    details: dict[str, Any] = {}
    if float(row["cpu_util"]) > 0.85 and float(row["memory_util"]) > 0.85:
        details["factor"] = 2
        return "scale_up_service", details
    if (
        float(row["request_latency_ms"]) > 220.0
        and float(row["cpu_util"]) < 0.70
        and float(row["memory_util"]) < 0.75
    ):
        details["action_id"] = "latency-diagnosis-runbook"
        details["params"] = {
            "latency_ms": float(row["request_latency_ms"]),
            "cpu_util": float(row["cpu_util"]),
            "memory_util": float(row["memory_util"]),
        }
        return "run_runbook", details
    return "restart_service", details


def _to_serializable(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, (pd.Int64Dtype, pd.StringDtype)):
        return str(value)
    if pd.isna(value):
        return None
    return value


def run_agent() -> int:
    """Run the end-to-end AIOps workflow."""
    try:
        load_dotenv()
        project_root = Path(__file__).resolve().parent
        paths = _build_paths(project_root)
        _ensure_dirs(paths)
        _ensure_data(paths)
        reference_df, current_df = _load_data(paths)

        detector = TwoStageAnomalyDetector(
            z_threshold=_env_float("Z_SCORE_THRESHOLD", 3.0),
            contamination=_env_float("IFOREST_CONTAMINATION", 0.05),
            n_features=len(METRIC_COLUMNS),
            random_state=_env_int("SIM_RANDOM_SEED", 42),
        )
        detector.fit(reference_df)
        scored_df = detector.score(current_df)
        scored_df["timestamp"] = pd.to_datetime(scored_df["timestamp"], errors="coerce")

        thresholds = load_thresholds()
        drift_interval_minutes = _env_int("DRIFT_CHECK_INTERVAL_MINUTES", 5)
        low_threshold = float(thresholds.get("ANOMALY_LOW_THRESHOLD", 0.40))
        last_drift_check_ts: pd.Timestamp | None = None
        latest_drift = {
            "drift_share": 0.0,
            "drifted_columns": [],
            "share_missing": 0.0,
            "share_constant": 0.0,
            "html_path": "",
            "json_path": "",
        }
        timeline: list[dict[str, Any]] = []

        for idx, row in scored_df.iterrows():
            timestamp = row.get("timestamp")
            row_ts = pd.to_datetime(timestamp, errors="coerce")
            row_metric_values = row[METRIC_COLUMNS].astype(float)
            z_score = float(
                ((row_metric_values - detector.means) / detector.stds).abs().max()  # type: ignore[operator]
            )
            should_check_drift = last_drift_check_ts is None
            if not should_check_drift and pd.notna(row_ts):
                should_check_drift = (
                    row_ts - last_drift_check_ts  # type: ignore[operator]
                    >= pd.Timedelta(minutes=drift_interval_minutes)
                )
            elif not should_check_drift and pd.isna(row_ts):
                should_check_drift = (idx % max(drift_interval_minutes, 1)) == 0

            if should_check_drift:
                report_name = f"drift_report_{idx + 1:04d}"
                try:
                    latest_drift = run_evidently(
                        ref_df=reference_df[METRIC_COLUMNS],
                        cur_df=current_df.iloc[: idx + 1][METRIC_COLUMNS],
                        report_dir=str(paths["report_dir"]),
                        report_name=report_name,
                    )
                except Exception as exc:
                    print(f"[main] Drift check failed at row {idx}: {exc}")
                if pd.notna(row_ts):
                    last_drift_check_ts = row_ts

            anomaly_score = float(row["anomaly_score"])
            drift_share = float(latest_drift.get("drift_share", 0.0))
            share_missing = float(latest_drift.get("share_missing", 0.0))
            decision = decide(
                anomaly_score=anomaly_score,
                drift_share=drift_share,
                share_missing=share_missing,
                thresholds=thresholds,
            )

            service_name = str(row["service"])
            action_name, action_details = _choose_action(row)
            action_details.update(
                {
                    "anomaly_score": anomaly_score,
                    "drift_share": drift_share,
                    "share_missing": share_missing,
                    "row_index": int(idx),
                }
            )

            if decision == AUTO:
                action_outcome = execute_action(
                    action=action_name,
                    service_name=service_name,
                    details=action_details,
                    auto_allowed=True,
                    human_required=False,
                )
            elif decision == CONFIRM:
                action_outcome = execute_action(
                    action=action_name,
                    service_name=service_name,
                    details=action_details,
                    auto_allowed=False,
                    human_required=True,
                )
            else:
                ticket_result = open_ticket(
                    summary=f"Escalation required for service={service_name}",
                    evidence=action_details,
                )
                action_outcome = {
                    "executed": False,
                    "result": ticket_result,
                    "action": "open_ticket",
                }

            decision_text = summarize_decision(
                anomaly_score=anomaly_score,
                drift_share=drift_share,
                share_missing=share_missing,
                decision=decision,
            )
            timeline.append(
                {
                    "index": int(idx),
                    "timestamp": row_ts,
                    "service": service_name,
                    "anomaly_score": anomaly_score,
                    "z_score": z_score,
                    "iforest_score": float(row["iforest_score"]),
                    "z_anomaly": bool(row["z_anomaly"]),
                    "drift_share": drift_share,
                    "share_missing": share_missing,
                    "decision": decision,
                    "action": str(action_outcome.get("action", action_name)),
                    "executed": bool(action_outcome.get("executed", False)),
                    "result": str(action_outcome.get("result", "")),
                    "decision_summary": decision_text,
                    "report_html": str(latest_drift.get("html_path", "")),
                    "report_json": str(latest_drift.get("json_path", "")),
                }
            )

        timeline_df = pd.DataFrame(timeline)
        if timeline_df.empty:
            print("[main] No events processed.")
            return 1

        timeline_json_path = paths["report_dir"] / "timeline.json"
        timeline_json_payload: list[dict[str, Any]] = []
        for event in timeline:
            timeline_json_payload.append(
                {
                    "timestamp": _to_serializable(event.get("timestamp")),
                    "service": str(event.get("service", "")),
                    "anomaly_score": float(event.get("anomaly_score", 0.0)),
                    "z_score": float(event.get("z_score", 0.0)),
                    "decision": str(event.get("decision", "")),
                    "action": str(event.get("action", "")),
                    "executed": bool(event.get("executed", False)),
                    "drift_share": float(event.get("drift_share", 0.0)),
                }
            )
        timeline_json_path.parent.mkdir(parents=True, exist_ok=True)
        timeline_json_path.write_text(
            json.dumps(timeline_json_payload, indent=2, default=str),
            encoding="utf-8",
        )

        decision_counts = timeline_df["decision"].value_counts(dropna=False).to_dict()
        anomaly_count = int((timeline_df["anomaly_score"] >= low_threshold).sum())
        top_anomalies = timeline_df.sort_values("anomaly_score", ascending=False).head(10)

        print("=" * 80)
        print("AIOps Agent Summary")
        print("=" * 80)
        print(
            f"events={len(timeline_df)} anomalies(>=ANOMALY_LOW_THRESHOLD={low_threshold})={anomaly_count}"
        )
        print(f"decision_counts={decision_counts}")
        print(
            "latest_drift: drift_share={drift_share:.4f}, share_missing={share_missing:.4f}, share_constant={share_constant:.4f}".format(
                drift_share=float(latest_drift.get("drift_share", 0.0)),
                share_missing=float(latest_drift.get("share_missing", 0.0)),
                share_constant=float(latest_drift.get("share_constant", 0.0)),
            )
        )
        print(f"drifted_columns={latest_drift.get('drifted_columns', [])}")
        print(f"report_html={latest_drift.get('html_path', '')}")
        print(f"report_json={latest_drift.get('json_path', '')}")
        print(f"timeline_json={timeline_json_path}")

        print("\nTop anomalies:")
        print(
            top_anomalies[
                [
                    "timestamp",
                    "service",
                    "anomaly_score",
                    "iforest_score",
                    "z_anomaly",
                    "drift_share",
                    "decision",
                    "action",
                    "executed",
                ]
            ].to_string(index=False)
        )
        return 0
    except FileNotFoundError as exc:
        print(f"[main] File not found: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - CLI guardrail
        print(f"[main] Agent execution failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(run_agent())
