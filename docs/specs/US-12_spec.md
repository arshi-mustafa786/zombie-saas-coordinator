---
story_id: US-12
module_name: fail_safe_quarantine_disposal
layers: [service, db, api]
ancestor_stories: [US-5, US-11]
parent_techspec: docs/techspecs/TS-12.md
---

# US-12: Fail-Safe Quarantine and Disposal Specification

## Capabilities
- Enforce default post-migration quarantine state: Once migration completes, source data is automatically designated as `SOURCE_QUARANTINED` for a configurable retention window (default 90 days).
- Enforce pre-disposal compliance guards: Destruction is strictly blocked if:
  1. Any validation exceptions from migration/reconciliation remain unresolved.
  2. A legal hold is active on the source data.
  3. Migration is incomplete or unverified.
- Implement multi-signature authorization: Destruction requires separate, multi-signature approval (`DISPOSAL_APPROVED`) requiring at least two distinct authorized SSO signers with security/compliance/CISO roles.
- Prevent duplicate signing: The same user cannot sign more than once to satisfy the multi-signature quorum.
- Cryptographically verifiable destruction execution: On execution, generates a verifiable destruction certificate with SHA-256 hash across the disposal manifest, execution timestamp, and authorizing signatures.
- Dual-persistence: Persists quarantine records, signatures, and verifiable disposal certificates in both Cloud SQL relational audit storage and Firestore real-time state.
- Structured audit logging: Emits audit events to Cloud Audit Logs (`data-disposal-audit`).
- Expose ADK Agent tools on the root orchestrator for automated governance queries and execution.

## Acceptance Criteria
- AC-12.1: Default action after migration is `SOURCE_QUARANTINED` (retention of source data).
- AC-12.2: Disposal is blocked if validation exceptions, legal holds, or incomplete migrations remain unresolved.
- AC-12.3: Requires a separate, multi-signature approval (`DISPOSAL_APPROVED`) before verifiable destruction.

## Integration Points
- Ancestor US-5 (HITL Execution Gate): Utilizes `PERMISSION_TO_DISPOSE` approval gate and Firebase SSO identity verification.
- Ancestor US-11 (Migration Execution & Reconciliation): Reads migration status and unresolved validation exceptions. Provided with a clean stub fallback for US-11 WIP compatibility.
- Root Orchestrator (`zombie_saas_coordinator/agent.py`): Registers ADK agent tools `check_disposal_eligibility` and `execute_source_disposal` for root coordinator governance.

## Data Contracts
- `QuarantineStatus` Enum:
  - `SOURCE_QUARANTINED`
  - `DISPOSAL_PENDING_APPROVAL`
  - `DISPOSAL_APPROVED`
  - `DISPOSAL_BLOCKED`
  - `SOURCE_DESTROYED`
- `DisposalSignature`:
  - `signer_id`: str (Firebase UID)
  - `signer_email`: str | None
  - `role`: str
  - `signed_at`: datetime
  - `notes`: str | None
- `ValidationExceptionItem`:
  - `exception_id`: str
  - `description`: str
  - `severity`: str
  - `resolved`: bool
  - `resolved_by`: str | None
  - `resolution_notes`: str | None
- `QuarantineRecord`:
  - `proposal_id`: str
  - `app_id`: str
  - `app_name`: str
  - `status`: QuarantineStatus
  - `quarantined_at`: datetime
  - `retention_days`: int
  - `expires_at`: datetime
  - `legal_hold`: bool
  - `legal_hold_reason`: str | None
  - `migration_completed`: bool
  - `unresolved_exceptions`: list[ValidationExceptionItem]
  - `signatures`: list[DisposalSignature]
  - `required_signatures`: int
  - `disposal_certificate_id`: str | None
- `DisposalCertificate`:
  - `certificate_id`: str
  - `proposal_id`: str
  - `app_id`: str
  - `app_name`: str
  - `disposed_at`: datetime
  - `executor_id`: str
  - `executor_email`: str | None
  - `signers`: list[dict]
  - `verification_hash`: str (SHA-256)
  - `items_purged_count`: int
  - `status`: str

## Out of Scope
- Direct physical disk wiping at cloud provider hardware level.
- Automated court order discovery / external legal subpoena feeds.
