"""Migration execution and reconciliation API (US-11)."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from google.api_core.exceptions import AlreadyExists
from pydantic import BaseModel, Field

from zombie_saas_coordinator.shared.auth.firebase_auth import verify_firebase_auth_token
from zombie_saas_coordinator.shared.db.firestore_client import get_firestore_client
from zombie_saas_coordinator.shared.models.approval import ApprovalRecord
from zombie_saas_coordinator.shared.models.manifest import MigrationManifest
from zombie_saas_coordinator.shared.services.reconciliation import (
    create_manifest,
    execute_migration,
    persist_reconciliation,
    reconcile_migration,
)

router = APIRouter(prefix="/api/v1/reconciliation", tags=["migration", "reconciliation"])


class ManifestRequest(BaseModel):
    firebase_token: str
    proposal_id: str = Field(min_length=1)
    board_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    source_records: list[dict[str, Any]]
    source_page_count: int = Field(default=1, ge=1)


class ReconcileRequest(BaseModel):
    firebase_token: str
    target_records: list[dict[str, Any]]
    target_page_count: int = Field(default=1, ge=1)


class ExecuteRequest(BaseModel):
    """JSON request body for moving a manifest into the MIGRATING phase."""

    firebase_token: str


def _migration_authority(token: str) -> None:
    verify_firebase_auth_token(token, required_roles=["ciso", "it_ops", "admin", "security_admin"])


def _require_active_migration_approval(proposal_id: str) -> None:
    """Block execution unless the proposal's formal migration gate is active."""
    snapshot = (
        get_firestore_client()
        .collection("approvals")
        .document(f"{proposal_id}_PERMISSION_TO_MIGRATE")
        .get()
    )
    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active PERMISSION_TO_MIGRATE approval is required before execution.",
        )
    approval = ApprovalRecord.model_validate(snapshot.to_dict() or {})
    if not approval.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The PERMISSION_TO_MIGRATE approval is expired, revoked, or inactive.",
        )


@router.post("/manifest", status_code=status.HTTP_201_CREATED)
def create_manifest_endpoint(request: ManifestRequest) -> dict[str, Any]:
    _migration_authority(request.firebase_token)
    manifest = create_manifest(**request.model_dump(exclude={"firebase_token"}))
    try:
        get_firestore_client().collection("migration_manifests").document(
            manifest.manifest_id
        ).create(manifest.model_dump(mode="json"))
    except AlreadyExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A migration manifest with this ID already exists.",
        ) from exc
    return {"manifest": manifest.model_dump(mode="json")}


@router.post("/{manifest_id}/execute")
def execute_manifest_endpoint(manifest_id: str, request: ExecuteRequest) -> dict[str, Any]:
    _migration_authority(request.firebase_token)
    snapshot = get_firestore_client().collection("migration_manifests").document(manifest_id).get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Migration manifest not found")
    manifest = MigrationManifest.model_validate(snapshot.to_dict() or {})
    _require_active_migration_approval(manifest.proposal_id)
    updated = execute_migration(
        manifest.board_id, manifest.project_id, manifest.model_dump(mode="json")
    )
    get_firestore_client().collection("migration_manifests").document(manifest_id).set(updated)
    return {"manifest": updated}


@router.post("/{manifest_id}/reconcile")
def reconcile_manifest_endpoint(manifest_id: str, request: ReconcileRequest) -> dict[str, Any]:
    _migration_authority(request.firebase_token)
    snapshot = get_firestore_client().collection("migration_manifests").document(manifest_id).get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Migration manifest not found")
    result = reconcile_migration(
        snapshot.to_dict() or {}, request.target_records, request.target_page_count
    )
    persist_reconciliation(result)
    return result


@router.get("/{manifest_id}/exceptions")
def exception_report_endpoint(manifest_id: str, firebase_token: str) -> dict[str, Any]:
    _migration_authority(firebase_token)
    reports = (
        get_firestore_client()
        .collection("migration_exception_reports")
        .where("manifest_id", "==", manifest_id)
        .stream()
    )
    report = next((item.to_dict() for item in reports), None)
    if report is None:
        raise HTTPException(status_code=404, detail="Reconciliation report not found")
    return {"report": report}
