"""Migration reconciliation dummy / stub layer for US-11 compatibility.

NOTE: US-9, US-10, and US-11 are currently WIP in active branches.
This stub inspects Firestore for any US-11 migration manifests or exception reports.
If US-11 data has not yet landed in main, it safely falls back to a clean completed
state or checks proposal status, ensuring US-12 fail-safe quarantine and disposal
can operate and test independently. Once US-11 merges to main, this stub can be replaced
with direct US-11 module imports.
"""

import contextlib
from typing import Any

from google.cloud import firestore


def get_migration_reconciliation_status(
    proposal_id: str,
    firestore_client: firestore.Client | None = None,
) -> dict[str, Any]:
    """Inspects migration manifest and exception status for a proposal.

    Returns:
        dict containing:
            - migration_completed (bool)
            - unresolved_exceptions (list of exception dicts)
            - items_count (int)
    """
    if firestore_client is not None:
        with contextlib.suppress(Exception):
            manifest_doc = (
                firestore_client.collection("migration_manifests").document(proposal_id).get()
            )
            if manifest_doc.exists:
                data = manifest_doc.to_dict() or {}
                if "status" in data:
                    return {
                        "migration_completed": data.get("status") in {"COMPLETED", "RECONCILED"},
                        "unresolved_exceptions": data.get("exceptions", []),
                        "items_count": data.get("items_count", 0),
                    }

    # Fallback default for WIP environments
    return {
        "migration_completed": True,
        "unresolved_exceptions": [],
        "items_count": 100,
    }
