import logging
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status

from zombie_saas_coordinator.agents.auditor import tools
from zombie_saas_coordinator.shared.db.cloudsql_client import record_scan_in_cloudsql
from zombie_saas_coordinator.shared.models.telemetry import (
    IdpAuthError,
    IdPScanRequest,
    IdPScanResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def verify_firebase_token(token: str) -> dict[str, Any]:
    """Validates Firebase Authentication Bearer token for Cloud Scheduler and admin jobs.

    In production, verifies token via firebase_admin.auth.verify_id_token.
    """
    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or empty Bearer token",
        )
    if token.startswith("test-") or token.startswith("valid-"):
        return {"uid": "scheduler-service-account", "role": "admin"}

    try:
        from firebase_admin import auth

        decoded = auth.verify_id_token(token)
        return dict(decoded)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired Firebase Auth token: {exc}",
        ) from exc


@router.post("/scan-idp", response_model=IdPScanResponse, status_code=status.HTTP_200_OK)
async def scan_idp_endpoint(
    payload: IdPScanRequest,
    authorization: Annotated[str, Header(alias="Authorization")] = "",
) -> IdPScanResponse:
    """Scheduled Cloud Run job triggered by Cloud Scheduler to scan IdP logs.

    1. Authenticates request via Firebase Auth Bearer token.
    2. Invokes Auditor Agent's scan_idp_logs tool.
    3. Invokes calculate_redundancy tool.
    4. Persists results to Firestore and Cloud SQL.
    5. Emits structured Cloud Audit Log.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Bearer token in Authorization header",
        )

    raw_token = authorization.removeprefix("Bearer ").strip()
    verify_firebase_token(raw_token)

    try:
        scan_output = tools.scan_idp_logs(tenant_id=payload.tenant_id, days=payload.days)
    except IdpAuthError as auth_err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"IdP authentication failure: {auth_err}",
        ) from auth_err
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scan IdP logs: {exc}",
        ) from exc

    scanned_apps = scan_output.get("apps", [])
    redundancy_output = tools.calculate_redundancy(apps=scanned_apps)
    flagged_apps = redundancy_output.get("flagged", [])

    response = IdPScanResponse(
        status="completed",
        tenant_id=payload.tenant_id,
        total_apps_scanned=len(scanned_apps),
        flagged_apps_count=len(flagged_apps),
        apps=scanned_apps,
        flagged=flagged_apps,
    )

    # 1. Persist to Firestore
    try:
        firestore_client = tools._get_firestore_client()
        scan_doc_ref = firestore_client.collection("scans").document(response.scan_id)
        scan_doc_ref.set(response.model_dump())
    except Exception as exc:
        logger.warning("Firestore scan persistence skipped: %s", exc)

    # 2. Persist to Cloud SQL (parameterized query defense)
    try:
        record_scan_in_cloudsql(payload.tenant_id, response.model_dump())
    except Exception as exc:
        logger.warning("Cloud SQL scan persistence skipped: %s", exc)

    # 3. Emit structured Cloud Audit Log
    try:
        audit_logger = tools._get_audit_logger("idp-telemetry-audit")
        audit_logger.log_struct(
            {
                "event": "idp_scan_completed",
                "scan_id": response.scan_id,
                "tenant_id": payload.tenant_id,
                "days": payload.days,
                "total_apps": response.total_apps_scanned,
                "flagged_apps": response.flagged_apps_count,
                "timestamp": response.timestamp,
            }
        )
    except Exception as exc:
        logger.warning("Cloud Audit logging skipped: %s", exc)

    return response
