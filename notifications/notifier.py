"""
File: notifications/notifier.py
Purpose: Send mobile push notifications via ntfy.sh when anomalies are detected.
Layer: Cross-cutting notification concern, called from the orchestration loop in main.py.
"""

from __future__ import annotations

import os
from typing import Any

import requests

NTFY_BASE_URL = "https://ntfy.sh"

_PRIORITY_MAP = {
    "ESCALATE": "5",
    "CONFIRM": "4",
    "AUTO": "3",
}

_TAG_MAP = {
    "ESCALATE": "rotating_light",
    "CONFIRM": "warning",
    "AUTO": "white_check_mark",
}


def send_anomaly_alert(
    service: str,
    anomaly_score: float,
    decision: str,
    action: str,
    details: dict[str, Any] | None = None,
) -> bool:
    """POST a push notification to ntfy.sh when an anomaly is detected.

    Returns True on HTTP 200, False on any failure.
    Silently skipped if NTFY_TOPIC env var is not set (opt-in — no topic = no noise).
    Never raises so a network failure cannot crash the agent.
    """
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        return False

    base_url = os.getenv("NTFY_URL", NTFY_BASE_URL).rstrip("/")
    url = f"{base_url}/{topic}"

    title = f"[{decision}] Anomaly on {service}"
    body_lines = [
        f"Score:  {anomaly_score:.3f}",
        f"Action: {action}",
    ]
    if details:
        for key in ("cpu_util", "memory_util", "request_latency_ms", "error_rate"):
            val = details.get(key)
            if val is not None:
                body_lines.append(f"{key}: {float(val):.3f}")

    priority = _PRIORITY_MAP.get(decision, "3")
    tags = _TAG_MAP.get(decision, "bell")

    try:
        resp = requests.post(
            url,
            data="\n".join(body_lines).encode("utf-8"),
            headers={
                "Title": title,
                "Priority": priority,
                "Tags": tags,
            },
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        # Intent: a notification failure must never crash the agent — alerting is best-effort.
        return False
