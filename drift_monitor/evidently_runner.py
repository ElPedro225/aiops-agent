"""
File: drift_monitor/evidently_runner.py
Purpose: Detect feature drift using KS tests and distill signals into policy-friendly metrics.
Layer: Drift Monitor (ML watchdog) layer in the AIOps architecture.
Note: Originally used Evidently, replaced with scipy KS tests due to Evidently incompatibility
      with Python 3.14 (Pydantic v1 crash). Same statistical method, no external dependency issues.
Attribution: AI-assisted development was used (Claude + ChatGPT Codex).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from scipy import stats

METRIC_COLUMNS = ["cpu_util", "request_latency_ms", "error_rate", "memory_util"]

# Intent: p < 0.05 is the standard threshold for rejecting the null hypothesis of identical distributions.
_DRIFT_P_VALUE_THRESHOLD = 0.05


def run_evidently(
    ref_df: pd.DataFrame,
    cur_df: pd.DataFrame,
    report_dir: str,
    report_name: str,
) -> dict[str, Any]:
    """Run KS-test drift detection and return drift/quality metrics.

    Keeps the same signature and return shape as the original Evidently-based version
    so nothing else in the codebase needs to change.
    """
    if ref_df.empty:
        raise ValueError("ref_df is empty")
    if cur_df.empty:
        raise ValueError("cur_df is empty")

    output_dir = Path(report_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report_name}.json"
    html_path = output_dir / f"{report_name}.html"

    columns = [c for c in ref_df.columns if c in cur_df.columns]
    drifted_columns: list[str] = []
    column_results: dict[str, Any] = {}

    for col in columns:
        ref_vals = ref_df[col].dropna().astype(float).values
        cur_vals = cur_df[col].dropna().astype(float).values

        if len(ref_vals) < 2 or len(cur_vals) < 2:
            continue

        # Intent: KS test measures whether reference and current distributions are statistically different.
        ks_stat, p_value = stats.ks_2samp(ref_vals, cur_vals)
        is_drifted = bool(p_value < _DRIFT_P_VALUE_THRESHOLD)
        if is_drifted:
            drifted_columns.append(col)

        column_results[col] = {
            "ks_statistic": round(float(ks_stat), 6),
            "p_value": round(float(p_value), 6),
            "drift_detected": is_drifted,
            "ref_mean": round(float(ref_vals.mean()), 6),
            "cur_mean": round(float(cur_vals.mean()), 6),
        }

    total_columns = max(len(columns), 1)
    drift_share = float(len(drifted_columns) / total_columns)

    # Missing value share computed on current data only.
    total_cells = cur_df[columns].size
    missing_cells = int(cur_df[columns].isna().sum().sum())
    share_missing = float(missing_cells / total_cells) if total_cells > 0 else 0.0

    report_dict: dict[str, Any] = {
        "drift_share": drift_share,
        "drifted_columns": sorted(drifted_columns),
        "share_missing": share_missing,
        "share_constant": 0.0,
        "column_results": column_results,
        "total_columns": total_columns,
        "n_drifted": len(drifted_columns),
    }

    json_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")

    # Write a minimal HTML report so existing html_path references still resolve.
    rows = "".join(
        f"<tr><td>{col}</td><td>{column_results[col]['ks_statistic']:.4f}</td>"
        f"<td>{column_results[col]['p_value']:.4f}</td>"
        f"<td style='color:{'#f87171' if column_results[col]['drift_detected'] else '#4ade80'}'>"
        f"{'YES' if column_results[col]['drift_detected'] else 'no'}</td></tr>"
        for col in columns if col in column_results
    )
    html_path.write_text(
        f"""<!DOCTYPE html><html><head><meta charset='utf-8'>
        <title>Drift Report — {report_name}</title>
        <style>body{{background:#0d1117;color:#e6edf3;font-family:monospace;padding:2rem}}
        table{{border-collapse:collapse;width:100%}}
        th,td{{border:1px solid #30363d;padding:.5rem 1rem;text-align:left}}
        th{{background:#161b22}}</style></head><body>
        <h2>Drift Report: {report_name}</h2>
        <p>drift_share={drift_share:.4f} &nbsp; drifted={sorted(drifted_columns)} &nbsp; share_missing={share_missing:.4f}</p>
        <table><tr><th>Column</th><th>KS Statistic</th><th>p-value</th><th>Drifted?</th></tr>
        {rows}</table></body></html>""",
        encoding="utf-8",
    )

    return {
        "drift_share": drift_share,
        "drifted_columns": sorted(drifted_columns),
        "share_missing": share_missing,
        "share_constant": 0.0,
        "html_path": str(html_path),
        "json_path": str(json_path),
    }


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
            print("[drift] Missing input CSV files. Run `python -m data_ingestion.simulator` first.")
            return 1

        reference_df = pd.read_csv(reference_path)
        current_df = pd.read_csv(current_path)
        result = run_evidently(
            ref_df=reference_df[METRIC_COLUMNS],
            cur_df=current_df[METRIC_COLUMNS],
            report_dir=report_dir,
            report_name=report_name,
        )
        print("Drift summary:")
        print(f"  drift_share={result['drift_share']:.4f}")
        print(f"  drifted_columns={result['drifted_columns']}")
        print(f"  share_missing={result['share_missing']:.4f}")
        print(f"  html={result['html_path']}")
        print(f"  json={result['json_path']}")
        return 0
    except Exception as exc:
        print(f"[drift] Failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
