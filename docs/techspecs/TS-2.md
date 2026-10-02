---
story_id: US-2
story_title: "Expense & Webhook Ingestion"
complexity: S
layers: [api, service, db]
depends_on: []
blocks: [US-3]
agent: auditor_agent
framework: Google ADK (google-adk)
---

## Story Summary
As a Finance Lead, I want the system to receive webhook notifications from expense systems when a new software subscription appears, so we catch shadow IT in real-time.

## Vertical Scope
This story is a complete vertical slice:
- **DB layer:** Firestore collection `expense_events`
- **Service layer:** ADK Tool functions (`validate_webhook`, `flag_subscription`) registered on the **Auditor Agent**
- **API layer:** Cloud Run endpoint `POST /webhooks/expense-notification` (HMAC-SHA256 authenticated)
- **UI layer:** N/A

## Agent Architecture (Google ADK)

This story adds **tool functions** to the same `auditor_agent` defined in US-1:

```python
def validate_webhook(payload: str, signature: str) -> dict:
    """Validates an incoming expense webhook by verifying its
    HMAC-SHA256 signature against the secret stored in Google
    Secret Manager. Returns validation status."""
    ...


def flag_subscription(event: dict) -> dict:
    """Analyzes an expense event against the enterprise-approved
    SaaS whitelist stored in Firestore. Flags unapproved recurring
    subscriptions and detects auto-renewal windows. Routes high-value
    subscriptions (>$500/month) for immediate Finance Lead review."""
    ...
```

These tools are added to the `auditor_agent.tools` list alongside the US-1 tools.

## Module Interface Contract (draft)
| Tool Function | Signature | Returns | Raises | Docstring |
|---------------|-----------|---------|--------|-----------|
| `validate_webhook` | `validate_webhook(payload: str, signature: str) -> dict` | `{"valid": bool}` | `InvalidSignatureError` | Validates HMAC-SHA256 webhook signature. |
| `flag_subscription` | `flag_subscription(event: dict) -> dict` | `{"status": str, "flagged": bool, "reason": str}` | `None` | Checks expense against whitelist. |

## Acceptance Criteria
- Exposes secure webhook endpoint on Cloud Run authenticated via HMAC-SHA256
- Accepts expense payloads (merchant name, amount, billing frequency, renewal date)
- Identifies unapproved recurring subscriptions by querying Firestore whitelist
- Detects auto-renewal windows and flags for cancellation opportunity
- Routes high-value subscriptions (>$500/month) directly to Finance Lead
- All webhook events immutably logged in Cloud Audit Logs

## Test Outline
- [ ] Happy path: Valid webhook received, parsed, flagged as unapproved, saved to Firestore.
- [ ] Edge case: Unknown merchant name — flagged with low confidence.
- [ ] Security: Invalid HMAC signature rejects request (403).
- [ ] Security: Malformed JSON payload returns 400.
- [ ] Error path: Firestore write timeout — returns 503, retryable.

## Files to Create or Modify
| Action   | File path                                    | Reason               |
|----------|----------------------------------------------|----------------------|
| MODIFY   | zombie_saas_coordinator/agents/auditor/tools.py | Add webhook tools   |
| CREATE   | zombie_saas_coordinator/shared/models/expense.py | Data models         |
| CREATE   | zombie_saas_coordinator/shared/auth/hmac_validator.py | HMAC validation  |
| CREATE   | tests/test_US2_expense.py                    | Tests                |

## Dependencies & Integration Points
- Root story — no upstream dependencies.
- Downstream: US-3 (Proposal Generation) reads flagged expenses.
- Webhook arrives from external expense platforms (Brex/Ramp/Expensify).
- Google Secret Manager stores the HMAC signing secret.
