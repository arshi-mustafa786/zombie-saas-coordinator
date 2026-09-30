---
story_id: US-1
story_title: "Scheduled Identity & Access Telemetry"
complexity: M
layers: [db, service, api]
depends_on: []
blocks: [US-3]
agent: auditor_agent
framework: Google ADK (google-adk)
---

## Story Summary
As an IT Operations Manager, I want the system to automatically scan IdP logs every 24–72 hours and flag applications with zero activity or redundant capabilities, so I don't have to manually hunt for zombie systems.

## Vertical Scope
This story is a complete vertical slice:
- **DB layer:** Cloud SQL table for `idp_telemetry` and `application_inventory`; Firestore session state for scan tracking
- **Service layer:** ADK Tool functions (`scan_idp_logs`, `calculate_redundancy`) registered on the **Auditor Agent**
- **API layer:** Cloud Run endpoint triggered by Cloud Scheduler `POST /api/v1/jobs/scan-idp`
- **UI layer:** N/A

## Agent Architecture (Google ADK)

This story contributes **tool functions** to the `auditor_agent`, defined using Google ADK:

```python
from google.adk.agents import Agent

# Tool functions (plain Python functions with docstrings)
def scan_idp_logs(tenant_id: str, days: int = 60) -> dict:
    """Fetches SAML/OIDC login events from the identity provider
    via Firebase Authentication federation. Returns a list of
    applications with their login activity over the specified period."""
    ...

def calculate_redundancy(apps: list[dict]) -> dict:
    """Analyzes application capabilities using Gemini Flash to detect
    functional overlap with enterprise-standard tools. Returns a list
    of flagged applications with redundancy confidence scores (0-100)."""
    ...

# Agent definition (composed in root orchestrator)
auditor_agent = Agent(
    name="auditor_agent",
    model="gemini-2.0-flash",
    description="Scans IdP telemetry and expense events to detect zombie SaaS applications",
    instruction="You are the Auditor Agent. Your job is to scan identity provider logs, "
                "detect applications with low or zero usage, and flag redundant tools. "
                "Use scan_idp_logs to fetch telemetry and calculate_redundancy to classify apps.",
    tools=[scan_idp_logs, calculate_redundancy],
)
```

## Module Interface Contract (draft)
| Tool Function | Signature | Returns | Raises | Docstring |
|---------------|-----------|---------|--------|-----------|
| `scan_idp_logs` | `scan_idp_logs(tenant_id: str, days: int) -> dict` | `{"status": str, "apps": list}` | `IdpAuthError` | Fetches login events from IdP via Firebase Auth. |
| `calculate_redundancy` | `calculate_redundancy(apps: list[dict]) -> dict` | `{"status": str, "flagged": list}` | `None` | Uses Gemini to detect capability overlap. |

## Acceptance Criteria
- System connects to identity providers using Firebase Authentication
- Cron-based Auditor Agent executes on configurable schedule (Cloud Scheduler → Cloud Run)
- Flags application when ≥60% of assigned seats show zero logins over 60+ days
- Detects capability redundancy using Gemini Flash for semantic tag matching
- Generates structured JSON payload stored in Firestore
- Logs to Cloud Audit Logs

## Test Outline
- [ ] Happy path: Scheduler hits endpoint, agent invoked, logs fetched, redundant apps saved to Firestore.
- [ ] Edge case: 0 apps returned from IdP — agent returns empty result gracefully.
- [ ] Security: Missing Firebase Auth token rejects request (401).
- [ ] Security: SQL injection in tenant_id parameter.
- [ ] Error path: IdP rate limit exceeded — tool returns error dict, agent retries.

## Files to Create or Modify
| Action   | File path                                    | Reason               |
|----------|----------------------------------------------|----------------------|
| CREATE   | zombie_saas_coordinator/agents/auditor/tools.py | Tool functions      |
| CREATE   | zombie_saas_coordinator/agents/auditor/agent.py | ADK Agent definition |
| CREATE   | zombie_saas_coordinator/agents/auditor/prompt.py | System instructions |
| CREATE   | zombie_saas_coordinator/agents/auditor/__init__.py | Package export    |
| CREATE   | zombie_saas_coordinator/shared/db/cloudsql_client.py | DB access layer |
| CREATE   | zombie_saas_coordinator/shared/models/telemetry.py | Data models       |
| CREATE   | tests/test_US1_scanner.py                    | Tests                |

## Dependencies & Integration Points
- Root story — no upstream dependencies.
- Downstream: US-3 (Proposal Generation) reads the flagged apps produced by this tool.
- Cloud Scheduler triggers this agent via Cloud Run HTTP endpoint.
- Firebase Authentication validates the IdP federation tokens.
- Firestore stores scan results and session state.
