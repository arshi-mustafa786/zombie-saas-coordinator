"""HITL Approval API endpoints — US-5.

Provides:
  POST /{proposal_id}/authorize  — Record per-gate human approval (auth required)
  POST /{proposal_id}/revoke     — Revoke all active approvals (auth required)
  GET  /{proposal_id}            — Read per-gate approval status (auth required)
"""

import contextlib
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from google.cloud import firestore, logging

from zombie_saas_coordinator.shared.approvals.approvals import revoke_approval
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


class _SafeAuditLogger:
    """Fallback logger used when Google ADC or Cloud Logging is unavailable."""

    def __init__(self, logger: Any | None = None) -> None:
        self._logger = logger

    def __getattr__(self, name: str) -> Any:
        if self._logger is None:
            return lambda *args, **kwargs: None
        return getattr(self._logger, name)

    def log_struct(self, *args: Any, **kwargs: Any) -> None:
        if self._logger is None:
            return None
        try:
            self._logger.log_struct(*args, **kwargs)
        except Exception:
            return None


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily."""
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database=database)


def _get_audit_logger() -> Any:  # noqa: ANN401
    """Structured audit logger for HITL authorization events."""
    try:
        client = logging.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))  # type: ignore[no-untyped-call]
        return _SafeAuditLogger(client.logger("hitl-approval-audit"))  # type: ignore[no-untyped-call]
    except Exception:
        return _SafeAuditLogger()


def record_approval(
    proposal_id: str,
    approver_info: dict[str, Any],
    gate_type: str = "PERMISSION_TO_MIGRATE",
    notes: str | None = None,
) -> ApprovalRecord:
    """Persists per-gate human approval record with 7-day TTL to Firestore and Cloud SQL.

    The Firestore document is keyed as `{proposal_id}_{gate_type}` so that each
    of the three gates (INVESTIGATE, MIGRATE, DISPOSE) can be approved independently.

    The proposal document is updated to APPROVED status on first authorization but
    gate_type is intentionally NOT written back onto the proposal — the proposal
    has its own semantic signature (US-3) that must not be mutated by approval records.
    """
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

    # Store the approval document keyed by proposal_id + gate so all three
    # gates can coexist without overwriting each other.
    doc_id = f"{proposal_id}_{record.gate_type.value}"
    approval_ref = client.collection("approvals").document(doc_id)
    approval_ref.set(record.model_dump(mode="json"))

    # Update proposal status — but only record who actioned it, NOT the gate_type.
    # Writing gate_type here would corrupt the US-3 semantic signature.
    prop_ref = client.collection("consolidation_proposals").document(proposal_id)
    prop_ref.update({
        "status": ProposalStatus.APPROVED.value,
        "updated_at": now.isoformat(),
        "action_by": record.approver_id,
        "action_email": record.approver_email,
        # Do NOT write record.gate_type.value here — it breaks US-3 signature.
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
    """Grant formal human authorization for a specific gate on a consolidation proposal.

    Verifies Firebase SSO token and CISO/IT-Ops claims.  Checks only the
    *per-gate* approval document — not the overall proposal status — so that
    all three gates (INVESTIGATE, MIGRATE, DISPOSE) can be authorized
    independently without triggering a 409 after the first one.
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

    # Check only the per-gate approval doc — NOT proposal.status.
    # proposal.status == APPROVED just means at least one gate was approved;
    # it must not block subsequent gate approvals (AC-5.1 three-gate design).
    doc_id = f"{proposal_id}_{request.gate_type.value}"
    approval_ref = client.collection("approvals").document(doc_id)
    app_snap = approval_ref.get()
    if app_snap.exists:
        existing_app = app_snap.to_dict() or {}
        if existing_app.get("approved") and not existing_app.get("revoked"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Gate '{request.gate_type.value}' for proposal '{proposal_id}' "
                    "has already been authorized."
                ),
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
    """Revoke all active gate approvals and halt consolidation.

    Requires CISO/IT-Ops Firebase token. Passes the authenticated user identity
    through to revoke_approval so revocations are never anonymous.
    """
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

    try:
        revoke_approval(
            proposal_id=proposal_id,
            revoker_info=user_info,
            reason=clean_reason,
            client=client,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

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
async def get_approval_status_endpoint(
    proposal_id: str,
    gate_type: str = "PERMISSION_TO_MIGRATE",
    authorization: str = Header(..., description="Firebase ID token — Bearer <token>"),
) -> ApprovalStatusResponse:
    """Retrieve per-gate HITL approval status for a proposal.

    Requires a valid Firebase Authorization header so that approver emails,
    UIDs, and role information are not exposed to unauthenticated callers.
    Any authenticated user (no specific role required) may read status.
    """
    token = authorization.removeprefix("Bearer ").strip()
    verify_firebase_auth_token(token)  # any authenticated caller — no role restriction

    client = _get_firestore_client()
    prop_snap = client.collection("consolidation_proposals").document(proposal_id).get()
    if not prop_snap.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consolidation proposal '{proposal_id}' was not found.",
        )

    doc_id = f"{proposal_id}_{gate_type}"
    app_snap = client.collection("approvals").document(doc_id).get()
    if not app_snap.exists:
        return ApprovalStatusResponse(
            proposal_id=proposal_id,
            gate_type=gate_type,
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
