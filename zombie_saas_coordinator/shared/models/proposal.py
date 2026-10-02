"""Consolidation Proposal models and dummy fallback utilities."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ProposalStatus(StrEnum):
    PENDING = "PENDING"
    SIMULATING = "SIMULATING"
    APPROVED = "APPROVED"
    WHITELISTED = "WHITELISTED"
    EXPIRED = "EXPIRED"


class ConsolidationProposal(BaseModel):
    """Structured proposal representing redundant SaaS consolidation recommendations."""

    model_config = ConfigDict(extra="ignore")

    proposal_id: str = Field(..., description="Unique proposal identifier")
    app_id: str = Field(..., description="Unique redundant application identifier")
    app_name: str = Field(..., description="Display name of the redundant application")
    target_platform: str = Field(default="Asana", description="Target enterprise standard platform")
    annual_savings: float = Field(
        ..., description="Estimated annual licensing and maintenance savings in USD"
    )
    risk_score: int = Field(
        ..., ge=0, le=100, description="Risk score from 0 (lowest) to 100 (highest)"
    )
    recommendation: str = Field(..., description="Summary action recommendation")
    detected_dependencies: list[str] = Field(
        default_factory=list,
        description="List of detected automations, webhooks, or critical workflows",
    )
    status: ProposalStatus = Field(
        default=ProposalStatus.PENDING, description="Current workflow state"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(days=7),
        description="Proposal expiration timestamp (default: 7 days)",
    )


def get_dummy_proposal(proposal_id: str = "prop-trello-asana-001") -> ConsolidationProposal:
    """Provides a realistic dummy proposal for testing and WIP fallbacks.

    Useful while US-1 (IdP telemetry) and US-3 (proposal generator) are in progress.
    """
    return ConsolidationProposal(
        proposal_id=proposal_id,
        app_id="app-trello-engineering",
        app_name="Trello",
        target_platform="Asana",
        annual_savings=14400.0,
        risk_score=42,
        recommendation=(
            "Proceed to Full Consolidation: 65% inactive seats, "
            "equivalent board logic available in Asana."
        ),
        detected_dependencies=[
            "Zapier Zap #9812: Trello card created -> Slack notification",
            "Make Scenario #42: Trello due date alert -> Google Calendar",
            "Trello Power-Up: Custom Fields (Sprint Points, Priority Tag)",
        ],
        status=ProposalStatus.PENDING,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
