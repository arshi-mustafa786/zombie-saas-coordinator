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
    scan_idp_logs,
)

auditor_agent = Agent(
    name="auditor_agent",
    model="gemini-3.5-flash",
    description=(
        "Scans IdP telemetry to detect zombie SaaS applications and flag "
        "redundant tools based on inactivity and overlap with enterprise standards."
    ),
    instruction=(
        "You are the Auditor Agent. Your responsibilities:\n\n"
        "1. Use `scan_idp_logs` to fetch identity provider telemetry for a tenant.\n"
        "2. Use `calculate_redundancy` to identify apps with high inactivity and "
        "overlapping capability tags.\n"
        "3. Keep the findings in a structured format suitable for downstream "
        "proposal generation and review.\n\n"
        "Always log your reasoning and results for audit compliance."
    ),
    tools=[
        scan_idp_logs,
        calculate_redundancy,
    ],
)

# Alias for ADK loader compatibility
agent = auditor_agent

