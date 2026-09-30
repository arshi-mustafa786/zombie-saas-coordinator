---
story_id: US-6
story_title: "Behavioral Contract Extraction"
complexity: L
layers: [service, api, db]
depends_on: [US-5]
blocks: [US-7]
agent: architect_agent
framework: Google ADK (google-adk)
---

## Story Summary
As a Technical Lead, I want the system to automatically extract automation rules and behavioral logic from Trello so we can verify Asana can enforce them.

## Vertical Scope
This story is a complete vertical slice:
- **DB layer:** Firestore collection `behavioral_contracts`
- **Service layer:** ADK Tool function (`extract_trello_rules`) on the **Architect Agent** using Gemini Pro
- **API layer:** Cloud Run — invoked by root orchestrator after HITL gate passes
- **UI layer:** N/A

## Agent Architecture (Google ADK)

This story defines the **Architect Agent** and its first tool:

```python
from google.adk.agents import Agent

def extract_trello_rules(board_id: str) -> dict:
    """Connects to Trello API and extracts all automation rules,
    Butler commands, and Power-Up configurations from the specified
    board. For each automation, records:
    - Trigger condition (e.g., card status change, label added)
    - Action to execute (e.g., archive, move, notify)
    - Scope (all cards in board, or specific list)
    Also extracts custom fields, due dates, labels, and checklists.
    Returns a structured behavioral contract as a JSON document,
    stored in Firestore for audit trail."""
    ...

def parse_automation_rule(raw_rule: dict) -> dict:
    """Normalizes a raw Trello Butler/Power-Up rule into a
    canonical contract format: {trigger, action, scope, metadata}.
    Uses Gemini Pro to interpret natural-language rules."""
    ...

architect_agent = Agent(
    name="architect_agent",
    model="gemini-2.0-pro",
    description="Validates semantic compatibility between source and target SaaS platforms",
    instruction="You are the Architect Agent. Your job is to extract behavioral contracts "
                "from source systems (Trello), compare schemas with target systems (Asana), "
                "simulate state transitions, and detect semantic mismatches. "
                "Start by extracting rules with extract_trello_rules.",
    tools=[extract_trello_rules, parse_automation_rule],
)
```

## Module Interface Contract (draft)
| Tool Function | Signature | Returns | Raises | Docstring |
|---------------|-----------|---------|--------|-----------|
| `extract_trello_rules` | `extract_trello_rules(board_id: str) -> dict` | `{"contracts": list[Contract]}` | `ApiError` | Pulls automations from Trello API. |
| `parse_automation_rule` | `parse_automation_rule(raw_rule: dict) -> dict` | `{"trigger": str, "action": str, "scope": str}` | `ParseError` | Normalizes a raw rule into canonical format. |

## Acceptance Criteria
- Architect Agent connects to Trello API and parses all board configurations
- Extracts automation and Power-Up rules in structured format
- Records trigger conditions and actions
- Records custom fields, due dates, card labels, and checklists
- Exports behavioral contract as JSON in Firestore
- Logs all API calls and extracted rules to Cloud Audit Logs

## Test Outline
- [ ] Happy path: Successfully extracts standard Trello Butler rule.
- [ ] Edge case: Board with 0 automations — returns empty contract list.
- [ ] Security: Trello API token injection prevented.
- [ ] Security: Prompt injection in Trello card content fed to Gemini.
- [ ] Error path: Trello API returns 500 — tool returns error dict.

## Files to Create or Modify
| Action   | File path                                    | Reason               |
|----------|----------------------------------------------|----------------------|
| CREATE   | zombie_saas_coordinator/agents/architect/agent.py | ADK Agent definition |
| CREATE   | zombie_saas_coordinator/agents/architect/tools.py | Tool functions      |
| CREATE   | zombie_saas_coordinator/agents/architect/prompt.py | System instructions |
| CREATE   | zombie_saas_coordinator/agents/architect/__init__.py | Package export    |
| CREATE   | zombie_saas_coordinator/shared/integrations/trello.py | Trello API client |
| CREATE   | zombie_saas_coordinator/shared/db/firestore_client.py | Firestore client  |
| CREATE   | tests/test_US6_extractor.py                  | Tests                |

## Dependencies & Integration Points
- **US-5:** Blocked until HITL approval gate passes.
- Downstream: US-7 (Schema Diffing) reads the behavioral contracts.
- Trello API accessed via OAuth token stored in Secret Manager.
