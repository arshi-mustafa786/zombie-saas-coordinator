"""Data models for US-12: Fail-Safe Quarantine and Disposal."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class QuarantineStatus(StrEnum):
    """Lifecycle states for fail-safe data quarantine and disposal."""

    SOURCE_QUARANTINED = "SOURCE_QUARANTINED"
    DISPOSAL_PENDING_APPROVAL = "DISPOSAL_PENDING_APPROVAL"
    DISPOSAL_APPROVED = "DISPOSAL_APPROVED"
    DISPOSAL_BLOCKED = "DISPOSAL_BLOCKED"
    SOURCE_DESTROYED = "SOURCE_DESTROYED"


class DisposalSignature(BaseModel):
    """Cryptographically auditable authorization signature for multi-sig disposal."""

    signer_id: str = Field(..., description="Firebase UID of the authorizing user")
    signer_email: str | None = Field(default=None, description="SSO email of the authorizer")
    role: str = Field(..., description="Authorizing role (e.g., ciso, compliance_officer, admin)")
    signed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when authorization signature was recorded",
    )
    notes: str | None = Field(default=None, description="Optional justification or sign-off notes")


class ValidationExceptionItem(BaseModel):
    """Validation or reconciliation discrepancy that blocks disposal."""

    exception_id: str = Field(..., description="Unique exception identifier")
    description: str = Field(..., description="Description of the discrepancy")
    severity: str = Field(
        default="MEDIUM", description="Severity level: LOW, MEDIUM, HIGH, CRITICAL"
    )
    resolved: bool = Field(default=False, description="Whether exception has been resolved")
    resolved_by: str | None = Field(default=None, description="UID of operator who resolved")
    resolved_at: datetime | None = Field(default=None, description="Timestamp of resolution")
    resolution_notes: str | None = Field(default=None, description="Resolution rationale")


def _default_quarantine_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=90)


class QuarantineRecord(BaseModel):
    """Comprehensive state record for quarantined source SaaS data."""

    proposal_id: str = Field(..., description="Associated consolidation proposal ID")
    app_id: str = Field(..., description="Unique source SaaS application ID")
    app_name: str = Field(..., description="Name of source SaaS application")
    status: QuarantineStatus = Field(
        default=QuarantineStatus.SOURCE_QUARANTINED,
        description="Current quarantine lifecycle state",
    )
    quarantined_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when quarantine was initiated",
    )
    retention_days: int = Field(
        default=90,
        description="Mandatory data retention window in days (default 90)",
    )
    expires_at: datetime = Field(
        default_factory=_default_quarantine_expiry,
        description="Expiration timestamp of the retention window",
    )
    legal_hold: bool = Field(
        default=False,
        description="Whether a legal / regulatory hold is active",
    )
    legal_hold_reason: str | None = Field(
        default=None,
        description="Mandatory reason if legal hold is active",
    )
    legal_hold_set_by: str | None = Field(
        default=None,
        description="UID of operator who set the legal hold",
    )
    legal_hold_set_at: datetime | None = Field(
        default=None,
        description="Timestamp when legal hold was applied",
    )
    migration_completed: bool = Field(
        default=True,
        description="Whether migration and reconciliation completed verified",
    )
    unresolved_exceptions: list[ValidationExceptionItem] = Field(
        default_factory=list,
        description="List of validation / reconciliation exceptions",
    )
    signatures: list[DisposalSignature] = Field(
        default_factory=list,
        description="Recorded authorization signatures for multi-signature approval",
    )
    required_signatures: int = Field(
        default=2,
        description="Minimum distinct signatures required for DISPOSAL_APPROVED",
    )
    disposal_certificate_id: str | None = Field(
        default=None,
        description="Certificate ID of verifiable destruction if executed",
    )

    @model_validator(mode="before")
    @classmethod
    def calculate_dates(cls, data: Any) -> Any:  # noqa: ANN401
        if isinstance(data, dict):
            quarantined_at = data.get("quarantined_at")
            retention_days = data.get("retention_days", 90)
            if quarantined_at is None:
                quarantined_at = datetime.now(UTC)
                data["quarantined_at"] = quarantined_at
            elif isinstance(quarantined_at, str):
                quarantined_at = datetime.fromisoformat(quarantined_at)

            if "expires_at" not in data or data.get("expires_at") is None:
                data["expires_at"] = quarantined_at + timedelta(days=retention_days)
        return data


class DisposalCertificate(BaseModel):
    """Cryptographically verifiable destruction certificate."""

    certificate_id: str = Field(..., description="Unique certificate identifier")
    proposal_id: str = Field(..., description="Proposal ID for which destruction was executed")
    app_id: str = Field(..., description="Application ID")
    app_name: str = Field(..., description="Application name")
    disposed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp of destruction execution",
    )
    executor_id: str = Field(..., description="UID of operator who executed destruction")
    executor_email: str | None = Field(default=None, description="Email of operator")
    signers: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Summary of authorizing signatures",
    )
    verification_hash: str = Field(
        ...,
        description="Cryptographic SHA-256 hash verifying disposal integrity",
    )
    items_purged_count: int = Field(
        default=0,
        description="Count of verified purged artifacts/cards/records",
    )
    status: str = Field(
        default="VERIFIED_DESTROYED",
        description="Destruction status confirmation",
    )


class QuarantineSourceRequest(BaseModel):
    """Request payload to initiate source quarantine."""

    firebase_token: str = Field(..., description="Firebase Auth SSO token")
    retention_days: int = Field(default=90, description="Retention window in days")
    source_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata override (app_id, app_name)",
    )


class LegalHoldRequest(BaseModel):
    """Request payload to apply or release a legal hold."""

    firebase_token: str = Field(..., description="Firebase Auth SSO token")
    legal_hold: bool = Field(..., description="True to enable hold, False to release")
    reason: str | None = Field(default=None, description="Reason for legal hold state change")


class DisposalSignRequest(BaseModel):
    """Request payload to submit a signature for multi-sig disposal authorization."""

    firebase_token: str = Field(..., description="Firebase Auth SSO token")
    notes: str | None = Field(default=None, description="Optional sign-off notes")


class DisposalExecuteRequest(BaseModel):
    """Request payload to execute verifiable disposal."""

    firebase_token: str = Field(..., description="Firebase Auth SSO token")


class ResolveExceptionRequest(BaseModel):
    """Request payload to resolve an exception."""

    firebase_token: str = Field(..., description="Firebase Auth SSO token")
    resolution_notes: str = Field(..., description="Detailed notes on how exception was resolved")
