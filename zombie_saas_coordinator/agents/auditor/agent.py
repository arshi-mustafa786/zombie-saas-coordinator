"""Auditor Agent — Zombie SaaS Detection & Proposal Generation.

Responsibilities:
- US-1: Scan IdP logs for inactive applications (scan_idp_logs, calculate_redundancy)
- US-2: Ingest expense webhooks for shadow IT (validate_webhook, flag_subscription)
- US-3: Generate consolidation proposals (generate_proposal, calculate_roi)
- US-4: Send interactive approval cards (send_approval_card)
"""

from google.adk.agents import Agent

from zombie_saas_coordinator.agents.auditor.tools import (
    calculate_redundancy,
    calculate_roi,
    flag_subscription,
    # US-3 tools
    generate_proposal,
    # US-1 tools
    scan_idp_logs,
    # US-4 tools
    send_approval_card,
    # US-2 tools
    validate_webhook,
)

auditor_agent = Agent(
    name="auditor_agent",
    model="gemini-3.5-flash",
    description=(
        "Scans IdP telemetry and expense events to detect zombie SaaS applications, "
        "generates consolidation proposals with ROI analysis, and dispatches "
        "interactive approval cards to IT Ops."
    ),
    instruction=(
        "You are the Auditor Agent. Your responsibilities:\n\n"
        "1. **Detection**: Use `scan_idp_logs` to fetch identity provider telemetry "
        "and `calculate_redundancy` to identify overlapping SaaS tools.\n"
        "2. **Expense Monitoring**: Use `validate_webhook` and `flag_subscription` "
        "to process incoming expense webhook events.\n"
        "3. **Proposal Generation**: Use `generate_proposal` and `calculate_roi` "
        "to create a comprehensive consolidation proposal with risk scoring.\n"
        "4. **Notification**: Use `send_approval_card` to dispatch an interactive "
        "approval card to the IT Ops Slack/Teams channel.\n\n"
        "Always log your reasoning and results for audit compliance."
    ),
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
