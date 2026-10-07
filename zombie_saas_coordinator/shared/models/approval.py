"""Data models for US-5: 3-Tier HITL Approval Gates and Lifecycle Management."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ApprovalGateType(StrEnum):
    """Three-tier authorization gates for autonomous migration lifecycle."""

    PERMISSION_TO_INVESTIGATE = "PERMISSION_TO_INVESTIGATE"
    PERMISSION_TO_MIGRATE = "PERMISSION_TO_MIGRATE"
    PERMISSION_TO_DISPOSE = "PERMISSION_TO_DISPOSE"


def _default_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=7)


class ApprovalRecord(BaseModel):
    """Authoritative approval record with 7-day TTL and revocation tracking."""

    proposal_id: str = Field(..., description="Unique proposal identifier")
    gate_type: ApprovalGateType = Field(
        default=ApprovalGateType.PERMISSION_TO_MIGRATE,
        description="Specific authorization gate tier",
    )
    approved: bool = Field(default=True, description="Whether human approval was granted")
    approver_id: str = Field(..., description="Firebase UID of the authorizing user")
    approver_email: str | None = Field(default=None, description="SSO email of the authorizer")
    roles: list[str] = Field(default_factory=list, description="Verified SSO roles/claims")
    approved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when authorization was recorded",
    )
    expires_at: datetime = Field(
        default_factory=_default_expiry,
        description="Expiration timestamp (7-day TTL window)",
    )
    notes: str | None = Field(
        default=None,
        description="Optional notes or rationale from authorizer",
    )
    revoked: bool = Field(default=False, description="Flag indicating if approval was revoked")
    revoked_at: datetime | None = Field(default=None, description="Timestamp of revocation")
    revoked_by: str | None = Field(default=None, description="UID of operator who revoked")
    revoke_reason: str | None = Field(default=None, description="Mandatory reason for halt")

    @model_validator(mode="before")
    @classmethod
    def calculate_dates(cls, data: Any) -> Any:  # noqa: ANN401
        if isinstance(data, dict):
            approved_at = data.get("approved_at")
            if approved_at is None:
                approved_at = datetime.now(UTC)
                data["approved_at"] = approved_at
            elif isinstance(approved_at, str):
                approved_at = datetime.fromisoformat(approved_at)

            if "expires_at" not in data or data.get("expires_at") is None:
                data["expires_at"] = approved_at + timedelta(days=7)
        return data

    @property
    def is_expired(self) -> bool:
        """Determines if the 7-day TTL expiration window has elapsed."""
        now = datetime.now(UTC)
        expiry = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=UTC)
        return now >= expiry

    @property
    def is_active(self) -> bool:
        """Indicates if the approval is currently valid, unrevoked, and unexpired."""
        return self.approved and not self.revoked and not self.is_expired


class AuthorizeProposalRequest(BaseModel):
    """Payload for authorizing a proposal via Firebase SSO token."""

    firebase_token: str = Field(..., description="Firebase Authentication ID token")
    gate_type: ApprovalGateType = Field(
        default=ApprovalGateType.PERMISSION_TO_MIGRATE,
        description="Gate to authorize",
    )
    notes: str | None = Field(default=None, description="Optional justification notes")


class RevokeApprovalRequest(BaseModel):
    """Payload for revoking approval and halting agent pipeline."""

    firebase_token: str = Field(..., description="Firebase Authentication ID token of revoker")
    reason: str = Field(..., description="Mandatory halt/revocation reason")


class ApprovalStatusResponse(BaseModel):
    """Response model for approval status queries."""

    proposal_id: str
    gate_type: str
    approved: bool
    approver_id: str | None = None
    approver_email: str | None = None
    roles: list[str] = Field(default_factory=list)
    approved_at: str | None = None
    expires_at: str | None = None
    is_expired: bool = False
    revoked: bool = False
    revoke_reason: str | None = None
    can_delegate: bool = False
