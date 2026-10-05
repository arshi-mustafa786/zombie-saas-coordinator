"""Cloud Run API endpoints for Interactive Approval Card notifications and callbacks."""

import hmac
import os
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status, Request
from google.cloud import firestore, logging
from pydantic import BaseModel, Field
import json

from zombie_saas_coordinator.agents.auditor.tools import send_approval_card
from zombie_saas_coordinator.shared.models.proposal import (
    ConsolidationProposal,
    ProposalStatus,
)

router = APIRouter(prefix="/api/v1", tags=["notifications", "callbacks"])


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily."""
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database=database)


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
async def handle_approval_callback(request: Request) -> dict[str, Any]:
    """Processes interactive button clicks from Slack/Teams approval cards.

    Enforces token authentication, validates proposal lifecycle, records
    approver identity in Firestore, and logs an immutable Cloud Audit Log entry.
    """
    content_type = request.headers.get("content-type", "")
    
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        payload_str = form.get("payload")
        if not payload_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Missing 'payload' in form data."
            )
        try:
            data = json.loads(str(payload_str))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Invalid JSON in 'payload' form field."
            )
        
        actions = data.get("actions", [])
        if not actions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="No actions found in Slack payload."
            )
            
        action_data = actions[0]
        user_data = data.get("user", {})
        
        payload_obj = ApprovalCallbackPayload(
            token=data.get("token", ""),
            action=action_data.get("action_id", ""),
            proposal_id=action_data.get("value", ""),
            user_id=user_data.get("id", "unknown"),
            user_email=user_data.get("name")
        )
    else:
        body = await request.json()
        payload_obj = ApprovalCallbackPayload.model_validate(body)

    expected_token = os.getenv("SLACK_VERIFICATION_TOKEN", "default-verification-token")
    if not hmac.compare_digest(payload_obj.token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid callback verification token.",
        )

    client = _get_firestore_client()
    doc_ref = client.collection("consolidation_proposals").document(payload_obj.proposal_id)
    snapshot = doc_ref.get()

    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consolidation proposal '{payload_obj.proposal_id}' not found.",
        )

    data = snapshot.to_dict() or {}
    proposal = ConsolidationProposal.model_validate(data)

    # Check for expiration
    now = datetime.now(UTC)
    if proposal.status == ProposalStatus.EXPIRED or (
        proposal.expires_at and proposal.expires_at < now
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Consolidation proposal '{payload_obj.proposal_id}' has expired.",
        )

    # Determine state transition
    if payload_obj.action == "approve_consolidation":
        new_state = ProposalStatus.APPROVED
    elif payload_obj.action == "simulate_migration":
        new_state = ProposalStatus.SIMULATING
    elif payload_obj.action == "ignore_whitelist":
        new_state = ProposalStatus.WHITELISTED
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported action '{payload_obj.action}'.",
        )

    update_payload = {
        "status": new_state.value,
        "updated_at": now.isoformat(),
        "action_by": payload_obj.user_id,
        "action_email": payload_obj.user_email,
        "action": payload_obj.action,
    }
    doc_ref.update(update_payload)

    # Emit Cloud Audit Log
    audit_record = {
        "event_type": "HITL_APPROVAL_CALLBACK",
        "proposal_id": payload_obj.proposal_id,
        "action": payload_obj.action,
        "new_state": new_state.value,
        "user_id": payload_obj.user_id,
        "user_email": payload_obj.user_email,
        "timestamp": now.isoformat(),
    }
    _get_audit_logger().log_struct(audit_record, severity="NOTICE")

    return {
        "status": "success",
        "action": payload_obj.action,
        "proposal_id": payload_obj.proposal_id,
        "new_state": new_state.value,
        "message": f"Action '{payload_obj.action}' processed successfully.",
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
