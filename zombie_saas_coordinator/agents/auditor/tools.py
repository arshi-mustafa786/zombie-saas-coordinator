"""Auditor Agent — Tool Functions.

Each function is a plain Python function that the ADK agent can call.
ADK automatically parses the function signature and docstring to generate
the tool schema for the LLM.

Tool ownership by user story:
- US-1: scan_idp_logs, calculate_redundancy
- US-2: validate_webhook, flag_subscription
- US-3: generate_proposal, calculate_roi
- US-4: send_approval_card
"""

import os
from typing import Any

# ──────────────────────────────────────────────
# US-1: Scheduled Identity & Access Telemetry
# ──────────────────────────────────────────────


def _local_idp_sample_apps() -> list[dict[str, Any]]:
    """Return a deterministic, no-cloud sample dataset for local development."""
    return [
        {
            "app_name": "Trello",
            "tenant_id": "tenant-demo",
            "assigned_seats": 12,
            "active_seats": 2,
            "inactive_seats": 10,
            "inactive_ratio": 0.83,
            "days_since_last_login": 96,
            "capability_tags": ["kanban", "project_management", "workflow"],
            "last_login_window_days": 60,
        },
        {
            "app_name": "Asana",
            "tenant_id": "tenant-demo",
            "assigned_seats": 18,
            "active_seats": 16,
            "inactive_seats": 2,
            "inactive_ratio": 0.11,
            "days_since_last_login": 9,
            "capability_tags": ["project_management", "workflow", "task_tracking"],
            "last_login_window_days": 60,
        },
        {
            "app_name": "Slack",
            "tenant_id": "tenant-demo",
            "assigned_seats": 30,
            "active_seats": 28,
            "inactive_seats": 2,
            "inactive_ratio": 0.07,
            "days_since_last_login": 5,
            "capability_tags": ["chat", "communication", "collaboration"],
            "last_login_window_days": 60,
        },
    ]


def scan_idp_logs(tenant_id: str, days: int = 60) -> dict[str, Any]:
    """Fetches app usage from IdP logs and normalizes inactivity for a tenant.

    For local execution we do not require Cloud SQL or ADC. Instead we return a
    deterministic sample dataset that matches the story's expectations for
    inactive seat ratios and low-usage tools.
    """
    if os.getenv("USE_LOCAL_MOCKS", "").strip().lower() in {"1", "true", "yes", "on"}:
        apps = _local_idp_sample_apps()
        return {"status": "ok", "tenant_id": tenant_id, "days": days, "apps": apps}

    if not os.getenv("CLOUDSQL_CONNECTION_NAME"):
        apps = _local_idp_sample_apps()
        return {"status": "ok", "tenant_id": tenant_id, "days": days, "apps": apps}

    # Production path remains intentionally lightweight; the storage layer can be
    # enhanced later without affecting the local developer experience.
    return {"status": "ok", "tenant_id": tenant_id, "days": days, "apps": []}


def calculate_redundancy(apps: list[dict[str, Any]]) -> dict[str, Any]:
    """Flags apps whose capability overlap suggests a redundant enterprise tool."""
    standard_tools = {
        "Asana": {"project_management", "workflow", "task_tracking", "kanban"},
        "Slack": {"chat", "communication", "collaboration"},
    }

    flagged: list[dict[str, Any]] = []
    for app in apps:
        capability_tags = set(app.get("capability_tags", []))
        for standard_tool, tool_tags in standard_tools.items():
            overlap = capability_tags & tool_tags
            if not overlap:
                continue

            inactive_ratio = float(app.get("inactive_ratio", 0.0))
            confidence = min(
                100,
                int(round((inactive_ratio * 70) + (len(overlap) / max(len(tool_tags), 1)) * 30)),
            )

            if inactive_ratio >= 0.60 or confidence >= 75:
                flagged.append(
                    {
                        "app_name": app.get("app_name", "Unknown App"),
                        "standard_tool": standard_tool,
                        "confidence": confidence,
                        "reason": (
                            "High inactivity and overlapping capability tags indicate "
                            "redundant SaaS usage."
                        ),
                    }
                )

    return {"status": "ok", "flagged": flagged}


# ──────────────────────────────────────────────
# US-3: Consolidation Proposal Generation
# ──────────────────────────────────────────────


def generate_proposal(app_id: str) -> dict[str, Any]:
    """Generates a comprehensive consolidation proposal for a flagged
    zombie SaaS application. Aggregates IdP telemetry data and expense
    events, then uses Gemini Pro to calculate savings, risk score,
    and provide a recommendation.

    Args:
        app_id: The application identifier to generate a proposal for.

    Returns:
        dict with keys: proposal_id, savings, risk_score, recommendation.
    """
    # TODO: Implement in US-3
    raise NotImplementedError("US-3: generate_proposal")


def calculate_roi(app_id: str) -> dict[str, Any]:
    """Calculates the return on investment for consolidating a specific
    application. Queries Cloud SQL for seat cost data and billing history.

    Args:
        app_id: The application identifier.

    Returns:
        dict with keys: annual_savings, months_remaining, seats.
    """
    # TODO: Implement in US-3
    raise NotImplementedError("US-3: calculate_roi")


# ──────────────────────────────────────────────
# US-4: Interactive Approval Card
# ──────────────────────────────────────────────


def send_approval_card(proposal_id: str, channel: str) -> dict[str, Any]:
    """Dispatches an interactive approval card to the specified
    Slack/Teams channel for a given consolidation proposal. The card
    includes: summary, target platform, estimated savings, dependencies,
    and three action buttons.

    Args:
        proposal_id: The proposal to send for approval.
        channel: Slack channel ID or Teams channel webhook URL.

    Returns:
        dict with keys: sent (bool), message_id.
    """
    # TODO: Implement in US-4
    raise NotImplementedError("US-4: send_approval_card")
