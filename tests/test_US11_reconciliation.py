"""Tests for US-11 migration execution and reconciliation."""

# ruff: noqa: N999, S106

from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from zombie_saas_coordinator.main import app
from zombie_saas_coordinator.shared.models.manifest import MigrationPhase
from zombie_saas_coordinator.shared.services.reconciliation import (
    canonical_hash,
    create_manifest,
    execute_migration,
    reconcile_migration,
)


def _source_records() -> list[dict[str, Any]]:
    return [
        {
            "id": "card-1",
            "record_type": "card",
            "data": {"name": "Prepare cutover", "status": "open"},
            "attachment_count": 2,
            "comment_count": 3,
        },
        {
            "id": "card-2",
            "record_type": "card",
            "data": {"name": "Verify result", "status": "done"},
            "attachment_count": 0,
            "comment_count": 1,
        },
    ]


def _executed_manifest() -> dict[str, Any]:
    manifest = create_manifest("proposal-1", "board-1", "project-1", _source_records())
    return execute_migration("board-1", "project-1", manifest.model_dump(mode="json"))


def test_execute_creates_stable_source_to_target_mapping() -> None:
    executed = _executed_manifest()
    retry = execute_migration("board-1", "project-1", executed)

    assert executed["phase"] == MigrationPhase.MIGRATING.value
    assert [item["target_id"] for item in executed["items"]] == [
        "asana_card-1",
        "asana_card-2",
    ]
    assert [item["target_id"] for item in retry["items"]] == [
        "asana_card-1",
        "asana_card-2",
    ]
    assert retry["items"][0]["migration_attempts"] == 2


def test_reconciliation_generates_cryptographic_proof_for_matching_records() -> None:
    executed = _executed_manifest()
    result = reconcile_migration(
        executed,
        [
            {
                "id": "asana_card-1",
                "data": {"name": "Prepare cutover", "status": "open"},
                "attachment_count": 2,
                "comment_count": 3,
            },
            {
                "id": "asana_card-2",
                "data": {"name": "Verify result", "status": "done"},
                "attachment_count": 0,
                "comment_count": 1,
            },
        ],
    )

    assert result["report"]["reconciled"] is True
    assert result["report"]["verified_count"] == 2
    assert result["report"]["exceptions"] == []
    assert result["manifest"]["phase"] == MigrationPhase.RECONCILED.value


def test_reconciliation_isolates_partial_failure_for_retry() -> None:
    result = reconcile_migration(
        _executed_manifest(),
        [
            {
                "id": "asana_card-1",
                "data": {"name": "Prepare cutover", "status": "open"},
                "attachment_count": 1,
                "comment_count": 3,
            }
        ],
    )

    codes = {item["code"] for item in result["report"]["exceptions"]}
    assert result["report"]["reconciled"] is False
    assert {"COUNT_MISMATCH", "ATTACHMENT_COUNT_MISMATCH", "MISSING_TARGET_RECORD"} <= codes
    assert result["manifest"]["phase"] == MigrationPhase.EXCEPTIONS_FOUND.value


def test_execute_rejects_manifest_with_different_scope() -> None:
    manifest = create_manifest("proposal-1", "board-1", "project-1", _source_records())
    with pytest.raises(ValueError, match="must match"):
        execute_migration("board-other", "project-1", manifest.model_dump(mode="json"))


def test_hash_normalizes_datetime_to_a_stable_utc_representation() -> None:
    naive = {"occurred_at": datetime(2026, 10, 14, 10, 0, 0)}
    aware = {"occurred_at": datetime(2026, 10, 14, 10, 0, 0, tzinfo=UTC)}

    assert canonical_hash(naive) == canonical_hash(aware)


def test_reconciliation_isolates_target_records_without_ids() -> None:
    result = reconcile_migration(
        _executed_manifest(),
        [{"data": {"name": "Prepare cutover", "status": "open"}}],
    )

    codes = {item["code"] for item in result["report"]["exceptions"]}
    assert "TARGET_RECORD_ID_MISSING" in codes


def test_reconcile_endpoint_returns_exception_report(monkeypatch: pytest.MonkeyPatch) -> None:
    from zombie_saas_coordinator.api import reconciliation

    executed = _executed_manifest()
    document = Mock()
    document.get.return_value.exists = True
    document.get.return_value.to_dict.return_value = executed
    collection = Mock()
    collection.document.return_value = document
    firestore = Mock()
    firestore.collection.return_value = collection
    monkeypatch.setattr(reconciliation, "get_firestore_client", lambda: firestore)
    monkeypatch.setattr(reconciliation, "persist_reconciliation", lambda result: None)
    monkeypatch.setattr(reconciliation, "_migration_authority", lambda token: None)

    response = TestClient(app).post(
        f"/api/v1/reconciliation/{executed['manifest_id']}/reconcile",
        json={"firebase_token": "test", "target_records": [], "target_page_count": 1},
    )

    assert response.status_code == 200
    assert response.json()["report"]["reconciled"] is False


def test_execute_endpoint_accepts_json_body_and_checks_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zombie_saas_coordinator.api import reconciliation

    executed = _executed_manifest()
    document = Mock()
    document.get.return_value.exists = True
    document.get.return_value.to_dict.return_value = executed
    collection = Mock()
    collection.document.return_value = document
    firestore = Mock()
    firestore.collection.return_value = collection
    monkeypatch.setattr(reconciliation, "get_firestore_client", lambda: firestore)
    monkeypatch.setattr(reconciliation, "_migration_authority", lambda token: None)
    monkeypatch.setattr(reconciliation, "_require_active_migration_approval", lambda _: None)

    response = TestClient(app).post(
        f"/api/v1/reconciliation/{executed['manifest_id']}/execute",
        json={"firebase_token": "test"},
    )

    assert response.status_code == 200
    assert response.json()["manifest"]["phase"] == MigrationPhase.MIGRATING.value
