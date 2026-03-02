"""
File: llm/claude_reasoner.py
Purpose: Use Claude API to generate plain-English explanations for detected anomalies.
Layer: Optional LLM reasoning layer — called from main.py after policy decision.
       Gracefully disabled when ANTHROPIC_API_KEY is not set.
"""

from __future__ import annotations

import os
from typing import Any


def explain_anomaly(
    service: str,
    anomaly_score: float,
    decision: str,
    metrics: dict[str, float],
    drift_share: float,
) -> str:
    """Call the Claude API to explain an anomaly in plain English.

    Returns a 1-2 sentence explanation string.
    Returns "" if ANTHROPIC_API_KEY is not set (graceful degradation).
    Never raises — LLM failure must not interrupt the agent pipeline.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "your_claude_api_key_here":
        return ""

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        metrics_str = ", ".join(
            f"{k}={v:.3f}" for k, v in metrics.items() if v is not None
        )

        prompt = (
            f"You are an SRE reviewing a telemetry anomaly alert. "
            f"Service: {service}. "
            f"Metrics: {metrics_str}. "
            f"Anomaly score: {anomaly_score:.3f} (0=normal, 1=severe). "
            f"Data drift share: {drift_share:.3f}. "
            f"Policy decision: {decision}. "
            f"In exactly 2 sentences: explain what likely caused this anomaly and "
            f"whether the automated {decision} response is appropriate."
        )

        message = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )

        return str(message.content[0].text).strip()

    except Exception as exc:
        # Intent: LLM failure is logged but never propagated — explanations are enrichment, not critical path.
        print(f"[llm] Claude explanation failed: {exc}")
        return ""
