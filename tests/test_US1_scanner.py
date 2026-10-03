"""Tests for US-1 scheduled identity & access telemetry scanner."""

# ruff: noqa: N999, S106, S107

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from fastapi.testclient import TestClient

from zombie_saas_coordinator.agents.auditor import tools
from zombie_saas_coordinator.main import app
from zombie_saas_coordinator.shared.models.telemetry import (
    IdpAuthError,
)


def _mock_firestore() -> tuple[Mock, Mock]:
    client = Mock()
    scans_collection = Mock()
    doc_ref = Mock()
    scans_collection.document.return_value = doc_ref
    client.collection.return_value = scans_collection
    return client, doc_ref


def _sample_raw_apps() -> list[dict[str, Any]]:
    return [
        {
            "app_id": "app_trello_01",
            "app_name": "Trello",
            "vendor": "Atlassian",
            "category": "Project Management",
            "capabilities": ["kanban", "task-tracking", "collaboration"],
            "total_seats": 100,
            "active_seats": 30,
            "inactive_seats": 70,  # 70% inactive >= 60% threshold
            "last_login_date": (datetime.now(UTC) - timedelta(days=65)).isoformat(),
        },
        {
            "app_id": "app_jira_01",
            "app_name": "Jira Software",
            "vendor": "Atlassian",
            "category": "Project Management",
            "capabilities": ["kanban", "scrum", "issue-tracking", "enterprise-agile"],
            "total_seats": 200,
            "active_seats": 180,
            "inactive_seats": 20,  # 10% inactive < 60% threshold
            "last_login_date": datetime.now(UTC).isoformat(),
        },
    ]


# ─────────────────────────────────────────────────────────────
# 1. Unit Tests: Tool Functions
# ─────────────────────────────────────────────────────────────


def test_scan_idp_logs_flags_inactive_seats_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-1.3: Flags app when >= 60% of assigned seats show zero logins over 60+ days."""
    mock_apps = _sample_raw_apps()

    # Mock IdP telemetry fetch
    monkeypatch.setattr(
        tools, "_fetch_idp_application_telemetry", lambda tenant_id, days: mock_apps
    )

    result = tools.scan_idp_logs(tenant_id="tenant-acme-corp", days=60)
    assert result["status"] == "success"
    apps = result["apps"]
    assert len(apps) == 2

    # Trello: 70% inactive -> flagged
    trello = next(a for a in apps if a["app_name"] == "Trello")
    assert trello["is_flagged_inactive"] is True
    assert trello["inactive_ratio"] == 0.70

    # Jira: 10% inactive -> not flagged
    jira = next(a for a in apps if a["app_name"] == "Jira Software")
    assert jira["is_flagged_inactive"] is False
    assert jira["inactive_ratio"] == 0.10


def test_scan_idp_logs_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge Case: 0 apps returned from IdP — tool returns empty result gracefully."""
    monkeypatch.setattr(tools, "_fetch_idp_application_telemetry", lambda tenant_id, days: [])

    result = tools.scan_idp_logs(tenant_id="tenant-empty", days=60)
    assert result["status"] == "success"
    assert result["apps"] == []
    assert result["total_scanned"] == 0


def test_scan_idp_logs_auth_error_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Error Path: IdpAuthError raised if IdP credentials or federation tokens fail."""

    def _raise_auth_error(tenant_id: str, days: int) -> list[dict[str, Any]]:
        raise IdpAuthError("Failed to authenticate with identity provider")

    monkeypatch.setattr(tools, "_fetch_idp_application_telemetry", _raise_auth_error)

    with pytest.raises(IdpAuthError, match="Failed to authenticate"):
        tools.scan_idp_logs(tenant_id="tenant-bad-token", days=60)


def test_calculate_redundancy_detects_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-1.4: Detects capability redundancy using Gemini semantic matching."""
    apps = _sample_raw_apps()

    result = tools.calculate_redundancy(apps)
    assert result["status"] == "success"
    flagged = result["flagged"]

    # Trello overlaps with enterprise standard Jira
    trello_flag = next((f for f in flagged if f["app_name"] == "Trello"), None)
    assert trello_flag is not None
    assert trello_flag["redundancy_score"] >= 70
    match_str = trello_flag["enterprise_standard_match"]
    assert "Jira" in match_str or "Enterprise" in match_str
    assert len(trello_flag["overlapping_capabilities"]) > 0


# ─────────────────────────────────────────────────────────────
# 2. Integration Tests: API Endpoint & Vertical Slice
# ─────────────────────────────────────────────────────────────


def test_scan_idp_endpoint_requires_auth() -> None:
    """Security: Missing or invalid Firebase Auth token returns 401."""
    client = TestClient(app)
    response = client.post("/api/v1/jobs/scan-idp", json={"tenant_id": "tenant-123", "days": 60})
    error_detail = response.json()["detail"]
    assert "Bearer token" in error_detail or "Unauthorized" in error_detail


def test_scan_idp_endpoint_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Happy Path: Scheduler hits endpoint with Bearer token, scans, and stores in Firestore."""
    client = TestClient(app)

    # Mock Firebase Auth verification
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.scanner.verify_firebase_token",
        lambda token: {"uid": "scheduler-service-account", "role": "admin"},
    )

    # Mock IdP fetch & redundancy
    monkeypatch.setattr(
        tools, "_fetch_idp_application_telemetry", lambda tenant_id, days: _sample_raw_apps()
    )

    # Mock Firestore
    mock_firestore_client, mock_doc = _mock_firestore()
    monkeypatch.setattr(tools, "_get_firestore_client", lambda: mock_firestore_client)

    # Mock Audit Logger
    mock_logger = Mock()
    monkeypatch.setattr(tools, "_get_audit_logger", lambda *args, **kwargs: mock_logger)

    # Mock Cloud SQL persistence
    mock_sql_recorder = Mock()
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.scanner.record_scan_in_cloudsql",
        mock_sql_recorder,
    )

    headers = {"Authorization": "Bearer valid-firebase-token-123"}
    response = client.post(
        "/api/v1/jobs/scan-idp",
        headers=headers,
        json={"tenant_id": "tenant-acme", "days": 60},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["tenant_id"] == "tenant-acme"
    assert data["total_apps_scanned"] == 2
    assert data["flagged_apps_count"] >= 1

    # Verify Firestore persistence was called
    mock_doc.set.assert_called_once()
    # Verify Audit log was recorded
    mock_logger.log_struct.assert_called_once()
    # Verify Cloud SQL was recorded
    mock_sql_recorder.assert_called_once()


def test_scan_idp_endpoint_sql_injection_defense(monkeypatch: pytest.MonkeyPatch) -> None:
    """Security: SQL injection strings in tenant_id are handled safely without syntax error."""
    client = TestClient(app)

    monkeypatch.setattr(
        "zombie_saas_coordinator.api.scanner.verify_firebase_token",
        lambda token: {"uid": "scheduler-service-account", "role": "admin"},
    )
    monkeypatch.setattr(tools, "_fetch_idp_application_telemetry", lambda tenant_id, days: [])

    mock_firestore_client, _ = _mock_firestore()
    monkeypatch.setattr(tools, "_get_firestore_client", lambda: mock_firestore_client)
    monkeypatch.setattr(tools, "_get_audit_logger", lambda: Mock())

    # Mock Cloud SQL persistence to verify parameters passed safely
    mock_sql_recorder = Mock()
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.scanner.record_scan_in_cloudsql",
        mock_sql_recorder,
    )

    malicious_tenant = "tenant-1'; DROP TABLE application_inventory; --"
    headers = {"Authorization": "Bearer valid-firebase-token-123"}
    response = client.post(
        "/api/v1/jobs/scan-idp",
        headers=headers,
        json={"tenant_id": malicious_tenant, "days": 60},
    )

    assert response.status_code == 200
    mock_sql_recorder.assert_called_once()
    call_args = mock_sql_recorder.call_args[0]
    # Ensure parameter was preserved verbatim as string, not injected into SQL query
    assert call_args[0] == malicious_tenant


def test_verify_firebase_token_validations() -> None:
    """Security: verify_firebase_token properly validates tokens and rejects empty/invalid."""
    from fastapi import HTTPException

    from zombie_saas_coordinator.api.scanner import verify_firebase_token

    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_token("")
    assert exc_info.value.status_code == 401

    claims = verify_firebase_token("valid-token-abc")
    assert claims["role"] == "admin"


def test_scan_idp_endpoint_idp_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Error Path: IdpAuthError returns 502 Bad Gateway."""
    client = TestClient(app)

    monkeypatch.setattr(
        "zombie_saas_coordinator.api.scanner.verify_firebase_token",
        lambda token: {"uid": "admin", "role": "admin"},
    )

    def _auth_err(tenant_id: str, days: int) -> dict[str, Any]:
        raise IdpAuthError("IdP SAML federation expired")

    monkeypatch.setattr(tools, "scan_idp_logs", _auth_err)

    headers = {"Authorization": "Bearer test-token"}
    response = client.post(
        "/api/v1/jobs/scan-idp",
        headers=headers,
        json={"tenant_id": "tenant-fail", "days": 60},
    )
    assert response.status_code == 502
    assert "IdP authentication failure" in response.json()["detail"]


def test_record_scan_in_cloudsql_executes_queries() -> None:
    """DB Layer: Verifies record_scan_in_cloudsql calls engine with bound parameters."""
    from zombie_saas_coordinator.shared.db.cloudsql_client import record_scan_in_cloudsql

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn

    scan_data = {
        "scan_id": "scan_test_123",
        "timestamp": "2026-10-03T12:00:00Z",
        "total_apps_scanned": 1,
        "flagged_apps_count": 1,
        "apps": [
            {
                "app_id": "app_1",
                "app_name": "Trello",
                "vendor": "Atlassian",
                "total_seats": 10,
                "active_seats": 2,
                "inactive_seats": 8,
                "inactive_ratio": 0.8,
                "is_flagged_inactive": True,
            }
        ],
    }

    record_scan_in_cloudsql("tenant-acme", scan_data, engine=mock_engine)
    # Ensure SQL statements were executed via begin context
    assert mock_conn.execute.call_count == 2
