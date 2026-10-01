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
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore, logging

from zombie_saas_coordinator.shared.auth.hmac_validator import verify_hmac_sha256
from zombie_saas_coordinator.shared.models.expense import ExpenseEvent, SubscriptionAssessment

# ──────────────────────────────────────────────
# US-1: Scheduled Identity & Access Telemetry
# ──────────────────────────────────────────────


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
    # TODO: Implement in US-1
    raise NotImplementedError("US-1: scan_idp_logs")


def calculate_redundancy(apps: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyzes application capabilities using Gemini Flash to detect
    functional overlap with enterprise-standard tools. Returns a list
    of flagged applications with redundancy confidence scores (0-100).

    Args:
        apps: List of application activity records from scan_idp_logs.

    Returns:
        dict with keys: status, flagged (list of flagged apps with scores).
    """
    # TODO: Implement in US-1
    raise NotImplementedError("US-1: calculate_redundancy")


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


def _get_audit_logger() -> Any:
    """Return the append-only structured logger used for webhook audit events."""
    client = logging.Client(  # type: ignore[no-untyped-call]
        project=os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    return client.logger("expense-webhook-audit")  # type: ignore[no-untyped-call]


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
