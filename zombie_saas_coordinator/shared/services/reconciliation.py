"""Safe, auditable migration planning and reconciliation service (US-11)."""

import hashlib
import json
from base64 import b64encode
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from google.cloud import logging

from zombie_saas_coordinator.shared.constants import (
    MIGRATION_EXCEPTION_REPORTS_COLLECTION,
    MIGRATION_MANIFESTS_COLLECTION,
    MIGRATION_RECONCILIATION_AUDIT_LOG,
)
from zombie_saas_coordinator.shared.db.firestore_client import get_firestore_client
from zombie_saas_coordinator.shared.models.manifest import (
    MigrationItem,
    MigrationManifest,
    MigrationPhase,
    ReconciliationException,
    ReconciliationReport,
)


def _normalize_for_hash(value: Any) -> Any:
    """Convert values to stable cross-runtime representations before hashing."""
    if isinstance(value, datetime):
        timestamp = value if value.tzinfo else value.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        return {"__bytes_base64__": b64encode(value).decode("ascii")}
    if isinstance(value, Enum):
        return _normalize_for_hash(value.value)
    if isinstance(value, dict):
        return {str(key): _normalize_for_hash(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_for_hash(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_for_hash(item) for item in value)
    return value


def canonical_hash(record: dict[str, Any]) -> str:
    """Return a stable SHA-256 digest for a record's migration-relevant fields."""
    canonical = json.dumps(
        _normalize_for_hash(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_manifest(
    proposal_id: str,
    board_id: str,
    project_id: str,
    source_records: list[dict[str, Any]],
    source_page_count: int = 1,
) -> MigrationManifest:
    """Create a manifest before migration; source payloads are hashed, never stored."""
    items: list[MigrationItem] = []
    for record in source_records:
        source_id = str(record.get("id") or record.get("source_id") or "")
        if not source_id:
            raise ValueError("each source record must contain id or source_id")
        payload = record.get("data", record)
        if not isinstance(payload, dict):
            raise ValueError("source record data must be an object")
        items.append(
            MigrationItem(
                source_id=source_id,
                record_type=str(record.get("record_type", "record")),
                source_hash=canonical_hash(payload),
                source_attachment_count=int(record.get("attachment_count", 0)),
                source_comment_count=int(record.get("comment_count", 0)),
            )
        )
    return MigrationManifest(
        proposal_id=proposal_id,
        board_id=board_id,
        project_id=project_id,
        items=items,
        source_page_count=source_page_count,
    )


def execute_migration(board_id: str, project_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """Enter MIGRATING and create deterministic target IDs for approved adapter execution.

    This deliberately performs no provider write. It establishes the idempotent mapping
    an approved Trello-to-Asana adapter must use, preventing duplicate target records.
    """
    parsed = MigrationManifest.model_validate(manifest)
    if parsed.board_id != board_id or parsed.project_id != project_id:
        raise ValueError("board_id and project_id must match the manifest")

    mapped_items = [
        item.model_copy(
            update={
                "target_id": item.target_id or f"{parsed.target_app}_{item.source_id}",
                "migration_attempts": item.migration_attempts + 1,
            }
        )
        for item in parsed.items
    ]
    updated = parsed.model_copy(
        update={
            "phase": MigrationPhase.MIGRATING,
            "items": mapped_items,
            "updated_at": datetime.now(UTC),
        }
    )
    return updated.model_dump(mode="json")


def reconcile_migration(
    manifest: dict[str, Any], target_records: list[dict[str, Any]], target_page_count: int = 1
) -> dict[str, Any]:
    """Compare count, field digest, attachment, and comment evidence after migration."""
    parsed = MigrationManifest.model_validate(manifest)
    exceptions: list[ReconciliationException] = []
    by_id: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(target_records):
        target_id = str(record.get("id") or record.get("target_id") or "").strip()
        if not target_id:
            exceptions.append(
                ReconciliationException(
                    code="TARGET_RECORD_ID_MISSING",
                    message=f"target record at index {index} has no id or target_id",
                    retryable=True,
                )
            )
        elif target_id in by_id:
            exceptions.append(
                ReconciliationException(
                    code="DUPLICATE_TARGET_RECORD_ID",
                    target_id=target_id,
                    message="multiple target records share the same target identifier",
                    retryable=True,
                )
            )
        else:
            by_id[target_id] = record
    verified = 0

    if len(parsed.items) != len(target_records):
        exceptions.append(
            ReconciliationException(
                code="COUNT_MISMATCH",
                message=(
                    f"source has {len(parsed.items)} records but target has {len(target_records)}"
                ),
                retryable=True,
            )
        )

    for item in parsed.items:
        target = by_id.get(item.target_id) if item.target_id else None
        if target is None:
            exceptions.append(
                ReconciliationException(
                    code="MISSING_TARGET_RECORD",
                    source_id=item.source_id,
                    target_id=item.target_id,
                    message="source record has no mapped target record",
                    retryable=True,
                )
            )
            continue
        payload = target.get("data", target)
        if not isinstance(payload, dict):
            payload = {}
        target_hash = canonical_hash(payload)
        attachment_count = int(target.get("attachment_count", 0))
        comment_count = int(target.get("comment_count", 0))
        mismatched = False
        if target_hash != item.source_hash:
            exceptions.append(
                ReconciliationException(
                    code="FIELD_HASH_MISMATCH",
                    source_id=item.source_id,
                    target_id=item.target_id,
                    message="canonical field digest differs between source and target",
                )
            )
            mismatched = True
        if attachment_count != item.source_attachment_count:
            exceptions.append(
                ReconciliationException(
                    code="ATTACHMENT_COUNT_MISMATCH",
                    source_id=item.source_id,
                    target_id=item.target_id,
                    message="attachment count differs between source and target",
                    retryable=True,
                )
            )
            mismatched = True
        if comment_count != item.source_comment_count:
            exceptions.append(
                ReconciliationException(
                    code="COMMENT_COUNT_MISMATCH",
                    source_id=item.source_id,
                    target_id=item.target_id,
                    message="comment count differs between source and target",
                    retryable=True,
                )
            )
            mismatched = True
        if not mismatched:
            verified += 1

    report = ReconciliationReport(
        manifest_id=parsed.manifest_id,
        source_count=len(parsed.items),
        target_count=len(target_records),
        source_page_count=parsed.source_page_count,
        target_page_count=target_page_count,
        mapped_count=sum(item.target_id is not None for item in parsed.items),
        verified_count=verified,
        exceptions=exceptions,
        reconciled=not exceptions,
    )
    updated = parsed.model_copy(
        update={
            "phase": MigrationPhase.RECONCILED
            if report.reconciled
            else MigrationPhase.EXCEPTIONS_FOUND,
            "target_page_count": target_page_count,
            "updated_at": datetime.now(UTC),
        }
    )
    return {"manifest": updated.model_dump(mode="json"), "report": report.model_dump(mode="json")}


def persist_reconciliation(result: dict[str, Any]) -> None:
    """Persist manifest/report without embedding source content in Firestore."""
    manifest = MigrationManifest.model_validate(result["manifest"])
    report = ReconciliationReport.model_validate(result["report"])
    client = get_firestore_client()
    client.collection(MIGRATION_MANIFESTS_COLLECTION).document(manifest.manifest_id).set(
        manifest.model_dump(mode="json")
    )
    client.collection(MIGRATION_EXCEPTION_REPORTS_COLLECTION).document(report.report_id).set(
        report.model_dump(mode="json")
    )
    logging.Client().logger(MIGRATION_RECONCILIATION_AUDIT_LOG).log_struct(  # type: ignore[no-untyped-call]
        {
            "event": "migration_reconciled",
            "manifest_id": manifest.manifest_id,
            "report_id": report.report_id,
            "reconciled": report.reconciled,
            "exception_count": len(report.exceptions),
        },
        severity="NOTICE",
    )
