import contextlib
import os
from datetime import UTC, datetime
from typing import Any

from google.cloud import firestore, logging


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily."""
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database=database)


def _get_audit_logger() -> Any:
    """Structured audit logger for HITL approval gates."""
    client = logging.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    return client.logger("hitl-approval-audit")


def check_approval_status(
    proposal_id: str,
    required_gate: str = "PERMISSION_TO_MIGRATE",
) -> dict[str, Any]:
    """Checks whether a consolidation proposal has been approved by an authorized human."""
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
        prop_data = prop_doc.to_dict() or {}
        return {
            "approved": False,
            "proposal_id": proposal_id,
            "status": str(prop_data.get("status", "PENDING")).upper(),
            "can_delegate": False,
            "is_expired": False,
            "revoked": False,
            "message": f"Proposal has not received formal human authorization for gate {required_gate}.",
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
    reason: str,
    revoker_info: str = "system",
    **kwargs: Any,
) -> dict[str, Any]:
    """Revokes previously granted approvals, halting any running or pending pipeline."""
    clean_reason = reason.strip() if reason else ""
    if not clean_reason:
        raise ValueError("Revocation reason must not be empty or whitespace.")

    revoker_id = (
        revoker_info if isinstance(revoker_info, str) else revoker_info.get("uid", "unknown")
    )
    revoker_email = revoker_info.get("email") if isinstance(revoker_info, dict) else None

    client = kwargs.get("client")
    if client is None:
        client = _get_firestore_client()
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

    try:
        app_docs = client.collection("approvals").where(filter=firestore.FieldFilter("proposal_id", "==", proposal_id)).get()
        for app_snap in app_docs:
            app_snap.reference.update(update_data)
    except Exception:
        # Fallback to single doc if index fails or something
        approval_ref = client.collection("approvals").document(proposal_id)
        app_snap = approval_ref.get()
        if app_snap.exists:
            approval_ref.update(update_data)

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
