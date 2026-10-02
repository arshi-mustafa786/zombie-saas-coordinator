"""Cloud Run API endpoints for Interactive Approval Card notifications and callbacks."""

import hmac
import os
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from google.cloud import firestore, logging
from pydantic import BaseModel, Field

from zombie_saas_coordinator.agents.auditor.tools import send_approval_card
from zombie_saas_coordinator.shared.models.proposal import (
    ConsolidationProposal,
    ProposalStatus,
    get_dummy_proposal,
)

router = APIRouter(prefix="/api/v1", tags=["notifications", "callbacks"])


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily."""
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))


def _get_audit_logger() -> Any:
    """Structured audit logger for HITL callbacks."""
    client = logging.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))  # type: ignore[no-untyped-call]
    return client.logger("hitl-approval-audit")  # type: ignore[no-untyped-call]


class ApprovalCallbackPayload(BaseModel):
    """Payload sent when an action button is clicked on an interactive approval card."""

    token: str = Field(..., description="Verification token to authenticate callback source")
    action: Literal["simulate_migration", "approve_consolidation", "ignore_whitelist"] = Field(
        ..., description="Action clicked by human operator"
    )
    proposal_id: str = Field(..., description="Target proposal identifier")
    user_id: str = Field(..., description="Identity of the operator performing the action")
    user_email: str | None = Field(default=None, description="SSO email of the operator")


class SendNotificationRequest(BaseModel):
    """Request model for dispatching an approval card."""

    proposal_id: str = Field(..., description="Proposal ID to dispatch")
    channel: str = Field(..., description="Slack channel ID or incoming webhook URL")


@router.post("/callbacks/approval", status_code=status.HTTP_200_OK)
async def handle_approval_callback(payload: ApprovalCallbackPayload) -> dict[str, Any]:
    """Processes interactive button clicks from Slack/Teams approval cards.

    Enforces token authentication, validates proposal lifecycle, records
    approver identity in Firestore, and logs an immutable Cloud Audit Log entry.
    """
    expected_token = os.getenv("SLACK_VERIFICATION_TOKEN", "default-verification-token")
    if not hmac.compare_digest(payload.token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid callback verification token.",
        )

    client = _get_firestore_client()
    doc_ref = client.collection("consolidation_proposals").document(payload.proposal_id)
    snapshot = doc_ref.get()

    if snapshot.exists:
        data = snapshot.to_dict() or {}
        proposal = ConsolidationProposal.model_validate(data)
    else:
        # Fallback to realistic dummy proposal if US-3 is still WIP
        proposal = get_dummy_proposal(payload.proposal_id)

    # Check for expiration
    now = datetime.now(UTC)
    if proposal.status == ProposalStatus.EXPIRED or (
        proposal.expires_at and proposal.expires_at < now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Consolidation proposal '{payload.proposal_id}' has expired.",
        )

    # Determine state transition
    if payload.action == "approve_consolidation":
        new_state = ProposalStatus.APPROVED
    elif payload.action == "simulate_migration":
        new_state = ProposalStatus.SIMULATING
    elif payload.action == "ignore_whitelist":
        new_state = ProposalStatus.WHITELISTED
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported action '{payload.action}'.",
        )

    update_payload = {
        "status": new_state.value,
        "updated_at": now.isoformat(),
        "action_by": payload.user_id,
        "action_email": payload.user_email,
        "action": payload.action,
    }
    doc_ref.update(update_payload)

    # Emit Cloud Audit Log
    audit_record = {
        "event_type": "HITL_APPROVAL_CALLBACK",
        "proposal_id": payload.proposal_id,
        "action": payload.action,
        "new_state": new_state.value,
        "user_id": payload.user_id,
        "user_email": payload.user_email,
        "timestamp": now.isoformat(),
    }
    _get_audit_logger().log_struct(audit_record, severity="NOTICE")

    return {
        "status": "success",
        "action": payload.action,
        "proposal_id": payload.proposal_id,
        "new_state": new_state.value,
        "message": f"Action '{payload.action}' processed successfully.",
    }


@router.post("/notifications/send", status_code=status.HTTP_200_OK)
async def send_notification_endpoint(request: SendNotificationRequest) -> dict[str, Any]:
    """API endpoint to dispatch an interactive approval card for a proposal."""
    result = send_approval_card(proposal_id=request.proposal_id, channel=request.channel)
    if not result.get("sent"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dispatch approval card: {result.get('error', 'unknown error')}",
        )
    return result
