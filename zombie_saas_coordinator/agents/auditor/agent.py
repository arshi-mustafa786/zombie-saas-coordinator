"""Auditor Agent — Zombie SaaS Detection & Proposal Generation.

Responsibilities:
- US-1: Scan IdP logs for inactive applications (scan_idp_logs, calculate_redundancy)
- US-2: Ingest expense webhooks for shadow IT (validate_webhook, flag_subscription)
- US-3: Generate consolidation proposals (generate_proposal, calculate_roi)
- US-4: Send interactive approval cards (send_approval_card)
"""

import os

from google.adk.agents import Agent

from zombie_saas_coordinator.agents.auditor.prompt import AUDITOR_SYSTEM_INSTRUCTION
from zombie_saas_coordinator.agents.auditor.tools import (
    calculate_redundancy,
    calculate_roi,
    flag_subscription,
    generate_proposal,
    scan_idp_logs,
    send_approval_card,
    validate_webhook,
)

auditor_agent = Agent(
    name="auditor_agent",
    model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    description=(
        "Scans IdP telemetry and expense events to detect zombie SaaS applications, "
        "generates consolidation proposals with ROI analysis, and dispatches "
        "interactive approval cards to IT Ops."
    ),
    instruction=AUDITOR_SYSTEM_INSTRUCTION,
    tools=[
        scan_idp_logs,
        calculate_redundancy,
        validate_webhook,
        flag_subscription,
        generate_proposal,
        calculate_roi,
        send_approval_card,
    ],
)


# Alias for ADK loader compatibility
agent = auditor_agent
