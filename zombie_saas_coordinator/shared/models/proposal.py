"""Consolidation Proposal Data Models (US-3).

Defines strongly-typed Pydantic schemas for consolidation proposals,
ROI savings calculations, risk evaluations, and migration recommendations.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, model_validator

PROPOSAL_TTL_DAYS = 7


class RecommendationType(StrEnum):
    """Actionable recommendation categories for a proposal."""

    PROCEED_CONSOLIDATION = "Proceed to Full Consolidation"
    MANUAL_REVIEW = "Proceed with Manual Review"
    IGNORE_WHITELIST = "Ignore/Whitelist"


class ComplianceSensitivity(StrEnum):
    """Compliance sensitivity classification level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SavingsBreakdown(BaseModel):
    """ROI derived from IdP seat counts (US-1) and corporate card spend (US-2)."""

    seats: int = Field(ge=0, description="Total licensed seats reported by the IdP scan")
    monthly_cost: float = Field(
        ge=0.0, description="Monthly-equivalent subscription spend from the expense event"
    )
    cost_per_seat_monthly: float = Field(ge=0.0, description="monthly_cost / seats")
    estimated_annual_savings: float = Field(
        ge=0.0, description="Annual savings if the subscription is cancelled: monthly_cost * 12"
    )
    currency: str = Field(default="USD", description="Billing currency code (e.g. USD)")
    renewal_date: str | None = Field(
        default=None, description="Next contract renewal date from the expense event"
    )
    days_until_renewal: int | None = Field(
        default=None, description="Days left to cancel before the subscription auto-renews"
    )
    cost_data_available: bool = Field(
        default=True,
        description="False when no expense event matched the app and savings fell back to $0",
    )


class RiskAssessment(BaseModel):
    """Risk analysis and score computation (0-100).

    Factors without a data source yet are ``None`` and listed in ``unknown_factors``
    instead of being guessed.
    """

    risk_score: int = Field(
        ge=0,
        le=100,
        description="Composite risk score from 0 (safest) to 100 (highest risk)",
    )
    active_user_count: int = Field(ge=0, description="Seats with logins in the scan window")
    inactive_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Share of seats with no logins (US-1)"
    )
    connected_integrations_count: int | None = Field(
        default=None,
        ge=0,
        description="Automations linked to this tool; None until US-10 scans them",
    )
    data_age_days: int | None = Field(
        default=None, ge=0, description="Age of data in the system in days; None if unknown"
    )
    compliance_sensitivity: ComplianceSensitivity | None = Field(
        default=None,
        description="Data compliance rating (low, medium, high); None if unknown",
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description="Key drivers contributing to the risk score",
    )
    unknown_factors: list[str] = Field(
        default_factory=list,
        description="Risk inputs that had no data source and were not scored",
    )


class ConsolidationProposal(BaseModel):
    """Full consolidation proposal schema for an identified zombie SaaS application."""

    proposal_id: str = Field(
        default_factory=lambda: f"prop_{uuid4().hex[:12]}",
        description="Unique proposal identifier",
    )
    app_id: str = Field(..., description="Source application identifier from the IdP scan")
    app_name: str = Field(..., description="Human-readable application name (e.g., 'Trello')")
    target_app: str = Field(
        ..., description="Enterprise-standard application matched by the redundancy scan"
    )
    tenant_id: str = Field(..., description="Tenant / organization ID")
    savings: SavingsBreakdown = Field(..., description="Detailed savings calculation")
    risk: RiskAssessment = Field(..., description="Risk scoring and factor analysis")
    redundancy_score: int = Field(
        ge=0, le=100, description="Capability overlap with the target app (US-1)"
    )
    redundancy_rationale: str = Field(default="", description="Why the app is redundant (US-1)")
    dependencies: list[str] = Field(
        default_factory=list,
        description="List of detected dependencies (e.g., webhooks, rules, custom fields)",
    )
    recommendation: RecommendationType = Field(
        ...,
        description="Strategic recommendation for IT Ops review",
    )
    summary: str = Field(
        ...,
        description="Human-readable summary explanation of the proposal",
    )
    source_refs: dict[str, str | None] = Field(
        default_factory=dict,
        description="IDs of the source records: IdP scan (US-1) and expense event (US-2)",
    )
    status: str = Field(
        default="PENDING",
        description="Approval workflow state, updated by US-4 callbacks (not signed)",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 UTC creation timestamp",
    )
    expires_at: str = Field(
        default="",
        description="Approval must happen before this time (FR2.3: created_at + 7 days)",
    )
    signed_by: str = Field(
        default="system:auditor_agent",
        description="System identity that generated and signed the proposal",
    )
    signature: str | None = Field(
        default=None,
        description="HMAC-SHA256 hex digest over the canonical proposal JSON (audit trail)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional auxiliary attributes",
    )

    @model_validator(mode="after")
    def _default_expiry(self) -> "ConsolidationProposal":
        if not self.expires_at:
            created = datetime.fromisoformat(self.created_at)
            self.expires_at = (created + timedelta(days=PROPOSAL_TTL_DAYS)).isoformat()
        return self

    # Flat aliases read by the US-4 approval card / callbacks model.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def annual_savings(self) -> float:
        return self.savings.estimated_annual_savings

    @computed_field  # type: ignore[prop-decorator]
    @property
    def risk_score(self) -> int:
        return self.risk.risk_score

    @computed_field  # type: ignore[prop-decorator]
    @property
    def target_platform(self) -> str:
        return self.target_app

    @computed_field  # type: ignore[prop-decorator]
    @property
    def detected_dependencies(self) -> list[str]:
        return self.dependencies
