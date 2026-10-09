"""HITL Approval gate helpers — shared module.

Contains the gate-keyed Firestore logic for checking and revoking approvals.
Lives in the shared package so both the root agent and the API router can
import it without creating a circular dependency.
"""

import os
from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore, logging

from zombie_saas_coordinator.shared.models.proposal import ProposalStatus


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily."""
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database=database)


def _get_audit_logger() -> Any:
    """Structured audit logger for HITL approval gates."""
    client = logging.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))  # type: ignore[no-untyped-call]
    return client.logger("hitl-approval-audit")  # type: ignore[no-untyped-call]


def check_approval_status(
    proposal_id: str,
    required_gate: str = "PERMISSION_TO_MIGRATE",
) -> dict[str, Any]:
    """Checks whether a specific gate on a proposal has been approved.

    Reads the per-gate approval document (keyed as `{proposal_id}_{gate}`),
    enforces 7-day TTL expiration, and returns a structured result that the
    root agent uses to decide whether delegation is safe.
    """
    client = _get_firestore_client()
    doc_id = f"{proposal_id}_{required_gate}"
    approval_doc = client.collection("approvals").document(doc_id).get()

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
        return {
            "approved": False,
            "proposal_id": proposal_id,
            "status": "PENDING",
            "can_delegate": False,
            "is_expired": False,
            "revoked": False,
            "message": (
                f"No approval found for gate '{required_gate}'. "
                "Human authorization via the /authorize endpoint is required."
            ),
        }

    data = approval_doc.to_dict() or {}

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

    is_approved = bool(data.get("approved", False))
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
    reason: str,
    revoker_info: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Revokes ALL active gate approvals for a proposal, halting the pipeline.

    Queries all per-gate approval documents by proposal_id and marks each as
    revoked. Raises RuntimeError if no approval documents are found (prevents
    silent no-ops). Updates the proposal status to REVOKED (a valid ProposalStatus
    enum value) and emits a Cloud Audit Log entry.

    Args:
        proposal_id: The proposal whose approvals are being revoked.
        reason: Mandatory non-empty reason for the revocation.
        revoker_info: Dict with 'uid' and optional 'email' of the authenticated revoker.
            Must be a real identity dict — anonymous revocations are not permitted.
        **kwargs: Optional 'client' (Firestore client) for testing injection.

    Raises:
        ValueError: If reason is empty or revoker_info is missing a uid.
        RuntimeError: If no approval documents are found for the proposal (prevents
            silent success when nothing was actually revoked).
    """
    clean_reason = reason.strip() if reason else ""
    if not clean_reason:
        raise ValueError("Revocation reason must not be empty or whitespace.")

    if not isinstance(revoker_info, dict) or not revoker_info.get("uid"):
        raise ValueError(
            "revoker_info must be a dict with a non-empty 'uid'. "
            "Anonymous revocations are not permitted."
        )

    revoker_id: str = revoker_info["uid"]
    revoker_email: str | None = revoker_info.get("email")

    client: firestore.Client = kwargs.get("client") or _get_firestore_client()
    now = datetime.now(UTC)

    update_data = {
        "proposal_id": proposal_id,
        "revoked": True,
        "revoked_at": now.isoformat(),
        "revoked_by": revoker_id,
        "revoker_email": revoker_email,
        "revoke_reason": clean_reason,
        "approved": False,
    }

    # Query all per-gate approval documents for this proposal.
    # This is the authoritative path — if it fails we raise immediately instead
    # of silently falling back to a stale document ID.
    app_docs = (
        client.collection("approvals")
        .where(filter=firestore.FieldFilter("proposal_id", "==", proposal_id))
        .get()
    )

    if not app_docs:
        raise RuntimeError(
            f"No approval documents found for proposal '{proposal_id}'. "
            "Nothing was revoked; downstream agents may still be running."
        )

    for snap in app_docs:
        snap.reference.update(update_data)

    # Update proposal to REVOKED — uses the enum value, not a raw string.
    prop_ref = client.collection("consolidation_proposals").document(proposal_id)
    try:
        prop_ref.update({
            "status": ProposalStatus.REVOKED.value,
            "updated_at": now.isoformat(),
        })
    except Exception as exc:
        # Log but don't suppress — callers must know if the proposal wasn't updated.
        _get_audit_logger().log_struct(
            {
                "event_type": "HITL_PROPOSAL_UPDATE_FAILED",
                "proposal_id": proposal_id,
                "error": str(exc),
                "timestamp": now.isoformat(),
            },
            severity="ERROR",
        )
        raise RuntimeError(
            f"Approval documents revoked but proposal status update failed: {exc}"
        ) from exc

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

    try:
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
    except Exception as exc:
        # Cloud SQL sync failure is non-fatal — Firestore is the source of truth.
        _get_audit_logger().log_struct(
            {
                "event_type": "CLOUDSQL_REVOCATION_SYNC_FAILED",
                "proposal_id": proposal_id,
                "error": str(exc),
            },
            severity="WARNING",
        )

    return {
        "revoked": True,
        "proposal_id": proposal_id,
        "reason": clean_reason,
        "revoked_by": revoker_id,
        "revoked_at": now.isoformat(),
    }
