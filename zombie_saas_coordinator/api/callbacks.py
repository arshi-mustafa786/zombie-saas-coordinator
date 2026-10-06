"""Cloud Run API endpoints for Interactive Approval Card notifications and callbacks."""

import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from google.cloud import firestore, logging
from pydantic import BaseModel, Field, ValidationError

from zombie_saas_coordinator.agents.auditor.tools import send_approval_card
from zombie_saas_coordinator.shared.models.proposal import (
    ConsolidationProposal,
    ProposalStatus,
)

router = APIRouter(prefix="/api/v1", tags=["notifications", "callbacks"])

# States that cannot transition further — a second button click must be rejected.
_TERMINAL_STATES = {ProposalStatus.APPROVED, ProposalStatus.WHITELISTED, ProposalStatus.EXPIRED}

# Replay window: reject Slack requests with a timestamp older than 5 minutes.
_SLACK_TIMESTAMP_TOLERANCE_SECONDS = 300


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily."""
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database=database)


def _get_audit_logger() -> Any:
    """Structured audit logger for HITL callbacks."""
    client = logging.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))  # type: ignore[no-untyped-call]
    return client.logger("hitl-approval-audit")  # type: ignore[no-untyped-call]


def _verify_slack_signature(raw_body: bytes, request: Request) -> None:
    """Verify the X-Slack-Signature header using HMAC-SHA256 (Slack signing secret).

    Raises HTTPException 403 on invalid signature, 503 if the secret is not configured.
    """
    signing_secret = os.getenv("SLACK_SIGNING_SECRET", "")
    if not signing_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack signing secret is not configured.",
        )
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    sig_header = request.headers.get("X-Slack-Signature", "")

    # Replay attack guard: reject stale timestamps.
    try:
        if abs(time.time() - int(timestamp)) > _SLACK_TIMESTAMP_TOLERANCE_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request timestamp is too old (possible replay attack).",
            )
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid X-Slack-Request-Timestamp header.",
        )

    basestring = f"v0:{timestamp}:{raw_body.decode('utf-8')}"
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        basestring.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, sig_header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Slack request signature.",
        )


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
    channel: str = Field(
        ...,
        description=(
            "Slack incoming webhook URL (must be https://hooks.slack.com/...). "
            "Slack channel IDs are not supported — use a webhook URL instead."
        ),
    )


@router.post("/callbacks/approval", status_code=status.HTTP_200_OK)
async def handle_approval_callback(request: Request) -> dict[str, Any]:
    """Processes interactive button clicks from Slack/Teams approval cards.

    Enforces request authentication, validates proposal lifecycle, enforces a
    state machine to prevent re-decisions, records approver identity in
    Firestore, and logs an immutable Cloud Audit Log entry.
    """
    content_type = request.headers.get("content-type", "")
    raw_body = await request.body()

    if "application/x-www-form-urlencoded" in content_type:
        # ── Slack native form payload ──────────────────────────────────────
        # Authenticate first using the signing secret before parsing any data.
        _verify_slack_signature(raw_body, request)

        try:
            form = await request.form()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not parse form data.",
            ) from exc

        payload_str = form.get("payload")
        if not payload_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing 'payload' in form data.",
            )
        try:
            data = json.loads(str(payload_str))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON in 'payload' form field.",
            ) from exc

        actions = data.get("actions", [])
        if not actions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No actions found in Slack payload.",
            )

        action_data = actions[0]
        user_data = data.get("user", {})
        user_id = user_data.get("id", "")

        # FR2.2/FR2.3: Identity is mandatory — reject payloads with no user ID.
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slack payload is missing user identity (user.id).",
            )

        try:
            payload_obj = ApprovalCallbackPayload(
                token="__slack_signed__",  # Signing secret already verified above.
                action=action_data.get("action_id", ""),
                proposal_id=action_data.get("value", ""),
                user_id=user_id,
                # user.name is a Slack handle, not an SSO email — stored for audit purposes only.
                user_email=user_data.get("name"),
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Slack action payload: {exc}",
            ) from exc

    else:
        # ── JSON branch (internal API / tests) ────────────────────────────
        expected_token = os.getenv("SLACK_VERIFICATION_TOKEN", "")
        if not expected_token:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Callback verification token is not configured.",
            )

        try:
            body = json.loads(raw_body)
            payload_obj = ApprovalCallbackPayload.model_validate(body)
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request payload: {exc}",
            ) from exc

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

    # State machine guard: terminal proposals must not be re-decided.
    if proposal.status in _TERMINAL_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Proposal '{payload_obj.proposal_id}' is already in terminal state "
                f"'{proposal.status.value}' and cannot be actioned again."
            ),
        )

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
    """API endpoint to dispatch an interactive approval card for a proposal.

    The `channel` field must be a Slack incoming webhook URL
    (https://hooks.slack.com/services/...). Slack channel IDs are not supported.
    """
    result = send_approval_card(proposal_id=request.proposal_id, channel=request.channel)
    if not result.get("sent"):
        error_msg = result.get("error", "unknown error")
        # SSRF / protocol / domain errors are client mistakes → 400, not 500.
        is_client_error = any(
            keyword in error_msg
            for keyword in ("Insecure protocol", "not in the allowed", "SSRF", "forbidden")
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST if is_client_error else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dispatch approval card: {error_msg}",
        )
    return result
