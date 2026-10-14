"""Root Orchestrator Agent — Zombie SaaS Coordinator.

This is the top-level agent that delegates work to specialized sub-agents:
- auditor_agent:    Detects zombie SaaS and generates consolidation proposals
- architect_agent:  Validates semantic compatibility between source/target platforms
- integrator_agent: Scans automation hubs for dependency graphs

The root agent implements the HITL (Human-in-the-Loop) execution gate
and coordinates parallel execution of Architect + Integrator after approval.
"""

import os

from google.adk.agents import Agent

from zombie_saas_coordinator.agents.architect.agent import architect_agent
from zombie_saas_coordinator.agents.auditor.agent import auditor_agent
from zombie_saas_coordinator.agents.integrator.agent import integrator_agent
from zombie_saas_coordinator.shared.approvals.approvals import check_approval_status
from zombie_saas_coordinator.shared.quarantine.service import (
    check_disposal_eligibility,
    quarantine_source_data,
)
from zombie_saas_coordinator.shared.services.reconciliation import (
    execute_migration,
    reconcile_migration,
)

root_agent = Agent(
    name="zombie_saas_coordinator",
    model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    description=(
        "Root orchestrator for the Zombie SaaS Consolidator platform. "
        "Coordinates detection, validation, migration planning, automation dependency scanning, "
        "reconciliation, and fail-safe quarantine/disposal for redundant SaaS applications."
    ),
    instruction=(
        "You are the Zombie SaaS Coordinator, the root orchestrator of a "
        "multi-agent system that detects and consolidates redundant SaaS tools.\n\n"
        "## Workflow\n"
        "1. Delegate to the **auditor_agent** for zombie SaaS detection and "
        "consolidation proposal generation.\n"
        "2. After the auditor generates a proposal and sends an approval card, "
        "WAIT for human approval (HITL gate). Use `check_approval_status` to verify.\n"
        "3. Once approved, delegate to the **architect_agent** for semantic contract validation "
        "(US-6 behavioral contracts, US-7 schema diffing, and US-8 state-transition simulation).\n"
        "4. Also delegate to the **integrator_agent** to scan Zapier and Make for automation "
        "workflows that depend on the app (US-10). This is independent of step 3.\n"
        "5. Summarize the validation findings and the automation dependencies into a single "
        "migration readiness report.\n"
        "6. After a separate PERMISSION_TO_MIGRATE approval, use `execute_migration` and "
        "`reconcile_migration` to create cryptographic cutover evidence (US-11).\n"
        "7. After migration execution and cutover verification, ensure source data is placed "
        "into `SOURCE_QUARANTINED` via `quarantine_source_data` (US-12). Verifiable destruction "
        "is blocked until multi-signature DISPOSAL_APPROVED is verified via "
        "`check_disposal_eligibility` with no legal holds or exceptions.\n\n"
        "## CRITICAL RULES\n"
        "- NEVER proceed past step 2 without explicit human approval.\n"
        "- NEVER destroy source data without verified multi-signature DISPOSAL_APPROVED state.\n"
        "- NEVER modify data in external systems (Trello, Asana, Zapier, Make) — "
        "read-only analysis until verified.\n"
        "- ALL actions must be logged for compliance audit trail.\n"
    ),
    tools=[
        check_approval_status,
        execute_migration,
        reconcile_migration,
        check_disposal_eligibility,
        quarantine_source_data,
    ],
    sub_agents=[auditor_agent, architect_agent, integrator_agent],
)

# Alias for ADK loader compatibility
agent = root_agent
