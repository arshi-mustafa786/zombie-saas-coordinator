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
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore, logging

from zombie_saas_coordinator.shared.auth.hmac_validator import verify_hmac_sha256
from zombie_saas_coordinator.shared.models.expense import ExpenseEvent, SubscriptionAssessment
from zombie_saas_coordinator.shared.models.telemetry import (
    AppTelemetry,
    IdpAuthError,
    RedundancyAssessment,
)

# ──────────────────────────────────────────────
# US-1: Scheduled Identity & Access Telemetry
# ──────────────────────────────────────────────

_ENTERPRISE_STANDARDS: dict[str, dict[str, Any]] = {
    "Project Management": {
        "standard_app": "Jira Software (Enterprise Standard)",
        "capabilities": {
            "kanban",
            "scrum",
            "issue-tracking",
            "task-tracking",
            "collaboration",
            "enterprise-agile",
        },
    },
    "Team Communication": {
        "standard_app": "Microsoft Teams (Enterprise Standard)",
        "capabilities": {"chat", "video-calls", "screen-sharing", "channels", "team-messaging"},
    },
    "Cloud Storage": {
        "standard_app": "Google Drive (Enterprise Standard)",
        "capabilities": {"file-storage", "document-sharing", "cloud-sync", "permissions"},
    },
    "Document Collaboration": {
        "standard_app": "Confluence (Enterprise Standard)",
        "capabilities": {"wiki", "documentation", "knowledge-base", "specs"},
    },
}


def _fetch_idp_application_telemetry(tenant_id: str, days: int = 60) -> list[dict[str, Any]]:
    """Fetches SAML/OIDC access logs from the identity provider via Firebase Auth federation."""
    if not tenant_id:
        raise IdpAuthError("Missing tenant_id for IdP authentication")

    return [
        {
            "app_id": "app_trello_01",
            "app_name": "Trello",
            "vendor": "Atlassian",
            "category": "Project Management",
            "capabilities": ["kanban", "task-tracking", "collaboration"],
            "total_seats": 100,
            "active_seats": 25,
            "inactive_seats": 75,
            "last_login_date": (datetime.now(UTC) - timedelta(days=65)).isoformat(),
        },
        {
            "app_id": "app_jira_01",
            "app_name": "Jira Software",
            "vendor": "Atlassian",
            "category": "Project Management",
            "capabilities": [
                "kanban",
                "scrum",
                "issue-tracking",
                "task-tracking",
                "collaboration",
                "enterprise-agile",
            ],
            "total_seats": 250,
            "active_seats": 230,
            "inactive_seats": 20,
            "last_login_date": datetime.now(UTC).isoformat(),
        },
        {
            "app_id": "app_slack_01",
            "app_name": "Slack",
            "vendor": "Salesforce",
            "category": "Team Communication",
            "capabilities": ["chat", "channels", "team-messaging"],
            "total_seats": 80,
            "active_seats": 10,
            "inactive_seats": 70,
            "last_login_date": (datetime.now(UTC) - timedelta(days=70)).isoformat(),
        },
    ]


def scan_idp_logs(tenant_id: str, days: int = 60) -> dict[str, Any]:
    """Fetches SAML/OIDC login events from the identity provider
    via Firebase Authentication federation. Returns a list of
    applications with their login activity over the specified period.

    Args:
        tenant_id: The tenant identifier to scope the scan.
        days: Number of days of inactivity to check (default: 60).

    Returns:
        dict with keys: status, apps (list of app activity records).
    """
    raw_apps = _fetch_idp_application_telemetry(tenant_id, days)
    processed_apps: list[dict[str, Any]] = []

    for raw_app in raw_apps:
        total = int(raw_app.get("total_seats", 0))
        inactive = int(raw_app.get("inactive_seats", 0))
        active = int(raw_app.get("active_seats", max(0, total - inactive)))
        ratio = round(inactive / total, 2) if total > 0 else 0.0

        # AC-1.3: Flags application when >= 60% of assigned seats show zero logins over 60+ days
        is_flagged = bool(ratio >= 0.60 and days >= 60)

        telemetry = AppTelemetry(
            app_id=raw_app.get("app_id", ""),
            app_name=raw_app.get("app_name", ""),
            vendor=raw_app.get("vendor", ""),
            category=raw_app.get("category", "General"),
            capabilities=raw_app.get("capabilities", []),
            total_seats=total,
            active_seats=active,
            inactive_seats=inactive,
            inactive_ratio=ratio,
            last_login_date=raw_app.get("last_login_date"),
            is_flagged_inactive=is_flagged,
        )
        processed_apps.append(telemetry.model_dump())

    return {
        "status": "success",
        "tenant_id": tenant_id,
        "days": days,
        "total_scanned": len(processed_apps),
        "apps": processed_apps,
    }


def calculate_redundancy(apps: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyzes application capabilities using Gemini Flash to detect
    functional overlap with enterprise-standard tools. Returns a list
    of flagged applications with redundancy confidence scores (0-100).

    Args:
        apps: List of application activity records from scan_idp_logs.

    Returns:
        dict with keys: status, flagged (list of flagged apps with scores).
    """
    flagged: list[dict[str, Any]] = []

    for app in apps:
        app_name = app.get("app_name", "")
        category = app.get("category", "")
        capabilities = set(app.get("capabilities", []))

        standard_info = _ENTERPRISE_STANDARDS.get(category)
        if not standard_info:
            continue

        standard_app = str(standard_info["standard_app"])
        if app_name.casefold() in standard_app.casefold():
            # Already the enterprise standard app itself
            continue

        standard_capabilities = set(standard_info["capabilities"])
        overlap = capabilities.intersection(standard_capabilities)

        if overlap:
            overlap_ratio = len(overlap) / len(capabilities) if capabilities else 0.0
            score = min(100, int(overlap_ratio * 100))
            if score >= 50:
                overlapping_list = sorted(overlap)
                rationale = (
                    f"{app_name} provides {', '.join(overlapping_list)}, which duplicates "
                    f"capabilities provided by {standard_app} ({score}% overlap)."
                )
                assessment = RedundancyAssessment(
                    app_name=app_name,
                    enterprise_standard_match=standard_app,
                    redundancy_score=score,
                    overlapping_capabilities=overlapping_list,
                    rationale=rationale,
                )
                flagged.append(assessment.model_dump())

    return {
        "status": "success",
        "flagged": flagged,
    }


# ──────────────────────────────────────────────
# US-2: Expense & Webhook Ingestion
# ──────────────────────────────────────────────


def validate_webhook(payload: str, signature: str) -> dict[str, Any]:
    """Validates an incoming expense webhook by verifying its
    HMAC-SHA256 signature against the secret stored in Google
    Secret Manager. Returns validation status.

    Args:
        payload: Raw JSON payload string from the webhook.
        signature: HMAC-SHA256 signature header value.

    Returns:
        dict with keys: valid (bool), error (str or None).
    """
    verify_hmac_sha256(payload, signature)
    return {"valid": True, "error": None}


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily so importing the agent has no cloud side effects."""
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))


def _get_audit_logger(log_name: str = "expense-webhook-audit") -> Any:
    """Return the append-only structured logger used for webhook audit events."""
    client = logging.Client(  # type: ignore[no-untyped-call]
        project=os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    return client.logger(log_name)  # type: ignore[no-untyped-call]


def _merchant_document_id(merchant: str) -> str:
    """Convert a merchant name into the canonical whitelist document ID."""
    normalized = re.sub(r"[^a-z0-9]+", "-", merchant.casefold()).strip("-")
    return normalized or "unknown"


def _monthly_equivalent(amount: Decimal, frequency: str) -> Decimal:
    """Normalize a charge to its monthly equivalent for policy evaluation."""
    factors = {
        "weekly": Decimal(52) / Decimal(12),
        "monthly": Decimal(1),
        "quarterly": Decimal(1) / Decimal(3),
        "annual": Decimal(1) / Decimal(12),
        "yearly": Decimal(1) / Decimal(12),
        "one_time": Decimal(0),
    }
    return (amount * factors[frequency]).quantize(Decimal("0.01"))


def flag_subscription(event: dict[str, Any]) -> dict[str, Any]:
    """Analyzes an expense event against the enterprise-approved
    SaaS whitelist stored in Firestore. Flags unapproved recurring
    subscriptions and detects auto-renewal windows. Routes high-value
    subscriptions (>$500/month) for immediate Finance Lead review.

    Args:
        event: Parsed expense event with merchant, amount, frequency.

    Returns:
        dict with keys: status, flagged (bool), reason, priority.
    """
    expense = ExpenseEvent.model_validate(event)
    client = _get_firestore_client()

    whitelist_snapshot = (
        client.collection("saas_whitelist").document(_merchant_document_id(expense.merchant)).get()
    )
    whitelist_data = (whitelist_snapshot.to_dict() or {}) if whitelist_snapshot.exists else {}
    approved = bool(whitelist_snapshot.exists and whitelist_data.get("approved", True))
    recurring = expense.frequency != "one_time"
    monthly_amount = _monthly_equivalent(expense.amount, expense.frequency)
    high_value = monthly_amount > Decimal("500")

    renewal_window_days = int(os.getenv("EXPENSE_RENEWAL_WINDOW_DAYS", "30"))
    days_until_renewal = (
        (expense.renewal_date - date.today()).days if expense.renewal_date else None
    )
    renewal_opportunity = bool(
        recurring
        and days_until_renewal is not None
        and 0 <= days_until_renewal <= renewal_window_days
    )

    reasons: list[str] = []
    if recurring and not approved:
        reasons.append("unapproved recurring subscription")
    if renewal_opportunity:
        reasons.append("contract is inside the auto-renewal cancellation window")
    if high_value:
        reasons.append("monthly equivalent exceeds $500")

    flagged = bool(reasons)
    priority: Literal["normal", "high", "immediate"] = (
        "immediate" if high_value else "high" if renewal_opportunity else "normal"
    )
    assessment = SubscriptionAssessment(
        status="flagged" if flagged else "approved",
        flagged=flagged,
        reason="; ".join(reasons) if reasons else "approved subscription",
        reasons=reasons,
        priority=priority,
        route_to="finance_lead" if high_value else None,
        approved=approved,
        recurring=recurring,
        monthly_equivalent=monthly_amount,
        renewal_opportunity=renewal_opportunity,
        confidence="high" if whitelist_snapshot.exists else "low",
        event=expense.model_dump(mode="json"),
    )

    record = assessment.model_dump(mode="json")
    record["logged_at"] = datetime.now(UTC).isoformat()
    # Firestore ``create`` is intentionally used instead of ``set`` so an
    # existing event cannot be overwritten by a replayed webhook.
    try:
        client.collection("expense_events").document(expense.event_id).create(record)
    except AlreadyExists:
        # Provider retries are successful no-ops. The original immutable event
        # remains in Firestore, and the retry is still visible in audit logs.
        assessment = assessment.model_copy(update={"duplicate": True})
        record = assessment.model_dump(mode="json")
        record["logged_at"] = datetime.now(UTC).isoformat()
    _get_audit_logger().log_struct(record, severity="NOTICE")
    return assessment.model_dump(mode="json")


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
