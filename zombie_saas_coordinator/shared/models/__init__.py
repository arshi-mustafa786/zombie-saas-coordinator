"""Data models package.

Each model file is created by the user story that introduces it:
- US-1: telemetry.py
- US-2: expense.py
- US-3/US-4: proposal.py
- US-5: approval.py
"""

from zombie_saas_coordinator.shared.models.approval import (
    ApprovalGateType,
    ApprovalRecord,
    ApprovalStatusResponse,
    AuthorizeProposalRequest,
    RevokeApprovalRequest,
)
from zombie_saas_coordinator.shared.models.expense import ExpenseEvent, SubscriptionAssessment
from zombie_saas_coordinator.shared.models.proposal import (
    ComplianceSensitivity,
    ConsolidationProposal,
    ProposalStatus,
    RecommendationType,
    RiskAssessment,
    SavingsBreakdown,
)
from zombie_saas_coordinator.shared.models.telemetry import (
    AppTelemetry,
    IdpAuthError,
    IdPScanRequest,
    IdPScanResponse,
    RedundancyAssessment,
)

__all__ = [
    "AppTelemetry",
    "IdPScanRequest",
    "IdPScanResponse",
    "IdpAuthError",
    "RedundancyAssessment",
    "ComplianceSensitivity",
    "ConsolidationProposal",
    "ProposalStatus",
    "RecommendationType",
    "RiskAssessment",
    "SavingsBreakdown",
    "ExpenseEvent",
    "SubscriptionAssessment",
    "ApprovalGateType",
    "ApprovalRecord",
    "ApprovalStatusResponse",
    "AuthorizeProposalRequest",
    "RevokeApprovalRequest",
]
