"""Rule-based policy logic for anomaly and drift-aware actions."""

from __future__ import annotations

import os
from typing import Any

AUTO = "AUTO"
CONFIRM = "CONFIRM"
ESCALATE = "ESCALATE"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def load_thresholds() -> dict[str, float]:
    """Load policy thresholds from environment variables."""
    return {
        "ANOMALY_HIGH_THRESHOLD": _env_float("ANOMALY_HIGH_THRESHOLD", 0.75),
        "ANOMALY_LOW_THRESHOLD": _env_float("ANOMALY_LOW_THRESHOLD", 0.40),
        "DRIFT_TOLERANCE": _env_float("DRIFT_TOLERANCE", 0.30),
    }


def decide(
    anomaly_score: float,
    drift_share: float,
    share_missing: float,
    thresholds: dict[str, float] | None = None,
) -> str:
    """Return one of AUTO, CONFIRM, or ESCALATE."""
    cfg = thresholds or load_thresholds()
    high = float(cfg.get("ANOMALY_HIGH_THRESHOLD", 0.75))
    low = float(cfg.get("ANOMALY_LOW_THRESHOLD", 0.40))
    drift_tol = float(cfg.get("DRIFT_TOLERANCE", 0.30))

    if anomaly_score >= high and drift_share < drift_tol and share_missing < 0.05:
        return AUTO
    if anomaly_score >= low:
        return CONFIRM
    return ESCALATE


def summarize_decision(
    anomaly_score: float,
    drift_share: float,
    share_missing: float,
    decision: str,
) -> str:
    """Build a concise human-readable decision summary."""
    action_text = {
        AUTO: "execute remediation automatically",
        CONFIRM: "request human confirmation before remediation",
        ESCALATE: "escalate incident for human investigation",
    }.get(decision, "take no action")
    return (
        "Decision={decision} for anomaly_score={anomaly_score:.3f}, drift_share={drift_share:.3f}, "
        "share_missing={share_missing:.3f}; recommended action: {action}."
    ).format(
        decision=decision,
        anomaly_score=anomaly_score,
        drift_share=drift_share,
        share_missing=share_missing,
        action=action_text,
    )


class PolicyEngine:
    """Backward-compatible policy wrapper."""

    HIGH = "autonomous"
    MEDIUM = "suggest"
    LOW = "escalate"

    def __init__(self, thresholds: dict[str, float] | None = None) -> None:
        self.thresholds = thresholds or load_thresholds()

    def decide(self, anomaly_score: float, drift_signal: dict[str, Any]) -> dict[str, Any]:
        drift_share = float(drift_signal.get("drift_share", 0.0))
        share_missing = float(drift_signal.get("share_missing", 0.0))
        tier = decide(
            anomaly_score=anomaly_score,
            drift_share=drift_share,
            share_missing=share_missing,
            thresholds=self.thresholds,
        )
        confidence = {
            AUTO: "high",
            CONFIRM: "medium",
            ESCALATE: "low",
        }[tier]
        recommended_action = {
            AUTO: "restart_service",
            CONFIRM: "restart_service_with_confirmation",
            ESCALATE: "open_ticket",
        }[tier]
        reasoning = summarize_decision(
            anomaly_score=anomaly_score,
            drift_share=drift_share,
            share_missing=share_missing,
            decision=tier,
        )
        return {
            "tier": tier,
            "recommended_action": recommended_action,
            "reasoning": reasoning,
            "confidence": confidence,
        }

    def _llm_reasoning(self, context: dict[str, Any]) -> str:
        """Placeholder hook for future optional LLM integration."""
        _ = context
        return "LLM reasoning is not enabled in v0.2+."
