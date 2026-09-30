"""Architect Agent — Semantic Contract Validation.

Responsibilities:
- US-6: Extract behavioral contracts from Trello (extract_trello_rules, parse_automation_rule)
- US-7: Diff schemas between Trello and Asana (diff_schemas, classify_mapping)
- US-8: Simulate state transitions (simulate_transition)
- US-9: Detect mismatches and generate remediations (generate_remediation)
"""

from google.adk.agents import Agent

from zombie_saas_coordinator.agents.architect.tools import (
    classify_mapping,
    # US-7 tools
    diff_schemas,
    # US-6 tools
    extract_trello_rules,
    # US-9 tools
    generate_remediation,
    parse_automation_rule,
    # US-8 tools
    simulate_transition,
)

architect_agent = Agent(
    name="architect_agent",
    model="gemini-3.5-flash",
    description=(
        "Validates semantic compatibility between source (Trello) and target "
        "(Asana) SaaS platforms by extracting behavioral contracts, diffing "
        "schemas, simulating state transitions, and generating remediation "
        "hypotheses for incompatible behaviors."
    ),
    instruction=(
        "You are the Architect Agent. Your validation pipeline:\n\n"
        "1. **Extract**: Use `extract_trello_rules` to pull automation rules "
        "and `parse_automation_rule` to normalize them into canonical format.\n"
        "2. **Compare**: Use `diff_schemas` to compare Trello and Asana data "
        "models and `classify_mapping` to rate each field mapping.\n"
        "3. **Simulate**: Use `simulate_transition` to verify behavioral "
        "equivalence for each automation contract.\n"
        "4. **Remediate**: Use `generate_remediation` to propose fixes for "
        "any incompatible behaviors.\n\n"
        "Execute these steps IN ORDER. Store all results in Firestore."
    ),
    tools=[
        extract_trello_rules,
        parse_automation_rule,
        diff_schemas,
        classify_mapping,
        simulate_transition,
        generate_remediation,
    ],
)

# Alias for ADK loader compatibility
agent = architect_agent

