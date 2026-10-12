"""Script to create a fresh consolidation proposal in Firestore."""

import uuid
from datetime import UTC, datetime, timedelta

import dotenv

dotenv.load_dotenv()

from zombie_saas_coordinator.shared.db.firestore_client import get_firestore_client
from zombie_saas_coordinator.shared.models.proposal import (
    ConsolidationProposal,
    ProposalStatus,
    RecommendationType,
    RiskAssessment,
    SavingsBreakdown,
)


def create_fresh_proposal(app_name: str = "Trello", target_app: str = "Asana") -> ConsolidationProposal:
    unique_id = uuid.uuid4().hex[:8]
    proposal_id = f"prop-{app_name.lower()}-{unique_id}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=7)

    proposal = ConsolidationProposal(
        proposal_id=proposal_id,
        app_id=f"app_{app_name.lower()}_01",
        app_name=app_name,
        target_app=target_app,
        tenant_id="tenant-001",
        savings=SavingsBreakdown(
            seats=15,
            monthly_cost=675.0,
            cost_per_seat_monthly=45.0,
            estimated_annual_savings=8100.0,
        ),
        risk=RiskAssessment(
            risk_score=28,
            active_user_count=4,
            inactive_ratio=0.73,
            risk_factors=[
                "High inactivity ratio (73% of seats idle >60 days)",
                "Redundant capability with approved enterprise tool (Asana)",
            ],
        ),
        redundancy_score=85,
        dependencies=["Zapier Webhook #42", "Slack Channel Notifications"],
        recommendation=RecommendationType.PROCEED_CONSOLIDATION,
        summary=(
            f"Fresh consolidation proposal for {app_name}. Cancelling it saves an estimated "
            f"$8,100.00/year ($675.00/month). Risk score 28/100. Action: Proceed to Full Consolidation."
        ),
        status=ProposalStatus.PENDING,
        created_at=now,
        expires_at=expires_at,
    )

    fs = get_firestore_client()
    # Write fresh proposal to Firestore
    fs.collection("consolidation_proposals").document(proposal_id).set(
        proposal.model_dump(mode="json")
    )

    # Ensure approvals collection has no stale record for this proposal
    approval_ref = fs.collection("approvals").document(proposal_id)
    if approval_ref.get().exists:
        approval_ref.delete()

    return proposal


if __name__ == "__main__":
    p = create_fresh_proposal()
    print("=" * 65)
    print(" [+] FRESH CONSOLIDATION PROPOSAL CREATED")
    print("=" * 65)
    print(f" Proposal ID:    {p.proposal_id}")
    print(f" Status:         {p.status.value.upper()} (Ready for action / approval)")
    print(f" Target Apps:    {p.app_name} -> {p.target_app}")
    print(f" Annual Savings: ${p.savings.estimated_annual_savings:,.2f}")
    print(f" Risk Score:     {p.risk.risk_score}/100")
    print(f" Recommendation: {p.recommendation.value}")
    print(f" Expires At:     {p.expires_at.isoformat()}")
    print("=" * 65)
