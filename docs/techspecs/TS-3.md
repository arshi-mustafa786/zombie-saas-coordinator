---
story_id: US-3
story_title: "Auditor Agent – Consolidation Proposal Generation"
complexity: L
layers: [service, db, api]
depends_on: [US-1, US-2]
blocks: [US-4]
agent: auditor_agent
framework: Google ADK (google-adk)
---

## Story Summary
As an IT Ops Manager, I want the system to create a detailed consolidation proposal before any migration begins, so I understand the risk.

## Vertical Scope
This story is a complete vertical slice:
- **DB layer:** Firestore document `consolidation_proposals`; Cloud SQL for structured ROI metrics
- **Service layer:** ADK Tool function (`generate_proposal`) on the **Auditor Agent** using **Gemini Pro** for deep reasoning
- **API layer:** Cloud Run endpoint `GET /api/v1/proposals/{id}`
- **UI layer:** N/A

## Agent Architecture (Google ADK)

This is the **capstone tool** of the Auditor Agent. It aggregates data from US-1 and US-2 tools and uses Gemini Pro for analysis:

```python
def generate_proposal(app_id: str) -> dict:
    """Generates a comprehensive consolidation proposal for a flagged
    zombie SaaS application. Aggregates IdP telemetry data and expense
    events, then uses Gemini Pro to:
    1. Calculate estimated annual savings (seats × cost × months remaining)
    2. Compute risk score (0-100) based on active users, integrations,
       data age, and compliance sensitivity
    3. Summarize detected dependencies (Zapier webhooks, custom fields)
    4. Provide recommendation: Proceed / Manual Review / Ignore
    Returns the proposal as a structured JSON document stored in Firestore."""
    ...


def calculate_roi(app_id: str) -> dict:
    """Calculates the return on investment for consolidating a specific
    application. Queries Cloud SQL for seat cost data and billing history."""
    ...
```

The `auditor_agent` now has the full toolset: `[scan_idp_logs, calculate_redundancy, validate_webhook, flag_subscription, generate_proposal, calculate_roi]` — 6 tools, within the ≤7 deep module limit.

## Module Interface Contract (draft)
| Tool Function | Signature | Returns | Raises | Docstring |
|---------------|-----------|---------|--------|-----------|
| `generate_proposal` | `generate_proposal(app_id: str) -> dict` | `{"proposal": Proposal}` | `AppNotFoundError` | Generates full consolidation proposal using Gemini Pro. |
| `calculate_roi` | `calculate_roi(app_id: str) -> dict` | `{"savings": float, "months": int}` | `None` | Calculates estimated savings. |

## Acceptance Criteria
- Auditor Agent generates structured JSON proposal with redundant app identifier, target, and savings
- Calculates savings accurately using Cloud SQL billing data
- Generates risk score (0-100) using Gemini Pro reasoning
- Summarizes detected dependencies
- Provides recommendation (Proceed, Manual Review, Ignore)
- Proposal timestamped and signed for audit trail in Firestore

## Test Outline
- [ ] Happy path: Proposal generated with correct ROI and risk score, stored in Firestore.
- [ ] Edge case: App has missing cost data (fallback to $0 savings).
- [ ] Security: Accessing proposal without correct tenant ID (403).
- [ ] Security: Prompt injection in app metadata fields.
- [ ] Error path: Invalid app_id — tool returns error dict.

## Files to Create or Modify
| Action   | File path                                    | Reason               |
|----------|----------------------------------------------|----------------------|
| MODIFY   | zombie_saas_coordinator/agents/auditor/tools.py | Add proposal tools  |
| MODIFY   | zombie_saas_coordinator/agents/auditor/prompt.py | Update instructions |
| CREATE   | zombie_saas_coordinator/shared/models/proposal.py | Data models        |
| CREATE   | tests/test_US3_proposal.py                   | Tests                |

## Dependencies & Integration Points
- **US-1:** Reads flagged apps from `scan_idp_logs` results in Firestore.
- **US-2:** Reads flagged expenses from `flag_subscription` results in Firestore.
- Downstream: US-4 (Interactive Approval Card) receives the generated proposal.
