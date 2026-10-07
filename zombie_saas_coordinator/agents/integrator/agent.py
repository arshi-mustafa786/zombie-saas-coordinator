"""Integrator Agent — Automation Hub Dependency Scanning.

Responsibilities:
- US-10: Scan Zapier/Make for workflows dependent on target app
         (scan_zapier, scan_make, build_dependency_graph)
"""

import os

from google.adk.agents import Agent

from zombie_saas_coordinator.agents.integrator.tools import (
    build_dependency_graph,
    scan_make,
    scan_zapier,
)

integrator_agent = Agent(
    name="integrator_agent",
    model=os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    description=(
        "Scans automation hubs (Zapier, Make) for workflow dependencies "
        "on target SaaS applications and builds risk dependency graphs."
    ),
    instruction=(
        "You are the Integrator Agent. Your job:\n\n"
        "1. Use `scan_zapier` to find all Zapier zaps referencing the target app.\n"
        "2. Use `scan_make` to find all Make scenarios referencing the target app.\n"
        "3. Use `build_dependency_graph` to compile results into a risk graph.\n\n"
        "Flag critical workflows (daily syncs, customer-facing automations) "
        "and identify which automations will break if the app is decommissioned."
    ),
    tools=[scan_zapier, scan_make, build_dependency_graph],
)

# Alias for ADK loader compatibility
agent = integrator_agent
