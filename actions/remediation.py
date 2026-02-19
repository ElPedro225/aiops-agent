"""
File: actions/remediation.py
Purpose: Route remediation requests through safe stubs with optional human approval gates.
Layer: Action Execution layer in the AIOps architecture.
Attribution: AI-assisted development was used (Claude + ChatGPT Codex).
"""

from __future__ import annotations

import os
import sys
from typing import Any


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def restart_service(service_name: str) -> str:
    """Stub service restart action."""
    # TODO(phase-7): Replace stub with Kubernetes restart call — required for actual service remediation.
    result = f"[ACTION] restart_service service={service_name}"
    print(result)
    return result


def scale_up_service(service_name: str, factor: int = 1) -> str:
    """Stub service scale-up action."""
    # TODO(phase-7): Replace stub with autoscaling API integration — required to increase real runtime capacity.
    factor = max(int(factor), 1)
    result = f"[ACTION] scale_up_service service={service_name} factor={factor}"
    print(result)
    return result


def run_runbook(action_id: str, params: dict[str, Any]) -> str:
    """Stub runbook execution action."""
    # TODO(phase-7): Integrate with runbook automation platform — required for consistent operational playbooks.
    result = f"[ACTION] run_runbook action_id={action_id} params={params}"
    print(result)
    return result


def open_ticket(summary: str, evidence: dict[str, Any]) -> str:
    """Stub incident ticket creation action."""
    # TODO(phase-7): Integrate with PagerDuty or Jira APIs — required for real incident assignment and tracking.
    evidence_keys = sorted(list(evidence.keys()))
    result = f"[ACTION] open_ticket summary={summary} evidence_keys={evidence_keys}"
    print(result)
    return result


def prompt_user_for_confirmation(prompt: str) -> bool:
    """Ask the operator for y/n confirmation via CLI."""
    # WARNING: input() blocks execution, so callers must guard this path in automated environments.
    while True:
        try:
            response = input(f"{prompt} [y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("Confirmation unavailable. Defaulting to 'no'.")
            return False

        if response in {"y", "yes"}:
            return True
        if response in {"n", "no"}:
            return False
        print("Please respond with 'y' or 'n'.")


def _dispatch_action(action: str, service_name: str, details: dict[str, Any]) -> str:
    # Intent: dispatcher follows single-responsibility by routing execution, not deciding policy.
    if action == "restart_service":
        return restart_service(service_name)
    if action == "scale_up_service":
        factor = int(details.get("factor", 1))
        return scale_up_service(service_name, factor=factor)
    if action == "run_runbook":
        action_id = str(details.get("action_id", "generic-runbook"))
        params = details.get("params", {})
        if not isinstance(params, dict):
            params = {"value": params}
        return run_runbook(action_id=action_id, params=params)
    if action == "open_ticket":
        summary = str(details.get("summary", f"Ticket for service {service_name}"))
        evidence = details.get("evidence", details)
        if not isinstance(evidence, dict):
            evidence = {"evidence": evidence}
        return open_ticket(summary=summary, evidence=evidence)
    raise ValueError(f"Unknown action: {action}")


def execute_action(
    action: str,
    service_name: str,
    details: dict[str, Any] | None,
    auto_allowed: bool,
    human_required: bool,
) -> dict[str, Any]:
    """Execute action based on environment and approval constraints."""
    detail_data = details or {}
    env_auto = _parse_bool(os.getenv("ENABLE_AUTO_ACTIONS"), default=False)
    env_human_required = _parse_bool(os.getenv("HUMAN_APPROVAL_REQUIRED"), default=True)
    effective_auto = bool(env_auto and auto_allowed)
    effective_human_required = bool(env_human_required or human_required)
    needs_confirmation = (not effective_auto) or effective_human_required

    # Intent: non-interactive detection prevents CI/CD or daemon runs from hanging on stdin.
    interactive = bool(
        sys.stdin is not None
        and sys.stdout is not None
        and sys.stderr is not None
        and sys.stdin.isatty()
        and sys.stdout.isatty()
        and sys.stderr.isatty()
    )

    if needs_confirmation:
        if interactive:
            prompt = (
                f"Execute action={action} for service={service_name} "
                f"with details={detail_data}?"
            )
            approved = prompt_user_for_confirmation(prompt)
            if not approved:
                return {
                    "executed": False,
                    "result": "[ACTION] action not approved by operator",
                    "action": action,
                }
        else:
            # Intent: when no human can answer prompts, we fail safe by escalation instead of silent execution.
            ticket_result = open_ticket(
                summary=f"Non-interactive escalation for action {action}",
                evidence={"service_name": service_name, "details": detail_data},
            )
            return {
                "executed": False,
                "result": f"Escalated without remediation execution: {ticket_result}",
                "action": action,
            }

    try:
        action_result = _dispatch_action(action, service_name, detail_data)
        return {"executed": True, "result": action_result, "action": action}
    except Exception as exc:
        return {
            "executed": False,
            "result": f"[ACTION] execution failed for {action}: {exc}",
            "action": action,
        }
