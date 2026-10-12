"""Tests for US-12: Fail-Safe Quarantine and Disposal.

Covers:
- AC-12.1: Default action after migration is SOURCE_QUARANTINED (retention of source data).
- AC-12.2: Disposal is blocked if validation exceptions, legal holds,
  or incomplete migrations remain unresolved.
- AC-12.3: Requires a separate, multi-signature approval (DISPOSAL_APPROVED)
  before verifiable destruction.
"""

# ruff: noqa: N999, S106, S107

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from zombie_saas_coordinator.main import app
from zombie_saas_coordinator.shared.models.quarantine import (
    DisposalCertificate,
    DisposalSignature,
    QuarantineRecord,
    QuarantineStatus,
    ValidationExceptionItem,
)
from zombie_saas_coordinator.shared.quarantine.service import (
    check_disposal_eligibility,
    execute_verifiable_disposal,
    quarantine_source_data,
    resolve_validation_exception,
    set_legal_hold,
    submit_disposal_signature,
)


def _get_dummy_quarantine_record(
    proposal_id: str = "prop-us12-001",
    status: QuarantineStatus = QuarantineStatus.SOURCE_QUARANTINED,
    legal_hold: bool = False,
    migration_completed: bool = True,
    exceptions: list[ValidationExceptionItem] | None = None,
    signatures: list[DisposalSignature] | None = None,
) -> QuarantineRecord:
    now = datetime.now(UTC)
    return QuarantineRecord(
        proposal_id=proposal_id,
        app_id="app-trello-123",
        app_name="Trello",
        status=status,
        quarantined_at=now,
        retention_days=90,
        expires_at=now + timedelta(days=90),
        legal_hold=legal_hold,
        legal_hold_reason="Active litigation hold" if legal_hold else None,
        migration_completed=migration_completed,
        unresolved_exceptions=exceptions or [],
        signatures=signatures or [],
        required_signatures=2,
    )


def _mock_quarantine_firestore(
    record_data: dict[str, Any] | None = None,
    proposal_data: dict[str, Any] | None = None,
    exists: bool = True,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    client = MagicMock()

    record_snap = MagicMock()
    record_snap.exists = exists
    record_snap.to_dict.return_value = record_data or _get_dummy_quarantine_record().model_dump(
        mode="json"
    )

    record_doc = MagicMock()
    record_doc.get.return_value = record_snap
    record_doc.set.return_value = None
    record_doc.update.return_value = None

    prop_snap = MagicMock()
    prop_snap.exists = True
    prop_snap.to_dict.return_value = proposal_data or {
        "proposal_id": "prop-us12-001",
        "app_id": "app-trello-123",
        "app_name": "Trello",
        "status": "APPROVED",
    }

    prop_doc = MagicMock()
    prop_doc.get.return_value = prop_snap

    def collection(name: str) -> MagicMock:
        coll = MagicMock()
        if name == "quarantine_records":
            coll.document.return_value = record_doc
        elif name == "consolidation_proposals":
            coll.document.return_value = prop_doc
        elif name == "disposal_certificates":
            cert_doc = MagicMock()
            cert_doc.set.return_value = None
            coll.document.return_value = cert_doc
        else:
            coll.document.return_value = MagicMock()
        return coll

    client.collection.side_effect = collection
    return client, record_doc, prop_doc


# ─────────────────────────────────────────────────────────────────────────────
# 1. AC-12.1: Default Action is SOURCE_QUARANTINED (Retention of Source Data)
# ─────────────────────────────────────────────────────────────────────────────


def test_quarantine_source_data_defaults_to_source_quarantined() -> None:
    """Default post-migration state is SOURCE_QUARANTINED with 90-day retention."""
    mock_client, mock_doc, _ = _mock_quarantine_firestore(exists=False)

    with (
        patch(
            "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
            return_value=mock_client,
        ),
        patch(
            "zombie_saas_coordinator.shared.quarantine.service.record_quarantine_in_cloudsql"
        ) as mock_sql,
        patch("zombie_saas_coordinator.shared.quarantine.service._get_audit_logger") as mock_audit,
    ):
        rec = quarantine_source_data(
            proposal_id="prop-us12-001",
            source_metadata={"app_id": "app-trello-123", "app_name": "Trello"},
            retention_days=90,
        )

        assert rec.status == QuarantineStatus.SOURCE_QUARANTINED
        assert rec.retention_days == 90
        assert rec.legal_hold is False
        assert rec.migration_completed is True
        assert mock_doc.set.called
        assert mock_sql.called
        assert mock_audit.return_value.log_struct.called


def test_quarantine_source_data_proposal_not_found_raises() -> None:
    """Non-existent proposal raises 404."""
    mock_client = MagicMock()
    prop_doc = MagicMock()
    prop_doc.get.return_value = MagicMock(exists=False)
    mock_client.collection.return_value.document.return_value = prop_doc

    with patch(
        "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
        return_value=mock_client,
    ):
        with pytest.raises(HTTPException) as exc_info:
            quarantine_source_data(proposal_id="nonexistent-prop")
        assert exc_info.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 2. AC-12.2: Disposal is Blocked on Exceptions, Legal Holds, Incomplete Migrations
# ─────────────────────────────────────────────────────────────────────────────


def test_disposal_blocked_when_legal_hold_is_active() -> None:
    """Active legal hold blocks disposal eligibility and execution."""
    rec = _get_dummy_quarantine_record(
        status=QuarantineStatus.DISPOSAL_APPROVED,
        legal_hold=True,
    )
    mock_client, _, _ = _mock_quarantine_firestore(record_data=rec.model_dump(mode="json"))

    with patch(
        "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
        return_value=mock_client,
    ):
        eligibility = check_disposal_eligibility("prop-us12-001")
        assert eligibility["eligible"] is False
        assert any("Legal hold" in b for b in eligibility["blockers"])

        with pytest.raises(HTTPException) as exc_info:
            execute_verifiable_disposal(
                "prop-us12-001",
                executor_info={"uid": "ciso-user", "email": "ciso@co.com"},
            )
        assert exc_info.value.status_code == 400
        assert "Legal hold active" in exc_info.value.detail


def test_disposal_blocked_when_unresolved_validation_exceptions_exist() -> None:
    """Unresolved validation exceptions block disposal eligibility and execution."""
    rec = _get_dummy_quarantine_record(
        status=QuarantineStatus.DISPOSAL_APPROVED,
        exceptions=[
            ValidationExceptionItem(
                exception_id="ex-1",
                description="Checklist items checksum mismatch",
                severity="HIGH",
                resolved=False,
            )
        ],
    )
    mock_client, _, _ = _mock_quarantine_firestore(record_data=rec.model_dump(mode="json"))

    with patch(
        "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
        return_value=mock_client,
    ):
        eligibility = check_disposal_eligibility("prop-us12-001")
        assert eligibility["eligible"] is False
        assert any("validation exception" in b.lower() for b in eligibility["blockers"])

        with pytest.raises(HTTPException) as exc_info:
            execute_verifiable_disposal(
                "prop-us12-001",
                executor_info={"uid": "ciso-user", "email": "ciso@co.com"},
            )
        assert exc_info.value.status_code == 400
        assert "validation exception" in exc_info.value.detail.lower()


def test_disposal_blocked_when_migration_incomplete() -> None:
    """Incomplete migration blocks disposal eligibility and execution."""
    rec = _get_dummy_quarantine_record(
        status=QuarantineStatus.DISPOSAL_APPROVED,
        migration_completed=False,
    )
    mock_client, _, _ = _mock_quarantine_firestore(record_data=rec.model_dump(mode="json"))

    with patch(
        "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
        return_value=mock_client,
    ):
        eligibility = check_disposal_eligibility("prop-us12-001")
        assert eligibility["eligible"] is False
        assert any("incomplete" in b.lower() for b in eligibility["blockers"])

        with pytest.raises(HTTPException) as exc_info:
            execute_verifiable_disposal(
                "prop-us12-001",
                executor_info={"uid": "ciso-user", "email": "ciso@co.com"},
            )
        assert exc_info.value.status_code == 400
        assert "incomplete" in exc_info.value.detail.lower()


def test_resolve_validation_exception_clears_blocker() -> None:
    """Resolving an exception marks it resolved and removes it from active blockers."""
    ex = ValidationExceptionItem(
        exception_id="ex-101",
        description="Attachment file size diff",
        severity="MEDIUM",
        resolved=False,
    )
    rec = _get_dummy_quarantine_record(exceptions=[ex])
    mock_client, mock_doc, _ = _mock_quarantine_firestore(record_data=rec.model_dump(mode="json"))

    with patch(
        "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
        return_value=mock_client,
    ):
        res = resolve_validation_exception(
            proposal_id="prop-us12-001",
            exception_id="ex-101",
            resolution_notes="Manual verification confirmed file parity.",
            resolved_by="qa-lead-user",
        )
        assert res["resolved"] is True
        assert res["remaining_unresolved_count"] == 0
        assert mock_doc.set.called


def test_set_and_release_legal_hold() -> None:
    """Operators can apply and release legal holds."""
    rec = _get_dummy_quarantine_record(legal_hold=False)
    mock_client, mock_doc, _ = _mock_quarantine_firestore(record_data=rec.model_dump(mode="json"))

    with patch(
        "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
        return_value=mock_client,
    ):
        # Set legal hold
        updated = set_legal_hold(
            proposal_id="prop-us12-001",
            operator_info={"uid": "legal-user", "email": "legal@co.com"},
            legal_hold=True,
            reason="Subpoena received",
        )
        assert updated.legal_hold is True
        assert updated.legal_hold_reason == "Subpoena received"

        # Release legal hold
        mock_doc.get.return_value.to_dict.return_value = updated.model_dump(mode="json")
        released = set_legal_hold(
            proposal_id="prop-us12-001",
            operator_info={"uid": "legal-user", "email": "legal@co.com"},
            legal_hold=False,
            reason="Case dismissed",
        )
        assert released.legal_hold is False
        assert released.legal_hold_reason is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. AC-12.3: Multi-Signature Approval & Verifiable Destruction
# ─────────────────────────────────────────────────────────────────────────────


def test_multi_signature_quorum_progression() -> None:
    """First signature moves to DISPOSAL_PENDING_APPROVAL; second moves to DISPOSAL_APPROVED."""
    rec = _get_dummy_quarantine_record()
    mock_client, mock_doc, _ = _mock_quarantine_firestore(record_data=rec.model_dump(mode="json"))

    with (
        patch(
            "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
            return_value=mock_client,
        ),
        patch(
            "zombie_saas_coordinator.shared.quarantine.service.record_approval_in_cloudsql"
        ) as mock_sql,
    ):
        # First signer: CISO
        sig1 = submit_disposal_signature(
            proposal_id="prop-us12-001",
            signer_info={"uid": "ciso-uid-1", "email": "ciso@co.com", "role": "ciso"},
            notes="CISO disposal approval granted.",
        )
        assert sig1["status"] == QuarantineStatus.DISPOSAL_PENDING_APPROVAL.value
        assert sig1["signature_count"] == 1
        assert sig1["quorum_reached"] is False

        # Attempt duplicate signature by same user -> Conflict
        rec.signatures.append(
            DisposalSignature(
                signer_id="ciso-uid-1",
                signer_email="ciso@co.com",
                role="ciso",
                signed_at=datetime.now(UTC),
                notes="test",
            )
        )
        rec.status = QuarantineStatus.DISPOSAL_PENDING_APPROVAL
        mock_doc.get.return_value.to_dict.return_value = rec.model_dump(mode="json")

        with pytest.raises(HTTPException) as exc_info:
            submit_disposal_signature(
                proposal_id="prop-us12-001",
                signer_info={"uid": "ciso-uid-1", "email": "ciso@co.com", "role": "ciso"},
            )
        assert exc_info.value.status_code == 409
        assert "already submitted a signature" in exc_info.value.detail

        # Second signer: Compliance Officer -> DISPOSAL_APPROVED
        sig2 = submit_disposal_signature(
            proposal_id="prop-us12-001",
            signer_info={
                "uid": "compliance-uid-2",
                "email": "compliance@co.com",
                "role": "compliance_officer",
            },
            notes="Compliance sign-off complete.",
        )
        assert sig2["status"] == QuarantineStatus.DISPOSAL_APPROVED.value
        assert sig2["signature_count"] == 2
        assert sig2["quorum_reached"] is True
        assert mock_sql.called


def test_verifiable_disposal_execution_generates_certificate_and_hash() -> None:
    """Verifiable disposal creates cryptographic SHA-256 certificate and destroys source."""
    sig1 = DisposalSignature(
        signer_id="ciso-uid-1",
        signer_email="ciso@co.com",
        role="ciso",
        signed_at=datetime.now(UTC),
    )
    sig2 = DisposalSignature(
        signer_id="compliance-uid-2",
        signer_email="compliance@co.com",
        role="compliance_officer",
        signed_at=datetime.now(UTC),
    )
    rec = _get_dummy_quarantine_record(
        status=QuarantineStatus.DISPOSAL_APPROVED,
        signatures=[sig1, sig2],
    )
    mock_client, mock_doc, _ = _mock_quarantine_firestore(record_data=rec.model_dump(mode="json"))

    with (
        patch(
            "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
            return_value=mock_client,
        ),
        patch(
            "zombie_saas_coordinator.shared.quarantine.service.record_disposal_in_cloudsql"
        ) as mock_sql,
        patch("zombie_saas_coordinator.shared.quarantine.service._get_audit_logger") as mock_audit,
    ):
        cert = execute_verifiable_disposal(
            proposal_id="prop-us12-001",
            executor_info={"uid": "executor-uid-99", "email": "ops@co.com"},
        )

        assert isinstance(cert, DisposalCertificate)
        assert cert.status == "VERIFIED_DESTROYED"
        assert len(cert.verification_hash) == 64  # SHA-256 hex string
        assert len(cert.signers) == 2
        assert mock_doc.set.called
        assert mock_sql.called
        assert mock_audit.return_value.log_struct.called


def test_disposal_execution_blocked_without_disposal_approved_status() -> None:
    """Cannot execute disposal while still in SOURCE_QUARANTINED or PENDING."""
    rec = _get_dummy_quarantine_record(status=QuarantineStatus.SOURCE_QUARANTINED)
    mock_client, _, _ = _mock_quarantine_firestore(record_data=rec.model_dump(mode="json"))

    with patch(
        "zombie_saas_coordinator.shared.quarantine.service._get_firestore_client",
        return_value=mock_client,
    ):
        with pytest.raises(HTTPException) as exc_info:
            execute_verifiable_disposal(
                "prop-us12-001",
                executor_info={"uid": "ciso-user", "email": "ciso@co.com"},
            )
        assert exc_info.value.status_code == 400
        assert "DISPOSAL_APPROVED" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# 4. API Endpoints Integration Tests (Cloud Run Router)
# ─────────────────────────────────────────────────────────────────────────────


client = TestClient(app)


def test_api_quarantine_source_endpoint() -> None:
    """POST /api/v1/quarantine/{id}/quarantine puts proposal into quarantine."""
    mock_user = {
        "uid": "ops-admin",
        "email": "ops@co.com",
        "roles": ["admin", "it_ops"],
    }
    mock_record = _get_dummy_quarantine_record()

    with (
        patch(
            "zombie_saas_coordinator.api.quarantine.verify_firebase_auth_token",
            return_value=mock_user,
        ),
        patch(
            "zombie_saas_coordinator.api.quarantine.quarantine_source_data",
            return_value=mock_record,
        ),
    ):
        resp = client.post(
            "/api/v1/quarantine/prop-us12-001/quarantine",
            json={"firebase_token": "valid-token", "retention_days": 90},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "SOURCE_QUARANTINED"


def test_api_get_quarantine_status_endpoint() -> None:
    """GET /api/v1/quarantine/{id} returns status and eligibility."""
    mock_record = _get_dummy_quarantine_record()
    mock_eligibility = {"eligible": True, "blockers": []}

    with (
        patch(
            "zombie_saas_coordinator.api.quarantine.get_quarantine_record", return_value=mock_record
        ),
        patch(
            "zombie_saas_coordinator.api.quarantine.check_disposal_eligibility",
            return_value=mock_eligibility,
        ),
    ):
        resp = client.get("/api/v1/quarantine/prop-us12-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["record"]["proposal_id"] == "prop-us12-001"
        assert data["eligibility"]["eligible"] is True


def test_api_disposal_sign_and_execute_endpoints() -> None:
    """POST sign and POST execute endpoints verify tokens and invoke service."""
    mock_ciso = {
        "uid": "ciso-uid",
        "email": "ciso@co.com",
        "roles": ["ciso"],
    }
    mock_sign_result = {
        "proposal_id": "prop-us12-001",
        "status": "DISPOSAL_PENDING_APPROVAL",
        "signature_count": 1,
        "quorum_reached": False,
    }
    mock_cert = DisposalCertificate(
        certificate_id="cert-123",
        proposal_id="prop-us12-001",
        app_id="app-1",
        app_name="Trello",
        disposed_at=datetime.now(UTC),
        executor_id="ciso-uid",
        executor_email="ciso@co.com",
        signers=[],
        verification_hash="a" * 64,
        items_purged_count=150,
        status="VERIFIED_DESTROYED",
    )

    with (
        patch(
            "zombie_saas_coordinator.api.quarantine.verify_firebase_auth_token",
            return_value=mock_ciso,
        ),
        patch(
            "zombie_saas_coordinator.api.quarantine.submit_disposal_signature",
            return_value=mock_sign_result,
        ),
        patch(
            "zombie_saas_coordinator.api.quarantine.execute_verifiable_disposal",
            return_value=mock_cert,
        ),
    ):
        # Sign endpoint
        resp_sign = client.post(
            "/api/v1/quarantine/prop-us12-001/disposal/sign",
            json={"firebase_token": "valid-token", "notes": "Approved by CISO"},
        )
        assert resp_sign.status_code == 200
        assert resp_sign.json()["signature_count"] == 1

        # Execute endpoint
        resp_exec = client.post(
            "/api/v1/quarantine/prop-us12-001/disposal/execute",
            json={"firebase_token": "valid-token"},
        )
        assert resp_exec.status_code == 200
        assert resp_exec.json()["status"] == "VERIFIED_DESTROYED"


def test_api_legal_hold_and_resolve_exception_endpoints() -> None:
    """POST legal-hold and POST resolve exception endpoints succeed."""
    mock_admin = {
        "uid": "admin-uid",
        "email": "admin@co.com",
        "roles": ["admin"],
    }
    mock_record = _get_dummy_quarantine_record(legal_hold=True)
    mock_res_result = {"exception_id": "ex-1", "resolved": True, "remaining_unresolved_count": 0}

    with (
        patch(
            "zombie_saas_coordinator.api.quarantine.verify_firebase_auth_token",
            return_value=mock_admin,
        ),
        patch("zombie_saas_coordinator.api.quarantine.set_legal_hold", return_value=mock_record),
        patch(
            "zombie_saas_coordinator.api.quarantine.resolve_validation_exception",
            return_value=mock_res_result,
        ),
    ):
        # Set legal hold
        resp_hold = client.post(
            "/api/v1/quarantine/prop-us12-001/legal-hold",
            json={"firebase_token": "valid-token", "legal_hold": True, "reason": "Audit review"},
        )
        assert resp_hold.status_code == 200
        assert resp_hold.json()["legal_hold"] is True

        # Resolve exception
        resp_res = client.post(
            "/api/v1/quarantine/prop-us12-001/exceptions/ex-1/resolve",
            json={"firebase_token": "valid-token", "resolution_notes": "Parity confirmed"},
        )
        assert resp_res.status_code == 200
        assert resp_res.json()["resolved"] is True
