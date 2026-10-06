"""Root Orchestrator Agent — Zombie SaaS Coordinator.

This is the top-level agent that delegates work to specialized sub-agents:
- auditor_agent:    Detects zombie SaaS and generates consolidation proposals
- architect_agent:  Validates semantic compatibility between source/target platforms
- integrator_agent: Scans automation hubs for dependency graphs

The root agent implements the HITL (Human-in-the-Loop) execution gate
and coordinates parallel execution of Architect + Integrator after approval.
"""

import contextlib
import os
from datetime import UTC, datetime
from typing import Any

from google.adk.agents import Agent
from google.cloud import firestore, logging

from zombie_saas_coordinator.agents.architect.agent import architect_agent
from zombie_saas_coordinator.agents.auditor.agent import auditor_agent
from zombie_saas_coordinator.agents.integrator.agent import integrator_agent


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily."""
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database=database)


def _get_audit_logger() -> Any:  # noqa: ANN401
    """Structured audit logger for HITL approval gates."""
    client = logging.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))  # type: ignore[no-untyped-call]
    return client.logger("hitl-approval-audit")  # type: ignore[no-untyped-call]


def check_approval_status(
    proposal_id: str,
    required_gate: str = "PERMISSION_TO_MIGRATE",
) -> dict[str, Any]:
    """Checks whether a consolidation proposal has been approved by an authorized human.

    Reads approval status from Cloud SQL and Firestore, enforces 7-day TTL expiration,
    and blocks agent delegation if the proposal is pending, expired, or revoked.
    """
    client = _get_firestore_client()
    approval_doc = client.collection("approvals").document(proposal_id).get()

    if not approval_doc.exists:
        prop_doc = client.collection("consolidation_proposals").document(proposal_id).get()
        if not prop_doc.exists:
            return {
                "approved": False,
                "proposal_id": proposal_id,
                "status": "NOT_FOUND",
                "can_delegate": False,
                "is_expired": False,
                "revoked": False,
                "message": f"Proposal '{proposal_id}' does not exist.",
            }
        prop_data = prop_doc.to_dict() or {}
        if prop_data.get("status") != "approved":
            return {
                "approved": False,
                "proposal_id": proposal_id,
                "status": str(prop_data.get("status", "PENDING")).upper(),
                "can_delegate": False,
                "is_expired": False,
                "revoked": False,
                "message": "Proposal has not received formal human authorization.",
            }

    data = approval_doc.to_dict() or {} if approval_doc.exists else {}

    # Revocation check
    if data.get("revoked", False):
        return {
            "approved": False,
            "proposal_id": proposal_id,
            "status": "REVOKED",
            "revoked": True,
            "revoke_reason": data.get("revoke_reason"),
            "can_delegate": False,
            "is_expired": False,
            "message": f"Approval was revoked: {data.get('revoke_reason')}",
        }

    # 7-day TTL expiration check
    now = datetime.now(UTC)
    expires_at_val = data.get("expires_at")
    if expires_at_val:
        if isinstance(expires_at_val, str):
            expires_at = datetime.fromisoformat(expires_at_val)
        else:
            expires_at = expires_at_val
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if now >= expires_at:
            return {
                "approved": False,
                "proposal_id": proposal_id,
                "status": "EXPIRED",
                "is_expired": True,
                "revoked": False,
                "can_delegate": False,
                "message": "Approval expired (7-day TTL elapsed). Re-authorization required.",
            }

    is_approved = data.get("approved", True)
    return {
        "approved": is_approved,
        "proposal_id": proposal_id,
        "status": "APPROVED" if is_approved else "PENDING",
        "approver": data.get("approver_id") or data.get("approver"),
        "approver_email": data.get("approver_email"),
        "gate_type": data.get("gate_type", required_gate),
        "expires_at": str(expires_at_val) if expires_at_val else None,
        "is_expired": False,
        "revoked": False,
        "can_delegate": is_approved,
        "message": "Proposal is approved and active for migration execution.",
    }


def revoke_approval(
    proposal_id: str,
    revoker_info: dict[str, Any] | str,
    reason: str,
    client: Any = None,  # noqa: ANN401
) -> dict[str, Any]:
    """Revokes a previously granted approval, halting any running or pending pipeline.

    Logs the halt reason and revoking identity to Cloud Audit Logs and updates
    state in Firestore and Cloud SQL.
    """
    clean_reason = reason.strip() if reason else ""
    if not clean_reason:
        raise ValueError("Revocation reason must not be empty or whitespace.")

    revoker_id = (
        revoker_info if isinstance(revoker_info, str) else revoker_info.get("uid", "unknown")
    )
    revoker_email = revoker_info.get("email") if isinstance(revoker_info, dict) else None

    if client is None:
        client = _get_firestore_client()
    now = datetime.now(UTC)

    approval_ref = client.collection("approvals").document(proposal_id)
    update_data = {
        "proposal_id": proposal_id,
        "revoked": True,
        "revoked_at": now.isoformat(),
        "revoked_by": revoker_id,
        "revoker_email": revoker_email,
        "revoke_reason": clean_reason,
        "approved": False,
    }
    app_snap = approval_ref.get()
    if app_snap.exists:
        approval_ref.update(update_data)
    else:
        approval_ref.set(update_data, merge=True)

    prop_ref = client.collection("consolidation_proposals").document(proposal_id)
    with contextlib.suppress(Exception):
        prop_ref.update({"status": "revoked", "updated_at": now.isoformat()})

    # Emit Cloud Audit Log
    audit_record = {
        "event_type": "HITL_APPROVAL_REVOKED",
        "proposal_id": proposal_id,
        "revoked_by": revoker_id,
        "revoker_email": revoker_email,
        "reason": clean_reason,
        "timestamp": now.isoformat(),
    }
    _get_audit_logger().log_struct(audit_record, severity="WARNING")

    with contextlib.suppress(Exception):
        from zombie_saas_coordinator.shared.db.cloudsql_client import (
            record_revocation_in_cloudsql,
        )

        record_revocation_in_cloudsql(
            proposal_id,
            {
                "revoked_at": now,
                "revoked_by": revoker_id,
                "revoke_reason": clean_reason,
            },
        )

    return {
        "revoked": True,
        "proposal_id": proposal_id,
        "reason": clean_reason,
        "revoked_by": revoker_id,
        "revoked_at": now.isoformat(),
    }


root_agent = Agent(
    name="zombie_saas_coordinator",
    model="gemini-3.5-flash",
    description=(
        "Root orchestrator for the Zombie SaaS Consolidator platform. "
        "Coordinates detection, validation, and migration planning for "
        "redundant SaaS applications."
    ),
    instruction=(
        "You are the Zombie SaaS Coordinator, the root orchestrator of a "
        "multi-agent system that detects and consolidates redundant SaaS tools.\n\n"
        "## Workflow\n"
        "1. Delegate to the **auditor_agent** for zombie SaaS detection and "
        "consolidation proposal generation.\n"
        "2. After the auditor generates a proposal and sends an approval card, "
        "WAIT for human approval (HITL gate). Use `check_approval_status` to verify.\n"
        "3. Once approved, delegate SIMULTANEOUSLY to:\n"
        "   - **architect_agent** for semantic contract validation\n"
        "   - **integrator_agent** for automation dependency scanning\n"
        "4. Aggregate results into a final migration readiness report.\n\n"
        "## CRITICAL RULES\n"
        "- NEVER proceed past step 2 without explicit human approval.\n"
        "- NEVER modify data in external systems (Trello, Asana) — read-only analysis.\n"
        "- ALL actions must be logged for compliance audit trail.\n"
    ),
    tools=[check_approval_status, revoke_approval],
    sub_agents=[auditor_agent, architect_agent, integrator_agent],
)

# Alias for ADK loader compatibility
agent = root_agent
