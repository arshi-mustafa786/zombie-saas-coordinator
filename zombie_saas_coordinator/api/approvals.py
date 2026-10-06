import contextlib
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, status
from google.cloud import firestore, logging

from zombie_saas_coordinator.agent import revoke_approval
from zombie_saas_coordinator.shared.auth.firebase_auth import verify_firebase_auth_token
from zombie_saas_coordinator.shared.db.cloudsql_client import (
    record_approval_in_cloudsql,
    record_revocation_in_cloudsql,
)
from zombie_saas_coordinator.shared.models.approval import (
    ApprovalGateType,
    ApprovalRecord,
    ApprovalStatusResponse,
    AuthorizeProposalRequest,
    RevokeApprovalRequest,
)
from zombie_saas_coordinator.shared.models.proposal import ProposalStatus

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals", "hitl"])


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily."""
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database=database)


def _get_audit_logger() -> Any:  # noqa: ANN401
    """Structured audit logger for HITL authorization events."""
    client = logging.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))  # type: ignore[no-untyped-call]
    return client.logger("hitl-approval-audit")  # type: ignore[no-untyped-call]


def record_approval(
    proposal_id: str,
    approver_info: dict[str, Any],
    gate_type: str = "PERMISSION_TO_MIGRATE",
    notes: str | None = None,
) -> ApprovalRecord:
    """Persists human approval record with 7-day TTL to Firestore and Cloud SQL."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=7)

    gate_enum = (
        ApprovalGateType(gate_type)
        if isinstance(gate_type, str) and gate_type in ApprovalGateType._value2member_map_
        else ApprovalGateType.PERMISSION_TO_MIGRATE
    )

    record = ApprovalRecord(
        proposal_id=proposal_id,
        gate_type=gate_enum,
        approved=True,
        approver_id=approver_info["uid"],
        approver_email=approver_info.get("email"),
        roles=approver_info.get("roles", []),
        approved_at=now,
        expires_at=expires_at,
        notes=notes,
        revoked=False,
    )

    client = _get_firestore_client()
    approval_ref = client.collection("approvals").document(proposal_id)
    approval_ref.set(record.model_dump(mode="json"))

    prop_ref = client.collection("consolidation_proposals").document(proposal_id)
    prop_ref.update({
        "status": ProposalStatus.APPROVED.value,
        "updated_at": now.isoformat(),
        "action_by": record.approver_id,
        "action_email": record.approver_email,
        "gate_type": record.gate_type.value,
    })

    with contextlib.suppress(Exception):
        record_approval_in_cloudsql({
            "proposal_id": proposal_id,
            "gate_type": record.gate_type.value,
            "approved": True,
            "approver_id": record.approver_id,
            "approver_email": record.approver_email,
            "roles": record.roles,
            "approved_at": now,
            "expires_at": expires_at,
            "notes": notes,
            "revoked": False,
        })

    audit_payload = {
        "event_type": "HITL_PROPOSAL_AUTHORIZED",
        "proposal_id": proposal_id,
        "gate_type": record.gate_type.value,
        "approver_id": record.approver_id,
        "approver_email": record.approver_email,
        "roles": record.roles,
        "expires_at": expires_at.isoformat(),
        "notes": notes,
        "timestamp": now.isoformat(),
    }
    _get_audit_logger().log_struct(audit_payload, severity="NOTICE")

    return record


@router.post("/{proposal_id}/authorize", status_code=status.HTTP_200_OK)
async def authorize_proposal_endpoint(
    proposal_id: str,
    request: AuthorizeProposalRequest,
) -> dict[str, Any]:
    """Cloud Run endpoint to grant formal human authorization for consolidation.

    Verifies Firebase SSO token and CISO/IT-Ops claims, checks proposal lifecycle,
    and records an immutable 7-day TTL approval.
    """
    user_info = verify_firebase_auth_token(
        request.firebase_token,
        required_roles=["ciso", "it_ops", "admin", "security_admin"],
    )

    client = _get_firestore_client()
    prop_ref = client.collection("consolidation_proposals").document(proposal_id)
    prop_snap = prop_ref.get()

    if not prop_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consolidation proposal '{proposal_id}' was not found.",
        )

    prop_data = prop_snap.to_dict() or {}
    current_status = prop_data.get("status")

    approval_ref = client.collection("approvals").document(proposal_id)
    app_snap = approval_ref.get()
    if app_snap.exists:
        existing_app = app_snap.to_dict() or {}
        if existing_app.get("approved") and not existing_app.get("revoked"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Proposal '{proposal_id}' has already been authorized.",
            )

    if current_status == ProposalStatus.APPROVED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Proposal '{proposal_id}' is already approved.",
        )

    record = record_approval(
        proposal_id=proposal_id,
        approver_info=user_info,
        gate_type=request.gate_type.value,
        notes=request.notes,
    )

    return {
        "status": "success",
        "approved": True,
        "proposal_id": proposal_id,
        "gate_type": record.gate_type.value,
        "approver_id": record.approver_id,
        "expires_at": record.expires_at.isoformat(),
        "message": f"Proposal authorized successfully under {record.gate_type.value}.",
    }


@router.post("/{proposal_id}/revoke", status_code=status.HTTP_200_OK)
async def revoke_approval_endpoint(
    proposal_id: str,
    request: RevokeApprovalRequest,
) -> dict[str, Any]:
    """Cloud Run endpoint to revoke approval and halt consolidation."""
    clean_reason = request.reason.strip() if request.reason else ""
    if not clean_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Revocation reason cannot be empty or whitespace.",
        )

    user_info = verify_firebase_auth_token(
        request.firebase_token,
        required_roles=["ciso", "it_ops", "admin", "security_admin"],
    )

    client = _get_firestore_client()
    prop_ref = client.collection("consolidation_proposals").document(proposal_id)
    prop_snap = prop_ref.get()
    if not prop_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consolidation proposal '{proposal_id}' was not found.",
        )

    revoke_approval(
        proposal_id=proposal_id,
        revoker_info=user_info,
        reason=clean_reason,
        client=client,
    )

    audit_record = {
        "event_type": "HITL_APPROVAL_REVOKED",
        "proposal_id": proposal_id,
        "revoked_by": user_info["uid"],
        "revoker_email": user_info.get("email"),
        "reason": clean_reason,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    _get_audit_logger().log_struct(audit_record, severity="WARNING")

    with contextlib.suppress(Exception):
        record_revocation_in_cloudsql(
            proposal_id,
            {
                "revoked_at": datetime.now(UTC),
                "revoked_by": user_info["uid"],
                "revoke_reason": clean_reason,
            },
        )

    return {
        "status": "success",
        "revoked": True,
        "proposal_id": proposal_id,
        "reason": clean_reason,
        "revoked_by": user_info["uid"],
        "message": f"Approval for proposal '{proposal_id}' has been revoked.",
    }


@router.get("/{proposal_id}", response_model=ApprovalStatusResponse, status_code=status.HTTP_200_OK)
async def get_approval_status_endpoint(proposal_id: str) -> ApprovalStatusResponse:
    """Retrieves current HITL approval gate and expiry details for a proposal."""
    client = _get_firestore_client()
    prop_snap = client.collection("consolidation_proposals").document(proposal_id).get()
    if not prop_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consolidation proposal '{proposal_id}' was not found.",
        )

    app_snap = client.collection("approvals").document(proposal_id).get()
    if not app_snap.exists:
        return ApprovalStatusResponse(
            proposal_id=proposal_id,
            gate_type=ApprovalGateType.PERMISSION_TO_MIGRATE.value,
            approved=False,
            can_delegate=False,
        )

    data = app_snap.to_dict() or {}
    record = ApprovalRecord.model_validate(data)

    return ApprovalStatusResponse(
        proposal_id=proposal_id,
        gate_type=record.gate_type.value,
        approved=record.is_active,
        approver_id=record.approver_id,
        approver_email=record.approver_email,
        roles=record.roles,
        approved_at=record.approved_at.isoformat(),
        expires_at=record.expires_at.isoformat(),
        is_expired=record.is_expired,
        revoked=record.revoked,
        revoke_reason=record.revoke_reason,
        can_delegate=record.is_active,
    )
