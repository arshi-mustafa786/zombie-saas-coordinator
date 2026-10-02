---
story_id: US-4
story_title: "Interactive Approval Card"
complexity: M
layers: [api, service, ui]
depends_on: [US-3]
blocks: [US-5]
agent: auditor_agent (callback tool)
framework: Google ADK (google-adk)
status: DONE
---

## Story Summary
As an IT Ops Manager, I want to receive an interactive notification (Slack, Teams, or email) that lets me review the consolidation proposal and take action without leaving my communication tool.

## Vertical Scope
This story is a complete vertical slice:
- **DB layer:** N/A (Reads proposals from Firestore)
- **Service layer:** ADK Tool function (`send_approval_card`) on the **Auditor Agent** + Cloud Run callback handler
- **API layer:** Cloud Run endpoints `POST /api/v1/notifications/send` and `POST /api/v1/callbacks/approval`
- **UI layer:** Firebase Hosting dashboard; Slack/Teams Block Kit interactive cards

## Agent Architecture (Google ADK)

The Auditor Agent dispatches a notification as part of its proposal workflow. The callback handler is a plain Cloud Run endpoint (not an agent tool) because it processes external webhook events:

```python
# Tool added to auditor_agent
def send_approval_card(proposal_id: str, channel: str) -> dict:
    """Dispatches an interactive approval card to the specified
    Slack/Teams channel for a given consolidation proposal.
    The card includes: summary, target platform, estimated savings,
    dependencies, and three action buttons:
    [Simulate Migration], [Approve Full Consolidation], [Ignore/Whitelist].
    Returns delivery status and message ID."""
    ...


# Cloud Run callback handler (NOT an agent tool — external webhook)
# Registered as a Flask/FastAPI route on Cloud Run
@app.post("/api/v1/callbacks/approval")
async def handle_approval_callback(payload: ApprovalCallbackPayload):
    """Processes button clicks from Slack/Teams interactive cards.
    Validates the callback token, records the approver identity
    (Firebase Auth SSO context), and updates the proposal status
    in Firestore. Emits Cloud Audit Log entry."""
    ...
```

## Module Interface Contract (draft)
| Component | Signature | Returns | Raises | Docstring |
|-----------|-----------|---------|--------|-----------|
| `send_approval_card` (tool) | `send_approval_card(proposal_id: str, channel: str) -> dict` | `{"sent": bool, "message_id": str}` | `DeliveryError` | Dispatches interactive card. |
| `handle_approval_callback` (endpoint) | `POST /api/v1/callbacks/approval` | `200 OK` | `403 InvalidToken` | Processes Slack/Teams button clicks. |

## Acceptance Criteria
- Auditor Agent sends formatted message card to designated Slack/Teams channel
- Card displays summary, target platform, estimated savings, and dependencies
- Three interactive buttons: [Simulate Migration], [Approve Full Consolidation], [Ignore/Whitelist]
- [Simulate Migration] triggers dry-run without permanent changes
- [Approve Full Consolidation] records approver identity via Firebase Auth SSO
- All user interactions logged to Cloud Audit Logs with full context

## Test Outline
- [x] Happy path: Card generated correctly and dispatched to Slack.
- [x] Happy path: Button click callback processes approval and updates Firestore.
- [x] Edge case: User clicks button on expired proposal.
- [x] Security: Forged callback payload with invalid token rejected (403).
- [x] Security: SSRF via manipulated channel URL.
- [x] Error path: Slack API is down — tool returns error dict.

## Files to Create or Modify
| Action   | File path                                    | Reason               |
|----------|----------------------------------------------|----------------------|
| MODIFY   | zombie_saas_coordinator/agents/auditor/tools.py | Add notification tool |
| CREATE   | zombie_saas_coordinator/api/callbacks.py      | Callback endpoint    |
| CREATE   | zombie_saas_coordinator/shared/integrations/slack.py | Slack client      |
| CREATE   | tests/test_US4_notifications.py              | Tests                |

## Dependencies & Integration Points
- **US-3:** Reads the generated proposal from Firestore.
- Downstream: US-5 (HITL Execution Gate) reads the approval status.
- External: Slack/Teams webhook APIs.
