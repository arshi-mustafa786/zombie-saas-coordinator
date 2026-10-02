"""Data models package.

Each model file is created by the user story that introduces it:
- US-1: telemetry.py
- US-2: expense.py
- US-3/US-4: proposal.py
- US-5: approval.py
"""

from zombie_saas_coordinator.shared.models.expense import ExpenseEvent, SubscriptionAssessment
from zombie_saas_coordinator.shared.models.proposal import (
    ConsolidationProposal,
    ProposalStatus,
    get_dummy_proposal,
)

__all__ = [
    "ConsolidationProposal",
    "ExpenseEvent",
    "ProposalStatus",
    "SubscriptionAssessment",
    "get_dummy_proposal",
]
