---
story_id: US-5
module_name: hitl_execution_gate
layers: [service, db, api]
ancestor_stories: [US-4]
parent_techspec: docs/techspecs/TS-5.md
---

# US-5: 3-Tier HITL Execution Gate Specification

## Capabilities
- Enforce three distinct authorization gates: Permission to Investigate, Permission to Migrate, and Permission to Dispose.
- Restrict root orchestrator delegation: downstream execution (Architect / Integrator agents) is blocked until human authorization is verified.
- Verify Firebase Authentication ID tokens, extracting SSO user claims (UID, email, and role claims: `ciso`, `it_ops`, `admin`).
- Enforce RBAC custom claims, rejecting tokens without adequate permissions with HTTP 403 Forbidden.
- Enforce strict 7-day TTL window on approvals, marking records expired once the timestamp exceeds 7 days.
- Provide a `revoke_approval` tool and API endpoint to halt any in-progress or authorized proposal, recording reason and identity.
- Persist approval records in Cloud SQL relational storage and Firestore state for cross-agent coordination.
- Immutably log all authorization, revocation, and expiry checks to Cloud Audit Logs.

## Acceptance Criteria
- AC-5.1: System enforces three distinct authorization gates: Permission to Investigate, Permission to Migrate, Permission to Dispose.
- AC-5.2: Root orchestrator does NOT delegate to Architect/Integrator agents without approval.
- AC-5.3: Approval is tied to authenticated SSO identity verified via Firebase Authentication with custom claim validation.
- AC-5.4: Approval expires after 7 days; re-issue required if not completed in window.
- AC-5.5: System can be halted at any stage via `revoke_approval` tool.
- AC-5.6: All halts and authorizations are logged with reason and authorizing identity in Cloud Audit Logs.

## Integration Points
- Ancestor US-4: Builds on interactive approval cards and callback tracking; verifies authoritative approval records in Firestore and Cloud SQL.
- Root Orchestrator (`zombie_saas_coordinator/agent.py`): Integrates `check_approval_status` and `revoke_approval` tools directly into agent decision loop.
- Downstream US-6 (Behavioral Contract Extraction) and US-10 (Automation Hub Scanning): Downstream agents depend on approved status.

## Data Contracts
- `ApprovalGateType`: Literal / Enum (`PERMISSION_TO_INVESTIGATE`, `PERMISSION_TO_MIGRATE`, `PERMISSION_TO_DISPOSE`).
- `ApprovalRecord`:
  - `proposal_id`: str
  - `gate_type`: ApprovalGateType
  - `approved`: bool
  - `approver_id`: str
  - `approver_email`: str | None
  - `roles`: list[str]
  - `approved_at`: datetime
  - `expires_at`: datetime (7-day TTL)
  - `revoked`: bool
  - `revoked_at`: datetime | None
  - `revoked_by`: str | None
  - `revoke_reason`: str | None
- `AuthorizeProposalRequest`:
  - `firebase_token`: str
  - `gate_type`: ApprovalGateType
  - `notes`: str | None
- `RevokeApprovalRequest`:
  - `firebase_token`: str
  - `reason`: str

## Out of Scope
- Automated extraction of Trello automation logic (US-6).
- Zapier/Make automation hub scans (US-10).
- Multi-signature cryptographic deletion certificates (US-12).
