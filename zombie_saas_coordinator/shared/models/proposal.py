"""Consolidation Proposal Data Models (US-3).

Defines strongly-typed Pydantic schemas for consolidation proposals,
ROI savings calculations, risk evaluations, and migration recommendations.

Proposals are signed for the audit trail, so the models are frozen and
reject internally inconsistent data instead of storing it.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from zombie_saas_coordinator.shared.constants import (
    MAX_RATIONALE_LENGTH,
    MAX_SUMMARY_LENGTH,
    MONEY_TOLERANCE,
    PROPOSAL_TTL_DAYS,
    US4_PROPOSAL_ALIASES,
)


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


class ProposalStatus(StrEnum):
    """Approval workflow states; values match the US-4 callbacks."""
    PENDING = "PENDING"
    SIMULATING = "SIMULATING"
    APPROVED = "APPROVED"
    WHITELISTED = "WHITELISTED"
    EXPIRED = "EXPIRED"


class SavingsBreakdown(BaseModel):
    """ROI derived from IdP seat counts (US-1) and corporate card spend (US-2)."""

    model_config = ConfigDict(frozen=True)

    seats: int = Field(ge=0, description="Total licensed seats reported by the IdP scan")
    monthly_cost: float = Field(
        ge=0.0, description="Monthly-equivalent subscription spend from the expense event"
    )
    cost_per_seat_monthly: float = Field(ge=0.0, description="monthly_cost / seats")
    estimated_annual_savings: float = Field(
        ge=0.0, description="Annual savings if the subscription is cancelled: monthly_cost * 12"
    )
    currency: str = Field(
        default="USD", min_length=3, max_length=3, description="ISO currency code (e.g. USD)"
    )
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

    @field_validator("monthly_cost", "cost_per_seat_monthly", "estimated_annual_savings")
    @classmethod
    def _round_to_cents(cls, value: float) -> float:
        return round(value, 2)

    @model_validator(mode="after")
    def _amounts_are_consistent(self) -> "SavingsBreakdown":
        if not self.cost_data_available:
            if self.monthly_cost or self.cost_per_seat_monthly or self.estimated_annual_savings:
                raise ValueError("cost data is unavailable, so all amounts must be 0")
            return self

        expected_annual = self.monthly_cost * 12
        if abs(self.estimated_annual_savings - expected_annual) > MONEY_TOLERANCE:
            raise ValueError(
                f"estimated_annual_savings {self.estimated_annual_savings} must equal "
                f"monthly_cost * 12 ({expected_annual:.2f})"
            )
        expected_per_seat = self.monthly_cost / self.seats if self.seats else 0.0
        if abs(self.cost_per_seat_monthly - expected_per_seat) > MONEY_TOLERANCE:
            raise ValueError(
                f"cost_per_seat_monthly {self.cost_per_seat_monthly} must equal "
                f"monthly_cost / seats ({expected_per_seat:.2f})"
            )
        return self


class RiskAssessment(BaseModel):
    """Risk analysis and score computation (0-100).

    Factors without a data source yet are ``None`` and listed in ``unknown_factors``
    instead of being guessed.
    """

    model_config = ConfigDict(frozen=True)

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
    """Full consolidation proposal schema for an identified zombie SaaS application.

    Unknown fields are ignored rather than rejected because US-4 adds
    ``updated_at`` / ``action_*`` to the same Firestore document.
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    proposal_id: str = Field(
        default_factory=lambda: f"prop_{uuid4().hex[:12]}",
        min_length=1,
        description="Unique proposal identifier",
    )
    app_id: str = Field(
        ..., min_length=1, description="Source application identifier from the IdP scan"
    )
    app_name: str = Field(
        ..., min_length=1, description="Human-readable application name (e.g., 'Trello')"
    )
    target_app: str = Field(
        ...,
        min_length=1,
        description="Enterprise-standard application matched by the redundancy scan",
    )
    tenant_id: str = Field(..., min_length=1, description="Tenant / organization ID")
    savings: SavingsBreakdown = Field(..., description="Detailed savings calculation")
    risk: RiskAssessment = Field(..., description="Risk scoring and factor analysis")
    redundancy_score: int = Field(
        ge=0, le=100, description="Capability overlap with the target app (US-1)"
    )
    redundancy_rationale: str = Field(
        default="",
        max_length=MAX_RATIONALE_LENGTH,
        description="Why the app is redundant (US-1)",
    )
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
        min_length=1,
        max_length=MAX_SUMMARY_LENGTH,
        description="Human-readable summary explanation of the proposal",
    )
    source_refs: dict[str, str | None] = Field(
        default_factory=dict,
        description="IDs of the source records: IdP scan (US-1) and expense event (US-2)",
    )
    status: ProposalStatus = Field(
        default=ProposalStatus.PENDING,
        description="Approval workflow state, updated by US-4 callbacks (not signed)",
    )
    created_at: AwareDatetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware creation timestamp",
    )
    expires_at: AwareDatetime | None = Field(
        default=None,
        description="Approval deadline (FR2.3); defaults to created_at + 7 days",
    )
    signed_by: str = Field(
        default="system:auditor_agent",
        min_length=1,
        description="System identity that generated and signed the proposal",
    )
    signature: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="HMAC-SHA256 hex digest over the canonical proposal JSON (audit trail)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional auxiliary attributes",
    )

    @model_validator(mode="before")
    @classmethod
    def _us4_aliases_match_nested_values(cls, data: Any) -> Any:
        """A stored document whose flat US-4 fields disagree with the nested data is corrupt."""
        if not isinstance(data, dict):
            return data
        for alias, path in US4_PROPOSAL_ALIASES.items():
            if alias not in data:
                continue
            nested: Any = data
            for key in path:
                nested = nested.get(key) if isinstance(nested, dict) else getattr(nested, key, None)
            if data[alias] != nested:
                raise ValueError(
                    f"{alias}={data[alias]!r} does not match {'.'.join(path)}={nested!r}"
                )
        return data

    @model_validator(mode="after")
    def _expiry_after_creation(self) -> "ConsolidationProposal":
        if self.expires_at is None:
            # The model is frozen; this is the one place the default expiry is filled in.
            expiry = self.created_at + timedelta(days=PROPOSAL_TTL_DAYS)
            object.__setattr__(self, "expires_at", expiry)
        elif self.expires_at <= self.created_at:
            raise ValueError("expires_at must be later than created_at")
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
