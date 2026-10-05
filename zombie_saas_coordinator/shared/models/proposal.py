"""Consolidation Proposal Data Models (US-3).

Defines strongly-typed Pydantic schemas for consolidation proposals,
ROI savings calculations, risk evaluations, and migration recommendations.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


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
    """Calculated ROI and cost savings metrics."""

    seats: int = Field(ge=0, description="Total licensed seats for this application")
    cost_per_seat_monthly: float = Field(ge=0.0, description="Monthly cost per seat in currency")
    months_remaining: int = Field(ge=0, description="Months remaining in current billing cycle")
    estimated_annual_savings: float = Field(
        ge=0.0,
        description="Calculated annual savings: seats * cost_per_seat_monthly * months_remaining",
    )
    currency: str = Field(default="USD", description="Billing currency code (e.g. USD)")
    cost_data_available: bool = Field(
        default=True,
        description="False when billing data was missing and savings fell back to $0",
    )


class RiskAssessment(BaseModel):
    """Risk analysis and score computation (0-100)."""

    risk_score: int = Field(
        ge=0,
        le=100,
        description="Composite risk score from 0 (safest) to 100 (highest risk)",
    )
    active_user_count: int = Field(ge=0, description="Number of active users in last 60 days")
    connected_integrations_count: int = Field(
        default=0,
        ge=0,
        description="Number of active automations / zaps linked to this tool",
    )
    data_age_days: int = Field(default=0, ge=0, description="Age of data in the system in days")
    compliance_sensitivity: ComplianceSensitivity = Field(
        default=ComplianceSensitivity.LOW,
        description="Data compliance rating (low, medium, high)",
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description="Key drivers contributing to the risk score",
    )


class ConsolidationProposal(BaseModel):
    """Full consolidation proposal schema for an identified zombie SaaS application."""

    proposal_id: str = Field(
        default_factory=lambda: f"prop_{uuid4().hex[:12]}",
        description="Unique proposal identifier",
    )
    app_id: str = Field(..., description="Source application identifier (e.g., 'trello')")
    app_name: str = Field(..., description="Human-readable application name (e.g., 'Trello')")
    target_app: str = Field(
        default="Asana",
        description="Target enterprise-standard application for migration",
    )
    tenant_id: str = Field(default="default-tenant", description="Tenant / organization ID")
    savings: SavingsBreakdown = Field(..., description="Detailed savings calculation")
    risk: RiskAssessment = Field(..., description="Risk scoring and factor analysis")
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
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 UTC creation timestamp",
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
