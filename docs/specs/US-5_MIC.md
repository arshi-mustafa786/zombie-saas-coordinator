# Module Interface Contract (MIC) — US-5: HITL Execution Gate

| # | Component / Method | Signature | Return Type | Raised Exceptions | Docstring |
|---|-------------------|-----------|-------------|-------------------|-----------|
| 1 | `verify_firebase_auth_token` | `verify_firebase_auth_token(token: str, required_roles: list[str] | None = None) -> dict[str, Any]` | `dict[str, Any]` | `HTTPException` (401, 403) | Verifies Firebase ID token, validates SSO claims, and checks RBAC permissions. |
| 2 | `record_approval` | `record_approval(proposal_id: str, approver_info: dict[str, Any], gate_type: str = "PERMISSION_TO_MIGRATE", notes: str | None = None) -> ApprovalRecord` | `ApprovalRecord` | `ValueError`, `HTTPException` (404, 409) | Persists approval with 7-day TTL to Cloud SQL and Firestore, emitting audit logs. |
| 3 | `check_approval_status` (Agent Tool) | `check_approval_status(proposal_id: str, required_gate: str = "PERMISSION_TO_MIGRATE") -> dict[str, Any]` | `dict[str, Any]` | `None` | Checks if an authorized human approved the proposal within the 7-day window. |
| 4 | `revoke_approval` (Agent Tool) | `revoke_approval(proposal_id: str, revoker_info: dict[str, Any] | str, reason: str) -> dict[str, Any]` | `dict[str, Any]` | `ValueError` | Revokes a previously granted approval, halting in-progress agent pipelines. |
| 5 | `authorize_proposal_endpoint` (API) | `POST /api/v1/approvals/{proposal_id}/authorize` | `dict[str, Any]` | `HTTPException` (400, 401, 403, 404, 409) | Cloud Run endpoint for SSO human authorization via Firebase Auth token. |
| 6 | `revoke_approval_endpoint` (API) | `POST /api/v1/approvals/{proposal_id}/revoke` | `dict[str, Any]` | `HTTPException` (400, 401, 403, 404) | Cloud Run endpoint to revoke approval and halt ongoing consolidation. |
| 7 | `get_approval_status_endpoint` (API) | `GET /api/v1/approvals/{proposal_id}` | `dict[str, Any]` | `HTTPException` (404) | Cloud Run endpoint to inspect current approval gate and expiry status. |

### Public Interface Count Gate
- Count: 7 methods
- Limit: ≤ 7 methods
- Status: **PASSED**
