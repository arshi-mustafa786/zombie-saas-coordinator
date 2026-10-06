---
story_id: US-5
story_title: "3-Tier HITL Approval Gates"
complexity: M
layers: [service, db, api]
depends_on: [US-4]
blocks: [US-6, US-10]
agent: root orchestrator (zombie_saas_coordinator)
framework: Google ADK (google-adk)
status: DONE
---

## Story Summary
As a CISO, I want distinct, mandatory human approval gates for investigation, migration, and destruction, so we maintain accountability.

## Vertical Scope
This story is a complete vertical slice:
- **DB layer:** Cloud SQL table `approvals`; Firestore session state for approval tracking
- **Service layer:** ADK **Human-in-the-Loop (HITL) pattern** using session state to gate agent execution
- **API layer:** Cloud Run endpoint `POST /api/v1/approvals/{proposal_id}/authorize`
- **UI layer:** N/A (approval happens via Slack/Teams card or Firebase Hosting dashboard)

## Agent Architecture (Google ADK)

This story implements the **ADK HITL pattern** — the root orchestrator agent pauses execution and waits for human input before delegating to downstream agents. ADK supports this natively via session state:

```python
from google.adk.agents import Agent
from google.adk.sessions import FirestoreSessionService

# Session service backed by Firestore for persistence
session_service = FirestoreSessionService(
    project_id="zombie-saas-coordinator",
    collection="agent_sessions",
)


# Tool that checks approval status before proceeding
def check_approval_status(proposal_id: str, required_state: str) -> dict:
    """Checks whether a consolidation proposal has been approved
    by an authorized human (CISO or IT Ops). Reads approval status
    from Cloud SQL. Returns approval state, approver identity,
    timestamp, and whether the 7-day expiry window has elapsed.
    The root orchestrator will NOT delegate to Architect or Integrator
    agents until this tool returns {"approved": true}."""
    ...


def revoke_approval(proposal_id: str, reason: str) -> dict:
    """Revokes a previously granted approval. Updates Cloud SQL
    and Firestore session state. Halts any in-progress migration
    pipeline. Logs the halt reason and revoking identity to
    Cloud Audit Logs."""
    ...


# Cloud Run endpoint for human authorization
@app.post("/api/v1/approvals/{proposal_id}/authorize")
async def authorize_proposal(proposal_id: str, firebase_token: str):
    """Validates Firebase Auth token, verifies the user has
    CISO/IT-Ops claims, and records the approval in Cloud SQL.
    Sets a 7-day TTL on the approval record."""
    ...
```

## Module Interface Contract (draft)
| Component | Signature | Returns | Raises | Docstring |
|-----------|-----------|---------|--------|-----------|
| `check_approval_status` (tool) | `check_approval_status(proposal_id: str) -> dict` | `{"approved": bool, "approver": str, "expires_at": str}` | `None` | Checks if human approved this proposal. |
| `revoke_approval` (tool) | `revoke_approval(proposal_id: str, reason: str) -> dict` | `{"revoked": bool}` | `UnauthorizedError` | Halts a running or pending migration. |
| `authorize_proposal` (endpoint) | `POST /api/v1/approvals/{id}/authorize` | `200 OK` | `401/403` | Records human approval via Firebase Auth. |

## Acceptance Criteria
- System enforces three distinct authorization gates: Permission to Investigate, Permission to Migrate, Permission to Dispose
- Root orchestrator does NOT delegate to Architect/Integrator agents without approval
- Approval is tied to authenticated SSO identity verified via Firebase Authentication
- Approval expires after 7 days; re-issue required if not completed in window
- System can be halted at any stage via `revoke_approval` tool
- All halts logged with reason and authorizing identity in Cloud Audit Logs

## Test Outline
- [ ] Happy path: Valid Firebase token grants approval, agent proceeds.
- [ ] Edge case: Approval expires exactly at 7 days — `check_approval_status` returns expired.
- [ ] Security: Token lacks admin/CISO custom claims (403).
- [ ] Security: Replay attack with previously used approval token.
- [ ] Error path: Attempting to authorize an already completed migration.

## Files to Create or Modify
| Action   | File path                                    | Reason               |
|----------|----------------------------------------------|----------------------|
| CREATE   | zombie_saas_coordinator/api/approvals.py     | Authorization endpoint |
| CREATE   | zombie_saas_coordinator/shared/models/approval.py | Data models       |
| CREATE   | zombie_saas_coordinator/shared/auth/firebase_auth.py | Firebase Auth utils |
| MODIFY   | zombie_saas_coordinator/agent.py             | Add HITL gate to root orchestrator |
| CREATE   | tests/test_US5_approvals.py                  | Tests                |

## Dependencies & Integration Points
- **US-4:** Reads approval callback results from Firestore.
- Downstream: US-6 (Behavioral Contract Extraction) and US-10 (Automation Hub Scanning) are blocked until this gate passes.
- Firebase Authentication verifies the user's identity and custom claims.
- Firestore `FirestoreSessionService` persists agent session state across invocations.
