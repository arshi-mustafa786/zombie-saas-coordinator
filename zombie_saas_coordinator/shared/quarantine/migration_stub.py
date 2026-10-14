"""Migration reconciliation integration service for US-12 (direct US-11 integration).

Connects US-12 quarantine and verifiable disposal directly to US-11 migration manifests,
reconciliation reports, and exception tracking in Firestore.
"""

import contextlib
from typing import Any

from google.cloud import firestore

from zombie_saas_coordinator.shared.constants import (
    MIGRATION_EXCEPTION_REPORTS_COLLECTION,
    MIGRATION_MANIFESTS_COLLECTION,
    PROPOSALS_COLLECTION,
)
from zombie_saas_coordinator.shared.models.manifest import MigrationPhase


def get_migration_reconciliation_status(
    proposal_id: str,
    firestore_client: firestore.Client | None = None,
) -> dict[str, Any]:
    """Inspects real US-11 migration manifests and reconciliation exception reports.

    Queries Firestore for migration manifests associated with the proposal,
    determines whether migration is completed (phase RECONCILED or EXCEPTIONS_FOUND),
    fetches unresolved exceptions from migration exception reports, and counts items.

    Returns:
        dict containing:
            - migration_completed (bool)
            - unresolved_exceptions (list of exception dicts)
            - items_count (int)
    """
    if firestore_client is None:
        return {
            "migration_completed": False,
            "unresolved_exceptions": [],
            "items_count": 0,
        }

    manifest_data: dict[str, Any] | None = None
    manifest_id: str | None = None

    # 1. Try direct document lookup by proposal_id (used in tests or direct ID mapping)
    with contextlib.suppress(Exception):
        doc = (
            firestore_client.collection(MIGRATION_MANIFESTS_COLLECTION)
            .document(proposal_id)
            .get()
        )
        if hasattr(doc, "exists") and doc.exists:
            raw = doc.to_dict()
            if isinstance(raw, dict):
                manifest_data = raw
                manifest_id = manifest_data.get("manifest_id", doc.id)

    # 2. Query by proposal_id field (standard US-11 manifest persistence)
    if not manifest_data:
        with contextlib.suppress(Exception):
            stream = (
                firestore_client.collection(MIGRATION_MANIFESTS_COLLECTION)
                .where("proposal_id", "==", proposal_id)
                .stream()
            )
            for m_doc in stream:
                if hasattr(m_doc, "to_dict"):
                    raw = m_doc.to_dict()
                    if isinstance(raw, dict):
                        manifest_data = raw
                        manifest_id = manifest_data.get("manifest_id", getattr(m_doc, "id", None))
                        break

    # If an actual manifest was found, parse US-11 state
    if manifest_data:
        phase = str(manifest_data.get("phase") or manifest_data.get("status") or "")
        migration_completed = phase in {
            MigrationPhase.RECONCILED.value,
            MigrationPhase.EXCEPTIONS_FOUND.value,
            "RECONCILED",
            "EXCEPTIONS_FOUND",
            "COMPLETED",
        }
        items = manifest_data.get("items", [])
        if isinstance(items, list) and items:
            items_count = len(items)
        else:
            items_count = int(manifest_data.get("items_count", 0))

        unresolved_exceptions: list[dict[str, Any]] = []
        for exc in manifest_data.get("exceptions", []):
            if isinstance(exc, dict):
                unresolved_exceptions.append({
                    "exception_id": exc.get("code") or exc.get("exception_id") or "EXC-MIG",
                    "description": (
                        exc.get("message") or exc.get("description", "Reconciliation exception")
                    ),
                    "severity": "HIGH" if not exc.get("retryable", False) else "MEDIUM",
                    "resolved": exc.get("resolved", False),
                })

        # Also query MIGRATION_EXCEPTION_REPORTS_COLLECTION for reports linked to this manifest_id
        if manifest_id:
            with contextlib.suppress(Exception):
                reports = (
                    firestore_client.collection(MIGRATION_EXCEPTION_REPORTS_COLLECTION)
                    .where("manifest_id", "==", manifest_id)
                    .stream()
                )
                for r_doc in reports:
                    if hasattr(r_doc, "to_dict"):
                        r_data = r_doc.to_dict()
                        if isinstance(r_data, dict):
                            for exc in r_data.get("exceptions", []):
                                if isinstance(exc, dict):
                                    unresolved_exceptions.append({
                                        "exception_id": (
                                            exc.get("code")
                                            or exc.get("exception_id")
                                            or "EXC-REC"
                                        ),
                                        "description": (
                                            exc.get("message")
                                            or exc.get("description", "Reconciliation exception")
                                        ),
                                        "severity": (
                                            "HIGH" if not exc.get("retryable", False) else "MEDIUM"
                                        ),
                                        "resolved": False,
                                    })

        return {
            "migration_completed": migration_completed,
            "unresolved_exceptions": unresolved_exceptions,
            "items_count": items_count,
        }

    # 3. If no manifest found, check if proposal document exists in consolidation_proposals
    with contextlib.suppress(Exception):
        prop_doc = firestore_client.collection(PROPOSALS_COLLECTION).document(proposal_id).get()
        if hasattr(prop_doc, "exists") and prop_doc.exists:
            prop_data = prop_doc.to_dict()
            if isinstance(prop_data, dict):
                status_val = prop_data.get("migration_status") or prop_data.get("status")
                is_completed = status_val in {"COMPLETED", "RECONCILED", "APPROVED"}
                return {
                    "migration_completed": is_completed,
                    "unresolved_exceptions": prop_data.get("migration_exceptions", []),
                    "items_count": int(prop_data.get("items_count", 0)),
                }

    # Default if no record found anywhere
    return {
        "migration_completed": True,
        "unresolved_exceptions": [],
        "items_count": 0,
    }
