# Module Interface Contract (MIC) — US-12: Fail-Safe Quarantine and Disposal

| # | Component / Method | Signature | Return Type | Raised Exceptions | Docstring |
|---|-------------------|-----------|-------------|-------------------|-----------|
| 1 | `quarantine_source_data` | `quarantine_source_data(proposal_id: str, source_metadata: dict[str, Any] | None = None, retention_days: int = 90) -> QuarantineRecord` | `QuarantineRecord` | `ValueError`, `HTTPException` (404) | Automatically places source SaaS data into SOURCE_QUARANTINED status with retention window. |
| 2 | `set_legal_hold` | `set_legal_hold(proposal_id: str, operator_info: dict[str, Any], legal_hold: bool, reason: str | None = None) -> QuarantineRecord` | `QuarantineRecord` | `ValueError`, `HTTPException` (404, 400) | Sets or releases legal hold on quarantined source data, immediately blocking/unblocking disposal. |
| 3 | `check_disposal_eligibility` | `check_disposal_eligibility(proposal_id: str) -> dict[str, Any]` | `dict[str, Any]` | `None` | Inspects blockers (legal hold, exceptions, migration status, signature quorum) and returns eligibility dict. |
| 4 | `submit_disposal_signature` | `submit_disposal_signature(proposal_id: str, signer_info: dict[str, Any], notes: str | None = None) -> dict[str, Any]` | `dict[str, Any]` | `ValueError`, `HTTPException` (400, 404, 409) | Records verified SSO signature for multi-sig authorization; transitions to DISPOSAL_APPROVED once quorum met. |
| 5 | `execute_verifiable_disposal` | `execute_verifiable_disposal(proposal_id: str, executor_info: dict[str, Any]) -> DisposalCertificate` | `DisposalCertificate` | `ValueError`, `HTTPException` (400, 404, 409) | Executes verifiable destruction, computing SHA-256 certificate and persisting proof in Cloud SQL and Firestore. |
| 6 | `get_quarantine_record` | `get_quarantine_record(proposal_id: str) -> QuarantineRecord | None` | `QuarantineRecord | None` | `None` | Fetches current quarantine and disposal record with audit trail. |
| 7 | `resolve_validation_exception` | `resolve_validation_exception(proposal_id: str, exception_id: str, resolution_notes: str, resolved_by: str) -> dict[str, Any]` | `dict[str, Any]` | `ValueError`, `HTTPException` (404, 400) | Resolves a pending validation exception on quarantined data, updating blockers. |

### Public Interface Count Gate
- Count: 7 methods
- Limit: ≤ 7 methods
- Status: **PASSED**
