"""Tests for US-5: 3-Tier HITL Execution Gates and lifecycle management."""

# ruff: noqa: N999, S106, S107

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from zombie_saas_coordinator.main import app
from zombie_saas_coordinator.shared.approvals.approvals import (
    check_approval_status,
    revoke_approval,
)
from zombie_saas_coordinator.shared.auth.firebase_auth import verify_firebase_auth_token
from zombie_saas_coordinator.shared.models.approval import (
    ApprovalGateType,
    ApprovalRecord,
)
from zombie_saas_coordinator.shared.models.proposal import (
    ConsolidationProposal,
    ProposalStatus,
    RecommendationType,
    RiskAssessment,
    SavingsBreakdown,
)


def _get_dummy_proposal(
    proposal_id: str = "prop-us5-001",
    status: ProposalStatus = ProposalStatus.PENDING,
    expires_delta_days: int = 7,
) -> ConsolidationProposal:
    return ConsolidationProposal(
        proposal_id=proposal_id,
        app_id="app-trello-123",
        app_name="Trello",
        target_app="Asana",
        tenant_id="tenant-001",
        savings=SavingsBreakdown(
            seats=10,
            monthly_cost=400.0,
            cost_per_seat_monthly=40.0,
            estimated_annual_savings=4800.0,
        ),
        risk=RiskAssessment(
            risk_score=20,
            active_user_count=8,
            inactive_ratio=0.2,
        ),
        redundancy_score=80,
        dependencies=["Slack", "Google Drive"],
        recommendation=RecommendationType.PROCEED_CONSOLIDATION,
        summary="Proposal for migrating Trello to Asana",
        status=status,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=expires_delta_days),
    )


def _mock_firestore(
    proposal_data: dict[str, Any] | None = None,
    approval_data: dict[str, Any] | None = None,
    exists: bool = True,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    client = MagicMock()
    proposal_snapshot = MagicMock()
    proposal_snapshot.exists = exists
    proposal_snapshot.to_dict.return_value = proposal_data or _get_dummy_proposal().model_dump(
        mode="json"
    )

    proposal_doc = MagicMock()
    proposal_doc.get.return_value = proposal_snapshot
    proposal_doc.update.return_value = None
    proposal_doc.set.return_value = None

    approval_snapshot = MagicMock()
    approval_snapshot.exists = approval_data is not None
    approval_snapshot.to_dict.return_value = approval_data

    approval_doc = MagicMock()
    approval_doc.get.return_value = approval_snapshot
    approval_doc.set.return_value = None
    approval_doc.update.return_value = None
    approval_snapshot.reference = approval_doc

    def collection(name: str) -> MagicMock:
        coll = MagicMock()
        if name == "consolidation_proposals":
            coll.document.return_value = proposal_doc
        elif name == "approvals":
            coll.document.return_value = approval_doc
            where_mock = MagicMock()
            where_mock.get.return_value = [approval_snapshot] if approval_data else []
            coll.where.return_value = where_mock
        else:
            coll.document.return_value = MagicMock()
        return coll

    client.collection.side_effect = collection
    return client, proposal_doc, approval_doc


# ─────────────────────────────────────────────────────────────────────────────
# 1. Firebase Authentication & SSO Claim Verification Unit Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_verify_firebase_auth_token_happy_path() -> None:
    """Valid Firebase token with CISO role succeeds."""
    mock_decoded = {
        "uid": "ciso-user-123",
        "email": "ciso@enterprise.com",
        "name": "Jane CISO",
        "roles": ["ciso", "security_admin"],
        "exp": (datetime.now(UTC) + timedelta(hours=1)).timestamp(),
    }
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded):
        result = verify_firebase_auth_token("valid-firebase-jwt", required_roles=["ciso", "admin"])
        assert result["uid"] == "ciso-user-123"
        assert result["email"] == "ciso@enterprise.com"
        assert "ciso" in result["roles"]


def test_verify_firebase_auth_token_missing_token() -> None:
    """Empty or whitespace token raises 401 Unauthorized."""
    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_auth_token("")
    assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info2:
        verify_firebase_auth_token("   ")
    assert exc_info2.value.status_code == 401


def test_verify_firebase_auth_token_invalid_jwt() -> None:
    """Invalid or expired JWT raises 401 Unauthorized."""
    with patch("firebase_admin.auth.verify_id_token", side_effect=Exception("Token expired")):
        with pytest.raises(HTTPException) as exc_info:
            verify_firebase_auth_token("bad-token")
        assert exc_info.value.status_code == 401
        assert "Invalid or expired Firebase Auth token" in exc_info.value.detail


def test_verify_firebase_auth_token_insufficient_roles() -> None:
    """Token lacking CISO or IT-Ops role raises 403 Forbidden."""
    mock_decoded = {
        "uid": "viewer-user-456",
        "email": "viewer@enterprise.com",
        "roles": ["viewer"],
    }
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded):
        with pytest.raises(HTTPException) as exc_info:
            verify_firebase_auth_token(
                "viewer-token", required_roles=["ciso", "it_ops", "admin"]
            )
        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# 2. Data Models & 7-Day TTL Expiration Window
# ─────────────────────────────────────────────────────────────────────────────


def test_approval_record_ttl_calculation() -> None:
    """ApprovalRecord automatically defaults expires_at to approved_at + 7 days."""
    now = datetime.now(UTC)
    record = ApprovalRecord(
        proposal_id="prop-001",
        gate_type=ApprovalGateType.PERMISSION_TO_MIGRATE,
        approved=True,
        approver_id="user-ciso-1",
        approver_email="ciso@example.com",
        roles=["ciso"],
        approved_at=now,
    )
    assert record.expires_at == now + timedelta(days=7)
    assert record.is_active is True
    assert record.revoked is False


def test_approval_record_expired_check() -> None:
    """ApprovalRecord accurately detects when 7-day TTL has elapsed."""
    past = datetime.now(UTC) - timedelta(days=8)
    record = ApprovalRecord(
        proposal_id="prop-001",
        gate_type=ApprovalGateType.PERMISSION_TO_MIGRATE,
        approved=True,
        approver_id="user-ciso-1",
        approver_email="ciso@example.com",
        roles=["ciso"],
        approved_at=past,
        expires_at=past + timedelta(days=7),
    )
    assert record.is_expired is True
    assert record.is_active is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Root Orchestrator HITL Tools (check_approval_status, revoke_approval)
# ─────────────────────────────────────────────────────────────────────────────


_FS_CLIENT_PATCH = "zombie_saas_coordinator.api.approvals._get_firestore_client"


def test_check_approval_status_unapproved_blocks_delegation() -> None:
    """If no approval exists or proposal is pending, check_approval_status returns false."""
    dummy_prop = _get_dummy_proposal(status=ProposalStatus.PENDING)
    client, _, _ = _mock_firestore(
        proposal_data=dummy_prop.model_dump(mode="json"),
        approval_data=None,
    )
    with patch("zombie_saas_coordinator.shared.approvals.approvals._get_firestore_client", return_value=client):
        result = check_approval_status(
            proposal_id="prop-us5-001",
            required_gate=ApprovalGateType.PERMISSION_TO_MIGRATE.value,
        )
        assert result["approved"] is False
        assert result["status"] in ("PENDING", "UNAPPROVED", "NOT_FOUND")
        assert "delegate" not in result or result.get("can_delegate") is False


def test_check_approval_status_approved_permits_delegation() -> None:
    """Valid non-expired approval permits orchestrator delegation to downstream agents."""
    now = datetime.now(UTC)
    approval_dict = {
        "proposal_id": "prop-us5-001",
        "gate_type": ApprovalGateType.PERMISSION_TO_MIGRATE.value,
        "approved": True,
        "approver_id": "user-ciso-99",
        "approver_email": "ciso@company.com",
        "roles": ["ciso"],
        "approved_at": now.isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
        "revoked": False,
        "revoked_at": None,
        "revoked_by": None,
        "revoke_reason": None,
    }
    client, _, _ = _mock_firestore(
        proposal_data=_get_dummy_proposal(status=ProposalStatus.APPROVED).model_dump(mode="json"),
        approval_data=approval_dict,
    )
    with patch("zombie_saas_coordinator.shared.approvals.approvals._get_firestore_client", return_value=client):
        result = check_approval_status(
            proposal_id="prop-us5-001",
            required_gate=ApprovalGateType.PERMISSION_TO_MIGRATE.value,
        )
        assert result["approved"] is True
        assert result["approver"] == "user-ciso-99"
        assert result["is_expired"] is False
        assert result["can_delegate"] is True


def test_check_approval_status_expired_blocks_delegation() -> None:
    """Approval past 7-day TTL returns approved=False, is_expired=True, blocking execution."""
    past = datetime.now(UTC) - timedelta(days=8)
    approval_dict = {
        "proposal_id": "prop-us5-001",
        "gate_type": ApprovalGateType.PERMISSION_TO_MIGRATE.value,
        "approved": True,
        "approver_id": "user-ciso-99",
        "approver_email": "ciso@company.com",
        "roles": ["ciso"],
        "approved_at": past.isoformat(),
        "expires_at": (past + timedelta(days=7)).isoformat(),
        "revoked": False,
    }
    client, _, _ = _mock_firestore(
        proposal_data=_get_dummy_proposal(status=ProposalStatus.APPROVED).model_dump(mode="json"),
        approval_data=approval_dict,
    )
    with patch("zombie_saas_coordinator.shared.approvals.approvals._get_firestore_client", return_value=client):
        result = check_approval_status(
            proposal_id="prop-us5-001",
            required_gate=ApprovalGateType.PERMISSION_TO_MIGRATE.value,
        )
        assert result["approved"] is False
        assert result["is_expired"] is True
        assert result["can_delegate"] is False


def test_revoke_approval_tool_halts_pipeline() -> None:
    """revoke_approval tool immediately halts all gate approvals and updates state."""
    client, _, approval_doc = _mock_firestore(
        proposal_data=_get_dummy_proposal(status=ProposalStatus.APPROVED).model_dump(mode="json"),
        approval_data={
            "proposal_id": "prop-us5-001",
            "approved": True,
            "revoked": False,
        },
    )
    mock_audit = MagicMock()
    with (
        patch("zombie_saas_coordinator.shared.approvals.approvals._get_firestore_client", return_value=client),
        patch("zombie_saas_coordinator.shared.approvals.approvals._get_audit_logger", return_value=mock_audit),
    ):
        result = revoke_approval(
            proposal_id="prop-us5-001",
            revoker_info={"uid": "ciso-admin", "email": "ciso@company.com"},
            reason="Suspected credential leak on source board",
        )
        assert result["revoked"] is True
        assert result["proposal_id"] == "prop-us5-001"
        assert approval_doc.update.called
        assert mock_audit.log_struct.called


def test_revoke_approval_rejects_anonymous_caller() -> None:
    """revoke_approval raises ValueError if revoker_info has no uid (AC-5.6 prompt injection guard)."""
    with pytest.raises(ValueError, match="non-empty 'uid'"):
        revoke_approval(
            proposal_id="prop-us5-001",
            revoker_info={"email": "nobody@unknown.com"},  # no uid
            reason="Some reason",
        )

    with pytest.raises(ValueError, match="non-empty 'uid'"):
        revoke_approval(
            proposal_id="prop-us5-001",
            revoker_info={"uid": ""},  # empty uid
            reason="Some reason",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. API Endpoints (POST authorize, POST revoke, GET status)
# ─────────────────────────────────────────────────────────────────────────────


def test_api_authorize_proposal_happy_path() -> None:
    """POST /api/v1/approvals/{proposal_id}/authorize with valid token records approval."""
    client = TestClient(app)
    fs_client, proposal_doc, approval_doc = _mock_firestore(
        proposal_data=_get_dummy_proposal(status=ProposalStatus.PENDING).model_dump(mode="json"),
        approval_data=None,
    )
    mock_audit = MagicMock()
    mock_decoded = {
        "uid": "ciso-auth-01",
        "email": "ciso@corp.internal",
        "roles": ["ciso"],
    }

    with (
        patch(_FS_CLIENT_PATCH, return_value=fs_client),
        patch("zombie_saas_coordinator.api.approvals._get_audit_logger", return_value=mock_audit),
        patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded),
        patch("zombie_saas_coordinator.api.approvals.record_approval_in_cloudsql") as mock_sql,
    ):
        response = client.post(
            "/api/v1/approvals/prop-us5-001/authorize",
            json={
                "firebase_token": "valid-ciso-token",
                "gate_type": "PERMISSION_TO_MIGRATE",
                "notes": "Authorized after architecture review",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["approved"] is True
        assert data["approver_id"] == "ciso-auth-01"
        assert data["gate_type"] == "PERMISSION_TO_MIGRATE"
        assert proposal_doc.update.called
        assert approval_doc.set.called
        assert mock_audit.log_struct.called
        assert mock_sql.called


def test_api_authorize_proposal_unauthorized_token() -> None:
    """POST /api/v1/approvals/{proposal_id}/authorize with bad token returns 401."""
    client = TestClient(app)
    with patch("firebase_admin.auth.verify_id_token", side_effect=Exception("Invalid signature")):
        response = client.post(
            "/api/v1/approvals/prop-us5-001/authorize",
            json={
                "firebase_token": "fake-bad-token",
                "gate_type": "PERMISSION_TO_MIGRATE",
            },
        )
        assert response.status_code == 401


def test_api_authorize_proposal_forbidden_claims() -> None:
    """POST /api/v1/approvals/{proposal_id}/authorize without CISO/IT-Ops claims returns 403."""
    client = TestClient(app)
    mock_decoded = {
        "uid": "regular-user",
        "email": "user@corp.internal",
        "roles": ["developer"],
    }
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded):
        response = client.post(
            "/api/v1/approvals/prop-us5-001/authorize",
            json={
                "firebase_token": "dev-token",
                "gate_type": "PERMISSION_TO_MIGRATE",
            },
        )
        assert response.status_code == 403


def test_api_authorize_proposal_not_found() -> None:
    """POST /api/v1/approvals/{proposal_id}/authorize for nonexistent proposal returns 404."""
    client = TestClient(app)
    fs_client, _, _ = _mock_firestore(exists=False)
    mock_decoded = {"uid": "ciso-01", "roles": ["ciso"]}

    with (
        patch(_FS_CLIENT_PATCH, return_value=fs_client),
        patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded),
    ):
        response = client.post(
            "/api/v1/approvals/non-existent-prop/authorize",
            json={"firebase_token": "ciso-token", "gate_type": "PERMISSION_TO_MIGRATE"},
        )
        assert response.status_code == 404


def test_api_authorize_proposal_conflict_if_same_gate_already_approved() -> None:
    """Authorizing the same gate twice returns 409 — but a different gate must succeed (AC-5.1)."""
    client = TestClient(app)
    # Same gate already approved
    fs_client, _, _ = _mock_firestore(
        proposal_data=_get_dummy_proposal(status=ProposalStatus.APPROVED).model_dump(mode="json"),
        approval_data={"approved": True, "revoked": False},
    )
    mock_decoded = {"uid": "ciso-01", "roles": ["ciso"]}

    with (
        patch(_FS_CLIENT_PATCH, return_value=fs_client),
        patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded),
    ):
        response = client.post(
            "/api/v1/approvals/prop-us5-001/authorize",
            json={"firebase_token": "ciso-token", "gate_type": "PERMISSION_TO_MIGRATE"},
        )
        assert response.status_code == 409


def test_api_authorize_second_gate_allowed_after_first_gate_approved() -> None:
    """Authorizing a second gate on an already-APPROVED proposal must NOT return 409 (AC-5.1)."""
    client = TestClient(app)
    # Proposal is APPROVED (first gate done) but the DISPOSE gate doc does not exist yet
    fs_client, _, _ = _mock_firestore(
        proposal_data=_get_dummy_proposal(status=ProposalStatus.APPROVED).model_dump(mode="json"),
        approval_data=None,  # no per-gate doc for DISPOSE yet
    )
    mock_decoded = {"uid": "ciso-01", "email": "ciso@corp.internal", "roles": ["ciso"]}
    mock_audit = MagicMock()

    with (
        patch(_FS_CLIENT_PATCH, return_value=fs_client),
        patch("zombie_saas_coordinator.api.approvals._get_audit_logger", return_value=mock_audit),
        patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded),
        patch("zombie_saas_coordinator.api.approvals.record_approval_in_cloudsql"),
    ):
        response = client.post(
            "/api/v1/approvals/prop-us5-001/authorize",
            json={"firebase_token": "ciso-token", "gate_type": "PERMISSION_TO_DISPOSE"},
        )
        # Must be 200 — proposal.status == APPROVED should NOT block a different gate
        assert response.status_code == 200
        data = response.json()
        assert data["gate_type"] == "PERMISSION_TO_DISPOSE"


def test_api_revoke_proposal_happy_path() -> None:
    """POST /api/v1/approvals/{proposal_id}/revoke halts and updates record."""
    client = TestClient(app)
    fs_client, proposal_doc, approval_doc = _mock_firestore(
        proposal_data=_get_dummy_proposal(status=ProposalStatus.APPROVED).model_dump(mode="json"),
        approval_data={"approved": True, "revoked": False},
    )
    mock_audit = MagicMock()
    mock_decoded = {"uid": "it-ops-01", "email": "itops@corp.internal", "roles": ["it_ops"]}

    with (
        patch(_FS_CLIENT_PATCH, return_value=fs_client),
        patch("zombie_saas_coordinator.api.approvals._get_audit_logger", return_value=mock_audit),
        patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded),
        patch("zombie_saas_coordinator.api.approvals.record_revocation_in_cloudsql") as mock_sql,
    ):
        response = client.post(
            "/api/v1/approvals/prop-us5-001/revoke",
            json={
                "firebase_token": "itops-token",
                "reason": "Discovery of unmapped Zapier dependency",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["revoked"] is True
        assert approval_doc.update.called
        assert mock_audit.log_struct.called
        assert mock_sql.called


def test_api_revoke_proposal_missing_reason() -> None:
    """POST /api/v1/approvals/{proposal_id}/revoke with empty reason returns 400."""
    client = TestClient(app)
    mock_decoded = {"uid": "it-ops-01", "roles": ["it_ops"]}
    with patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded):
        response = client.post(
            "/api/v1/approvals/prop-us5-001/revoke",
            json={"firebase_token": "itops-token", "reason": "   "},
        )
        assert response.status_code == 400


def test_api_get_approval_status_requires_auth() -> None:
    """GET /api/v1/approvals/{proposal_id} without Authorization header returns 422."""
    client = TestClient(app)
    response = client.get("/api/v1/approvals/prop-us5-001")
    assert response.status_code == 422  # FastAPI missing header → 422 Unprocessable Entity


def test_api_get_approval_status() -> None:
    """GET /api/v1/approvals/{proposal_id} retrieves current gate and expiration details."""
    client = TestClient(app)
    now = datetime.now(UTC)
    fs_client, _, _ = _mock_firestore(
        proposal_data=_get_dummy_proposal(status=ProposalStatus.APPROVED).model_dump(mode="json"),
        approval_data={
            "proposal_id": "prop-us5-001",
            "gate_type": "PERMISSION_TO_MIGRATE",
            "approved": True,
            "approver_id": "ciso-1",
            "approver_email": "ciso@corp.internal",
            "approved_at": now.isoformat(),
            "expires_at": (now + timedelta(days=7)).isoformat(),
            "revoked": False,
        },
    )
    mock_decoded = {"uid": "any-user", "roles": ["viewer"]}
    with (
        patch(_FS_CLIENT_PATCH, return_value=fs_client),
        patch("firebase_admin.auth.verify_id_token", return_value=mock_decoded),
    ):
        response = client.get(
            "/api/v1/approvals/prop-us5-001",
            headers={"Authorization": "Bearer valid-viewer-token"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["proposal_id"] == "prop-us5-001"
        assert data["approved"] is True
        assert data["is_expired"] is False
        assert data["revoked"] is False
