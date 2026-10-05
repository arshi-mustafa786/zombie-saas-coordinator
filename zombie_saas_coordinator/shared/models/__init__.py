"""Data models package.

Each model file is created by the user story that introduces it:
- US-1: telemetry.py
- US-2: expense.py
- US-3: proposal.py
- US-5: approval.py
"""

from zombie_saas_coordinator.shared.models.proposal import (
    ComplianceSensitivity,
    ConsolidationProposal,
    RecommendationType,
    RiskAssessment,
    SavingsBreakdown,
)

__all__ = [
    "ComplianceSensitivity",
    "ConsolidationProposal",
    "RecommendationType",
    "RiskAssessment",
    "SavingsBreakdown",
]

