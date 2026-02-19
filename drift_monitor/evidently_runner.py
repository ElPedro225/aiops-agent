"""Run Evidently drift and quality reports and extract key signals."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

METRIC_COLUMNS = ["cpu_util", "request_latency_ms", "error_rate", "memory_util"]


def _iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_dicts(item)


def _first_float(report_dict: dict[str, Any], keys: list[str], default: float = 0.0) -> float:
    for container in _iter_dicts(report_dict):
        for key in keys:
            value = container.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return default


def _extract_drifted_columns(report_dict: dict[str, Any]) -> list[str]:
    drifted: set[str] = set()
    for container in _iter_dicts(report_dict):
        drift_by_columns = container.get("drift_by_columns")
        if isinstance(drift_by_columns, dict):
            for column, details in drift_by_columns.items():
                if isinstance(details, dict):
                    if any(
                        bool(details.get(flag))
                        for flag in ("drift_detected", "column_drift", "drifted")
                    ):
                        drifted.add(str(column))

        raw_list = container.get("drifted_columns")
        if isinstance(raw_list, list):
            drifted.update(str(item) for item in raw_list)
        elif isinstance(raw_list, dict):
            for column, details in raw_list.items():
                if isinstance(details, dict):
                    if any(
                        bool(details.get(flag))
                        for flag in ("drift_detected", "column_drift", "drifted")
                    ):
                        drifted.add(str(column))
                elif bool(details):
                    drifted.add(str(column))
    return sorted(drifted)


def _parse_v2_metrics(report_dict: dict[str, Any], current_columns: list[str]) -> dict[str, Any] | None:
    metrics = report_dict.get("metrics")
    if not isinstance(metrics, list):
        return None

    drift_share: float | None = None
    drifted_columns: set[str] = set()
    share_missing: float | None = None
    share_constant: float | None = None
    total_columns: float | None = None
    constant_columns: float | None = None

    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        metric_name = str(metric.get("metric_name", ""))
        config = metric.get("config", {})
        if not isinstance(config, dict):
            config = {}
        value = metric.get("value")

        if metric_name == "DriftedColumnsCount()":
            if isinstance(value, dict):
                drift_share = float(value.get("share", 0.0))
            elif isinstance(value, (int, float)):
                drift_share = float(value)
            continue

        if metric_name.startswith("ValueDrift("):
            column = config.get("column")
            threshold = config.get("threshold")
            method = str(config.get("method", "")).lower()
            if (
                isinstance(column, str)
                and column in current_columns
                and isinstance(value, (int, float))
                and isinstance(threshold, (int, float))
            ):
                if "p_value" in method or "p-value" in method or "ks" in method:
                    is_drift = float(value) < float(threshold)
                else:
                    is_drift = float(value) > float(threshold)
                if is_drift:
                    drifted_columns.add(column)
            continue

        if metric_name == "DatasetMissingValueCount()" and isinstance(value, dict):
            share_missing = float(value.get("share", 0.0))
            continue

        if metric_name == "ConstantColumnsCount()" and isinstance(value, (int, float)):
            constant_columns = float(value)
            continue

        if metric_name == "ColumnCount()" and isinstance(value, (int, float)):
            total_columns = float(value)
            continue

    if share_constant is None and total_columns and total_columns > 0 and constant_columns is not None:
        share_constant = float(constant_columns / total_columns)

    if drift_share is None and drifted_columns:
        denominator = max(len(current_columns), 1)
        drift_share = float(len(drifted_columns) / denominator)

    if drift_share is None and share_missing is None and share_constant is None and not drifted_columns:
        return None

    return {
        "drift_share": float(drift_share or 0.0),
        "drifted_columns": sorted(drifted_columns),
        "share_missing": float(share_missing or 0.0),
        "share_constant": float(share_constant or 0.0),
    }


def _parse_report(report_dict: dict[str, Any], current_columns: list[str]) -> dict[str, Any]:
    v2_result = _parse_v2_metrics(report_dict, current_columns=current_columns)
    if v2_result is not None:
        return v2_result

    drift_share = _first_float(
        report_dict,
        keys=["share_of_drifted_columns", "share_drifted", "dataset_drift_score"],
        default=0.0,
    )
    drifted_columns = _extract_drifted_columns(report_dict)
    if drifted_columns:
        metric_only = [col for col in drifted_columns if col in current_columns]
        drifted_columns = metric_only or drifted_columns
    if drift_share <= 0.0 and drifted_columns:
        denominator = max(len(current_columns), 1)
        drift_share = float(len(drifted_columns) / denominator)

    share_missing = _first_float(
        report_dict,
        keys=["share_of_missing_values", "current_share_of_missing_values", "share_missing"],
        default=0.0,
    )
    share_constant = _first_float(
        report_dict,
        keys=["share_of_constant_columns", "current_share_of_constant_columns", "share_constant"],
        default=0.0,
    )
    return {
        "drift_share": float(drift_share),
        "drifted_columns": drifted_columns,
        "share_missing": float(share_missing),
        "share_constant": float(share_constant),
    }


def run_evidently(
    ref_df: pd.DataFrame,
    cur_df: pd.DataFrame,
    report_dir: str,
    report_name: str,
) -> dict[str, Any]:
    """Run Evidently report and return extracted drift and quality metrics."""
    if ref_df.empty:
        raise ValueError("ref_df is empty")
    if cur_df.empty:
        raise ValueError("cur_df is empty")

    try:
        # Evidently <=0.4 import path
        from evidently.metric_preset import DataDriftPreset, DataQualityPreset
        from evidently.report import Report
    except ImportError:
        try:
            # Evidently >=0.5 import path
            from evidently import Report
            from evidently.presets import DataDriftPreset
            try:
                from evidently.presets import DataQualityPreset
            except ImportError:
                # Evidently >=0.7 replaced DataQualityPreset with DataSummaryPreset.
                from evidently.presets import DataSummaryPreset as DataQualityPreset
        except ImportError as exc:  # pragma: no cover - environment guardrail
            raise ImportError(
                "evidently is required. Install dependencies with: pip install -r requirements.txt"
            ) from exc

    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{report_name}.html"
    json_path = output_dir / f"{report_name}.json"

    report = Report(metrics=[DataDriftPreset(), DataQualityPreset()])
    snapshot = report.run(reference_data=ref_df, current_data=cur_df)
    report_obj = snapshot if snapshot is not None else report

    if hasattr(report_obj, "save_html"):
        report_obj.save_html(str(html_path))
    elif hasattr(report, "save_html"):
        report.save_html(str(html_path))
    else:  # pragma: no cover - defensive fallback
        html_path.write_text("<html><body><p>Evidently HTML output unavailable.</p></body></html>", encoding="utf-8")

    if hasattr(report_obj, "dict"):
        report_dict = report_obj.dict()
    elif hasattr(report_obj, "dump_dict"):
        report_dict = report_obj.dump_dict()
    elif hasattr(report_obj, "as_dict"):
        report_dict = report_obj.as_dict()
    elif hasattr(report_obj, "json"):
        raw_json = report_obj.json()
        report_dict = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    else:  # pragma: no cover - defensive fallback
        report_dict = {}

    if not isinstance(report_dict, dict):
        report_dict = {"report": report_dict}
    json_path.write_text(json.dumps(report_dict, indent=2, default=str), encoding="utf-8")

    parsed = _parse_report(report_dict, current_columns=list(cur_df.columns))
    parsed["html_path"] = str(html_path)
    parsed["json_path"] = str(json_path)
    return parsed


class DriftMonitor:
    """Backward-compatible wrapper class."""

    def __init__(self, report_dir: str = "reports") -> None:
        self.report_dir = report_dir

    def run(self, reference_df: pd.DataFrame, current_df: pd.DataFrame) -> dict[str, Any]:
        return run_evidently(
            ref_df=reference_df,
            cur_df=current_df,
            report_dir=self.report_dir,
            report_name="drift_report",
        )


def main() -> int:
    """CLI entrypoint for drift report execution."""
    try:
        load_dotenv()
        project_root = Path(__file__).resolve().parents[1]
        reference_path = project_root / "data" / "reference" / "metrics.csv"
        current_path = project_root / "data" / "current" / "metrics.csv"
        report_dir = os.getenv("DRIFT_REPORT_DIR", str(project_root / "reports"))
        report_name = os.getenv("DRIFT_REPORT_NAME", "drift_report")

        if not reference_path.exists() or not current_path.exists():
            print(
                "[evidently] Missing input CSV files. Run `python -m data_ingestion.simulator` first."
            )
            return 1

        reference_df = pd.read_csv(reference_path)
        current_df = pd.read_csv(current_path)
        result = run_evidently(
            ref_df=reference_df,
            cur_df=current_df,
            report_dir=report_dir,
            report_name=report_name,
        )
        print("Evidently drift summary:")
        print(
            "  drift_share={drift_share:.4f} share_missing={share_missing:.4f} share_constant={share_constant:.4f}".format(
                **result
            )
        )
        print(f"  drifted_columns={result['drifted_columns']}")
        print(f"  html={result['html_path']}")
        print(f"  json={result['json_path']}")
        return 0
    except FileNotFoundError as exc:
        print(f"[evidently] File error: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - CLI guardrail
        print(f"[evidently] Failed to generate report: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
