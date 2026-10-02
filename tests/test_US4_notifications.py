"""Tests for US-4 Interactive Approval Card and callback handling."""

# ruff: noqa: N999, S106, S107

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from zombie_saas_coordinator.agents.auditor import tools
from zombie_saas_coordinator.main import app
from zombie_saas_coordinator.shared.integrations.slack import (
    SSRFSecurityError,
    build_slack_approval_card,
    dispatch_slack_message,
    validate_slack_webhook_url,
)
from zombie_saas_coordinator.shared.models.proposal import (
    ProposalStatus,
    get_dummy_proposal,
)


def _mock_firestore(
    proposal_data: dict[str, Any] | None = None,
    exists: bool = True,
) -> tuple[Mock, Mock]:
    client = Mock()
    proposal_snapshot = Mock()
    proposal_snapshot.exists = exists
    proposal_snapshot.to_dict.return_value = proposal_data or get_dummy_proposal().model_dump(
        mode="json"
    )

    proposal_doc = Mock()
    proposal_doc.get.return_value = proposal_snapshot
    proposal_doc.update.return_value = None

    def collection(name: str) -> Mock:
        coll = Mock()
        coll.document.return_value = proposal_doc
        return coll

    client.collection.side_effect = collection
    return client, proposal_doc


# ──────────────────────────────────────────────
# Model & Dummy Data Tests
# ──────────────────────────────────────────────


def test_dummy_proposal_generation() -> None:
    proposal = get_dummy_proposal("prop-trello-001")
    assert proposal.proposal_id == "prop-trello-001"
    assert proposal.app_name == "Trello"
    assert proposal.target_platform == "Asana"
    assert proposal.annual_savings > 0
    assert 0 <= proposal.risk_score <= 100
    assert len(proposal.detected_dependencies) > 0
    assert proposal.status == ProposalStatus.PENDING


# ──────────────────────────────────────────────
# Block Kit Card Generation Tests
# ──────────────────────────────────────────────


def test_build_slack_approval_card_format() -> None:
    proposal = get_dummy_proposal("prop-123")
    card = build_slack_approval_card(proposal)

    assert "blocks" in card
    blocks = card["blocks"]

    # Header block
    assert any(b.get("type") == "header" for b in blocks)

    # Actions block containing the 3 buttons
    action_block = next((b for b in blocks if b.get("type") == "actions"), None)
    assert action_block is not None
    elements = action_block.get("elements", [])
    assert len(elements) == 3

    action_ids = [el.get("action_id") for el in elements]
    assert "simulate_migration" in action_ids
    assert "approve_consolidation" in action_ids
    assert "ignore_whitelist" in action_ids


# ──────────────────────────────────────────────
# SSRF Validation Tests
# ──────────────────────────────────────────────


def test_validate_slack_webhook_url_accepts_valid_domain() -> None:
    valid_url = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
    assert validate_slack_webhook_url(valid_url) is True


@pytest.mark.parametrize(
    "forbidden_url",
    [
        "http://localhost:8080/webhook",
        "http://127.0.0.1/evil",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://10.0.0.1/admin",
        "https://evil-attacker.com/steal-data",
        "ftp://hooks.slack.com/files",
    ],
)
def test_validate_slack_webhook_url_rejects_ssrf(forbidden_url: str) -> None:
    with pytest.raises(SSRFSecurityError):
        validate_slack_webhook_url(forbidden_url)


# ──────────────────────────────────────────────
# Dispatch & Tool Tests
# ──────────────────────────────────────────────


def test_dispatch_slack_message_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_post = Mock()
    mock_post.return_value.status_code = 200
    mock_post.return_value.text = "ok"

    monkeypatch.setattr("httpx.Client.post", mock_post)

    result = dispatch_slack_message(
        "https://hooks.slack.com/services/T00/B00/X00",
        {"text": "Hello test"},
    )
    assert result["sent"] is True
    assert result["status_code"] == 200


def test_send_approval_card_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    firestore_client, _ = _mock_firestore()
    audit_logger = Mock()

    monkeypatch.setattr(tools, "_get_firestore_client", lambda: firestore_client)
    monkeypatch.setattr(tools, "_get_audit_logger", lambda: audit_logger)

    with patch(
        "zombie_saas_coordinator.shared.integrations.slack.dispatch_slack_message"
    ) as mock_dispatch:
        mock_dispatch.return_value = {"sent": True, "message_id": "msg_999", "status_code": 200}

        result = tools.send_approval_card(
            proposal_id="prop-test-01",
            channel="https://hooks.slack.com/services/T00/B00/X00",
        )
        assert result["sent"] is True
        assert result["message_id"] == "msg_999"
        assert result["proposal_id"] == "prop-test-01"


# ──────────────────────────────────────────────
# API Endpoint & Callback Tests
# ──────────────────────────────────────────────


def test_send_notification_endpoint_success(monkeypatch: pytest.MonkeyPatch) -> None:
    firestore_client, _ = _mock_firestore()
    audit_logger = Mock()

    monkeypatch.setattr(tools, "_get_firestore_client", lambda: firestore_client)
    monkeypatch.setattr(tools, "_get_audit_logger", lambda: audit_logger)

    with patch(
        "zombie_saas_coordinator.shared.integrations.slack.dispatch_slack_message"
    ) as mock_dispatch:
        mock_dispatch.return_value = {"sent": True, "message_id": "msg_123", "status_code": 200}

        client = TestClient(app)
        response = client.post(
            "/api/v1/notifications/send",
            json={
                "proposal_id": "prop-test-01",
                "channel": "https://hooks.slack.com/services/T00/B00/X00",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sent"] is True


def test_callback_approval_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    firestore_client, proposal_doc = _mock_firestore()
    audit_logger = Mock()

    monkeypatch.setenv("SLACK_VERIFICATION_TOKEN", "valid-token-secret")
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.callbacks._get_firestore_client", lambda: firestore_client
    )
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.callbacks._get_audit_logger", lambda: audit_logger
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/callbacks/approval",
        json={
            "token": "valid-token-secret",
            "action": "approve_consolidation",
            "proposal_id": "prop-test-01",
            "user_id": "usr_itops_42",
            "user_email": "ops@example.com",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["action"] == "approve_consolidation"
    assert data["new_state"] == "APPROVED"

    # Verify Firestore update and Audit log call
    proposal_doc.update.assert_called_once()
    audit_logger.log_struct.assert_called_once()


def test_callback_simulate_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    firestore_client, proposal_doc = _mock_firestore()
    audit_logger = Mock()

    monkeypatch.setenv("SLACK_VERIFICATION_TOKEN", "valid-token-secret")
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.callbacks._get_firestore_client", lambda: firestore_client
    )
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.callbacks._get_audit_logger", lambda: audit_logger
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/callbacks/approval",
        json={
            "token": "valid-token-secret",
            "action": "simulate_migration",
            "proposal_id": "prop-test-01",
            "user_id": "usr_itops_42",
        },
    )

    assert response.status_code == 200
    assert response.json()["new_state"] == "SIMULATING"


def test_callback_ignore_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    firestore_client, proposal_doc = _mock_firestore()
    audit_logger = Mock()

    monkeypatch.setenv("SLACK_VERIFICATION_TOKEN", "valid-token-secret")
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.callbacks._get_firestore_client", lambda: firestore_client
    )
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.callbacks._get_audit_logger", lambda: audit_logger
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/callbacks/approval",
        json={
            "token": "valid-token-secret",
            "action": "ignore_whitelist",
            "proposal_id": "prop-test-01",
            "user_id": "usr_itops_42",
        },
    )

    assert response.status_code == 200
    assert response.json()["new_state"] == "WHITELISTED"


def test_callback_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SLACK_VERIFICATION_TOKEN", "super-secret-token")

    client = TestClient(app)
    response = client.post(
        "/api/v1/callbacks/approval",
        json={
            "token": "forged-or-wrong-token",
            "action": "approve_consolidation",
            "proposal_id": "prop-test-01",
            "user_id": "attacker",
        },
    )
    assert response.status_code == 403
    assert "Invalid callback verification token" in response.json()["detail"]


def test_callback_rejects_expired_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    expired_data = get_dummy_proposal().model_dump(mode="json")
    expired_data["status"] = "EXPIRED"
    expired_data["expires_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    firestore_client, _ = _mock_firestore(proposal_data=expired_data)
    audit_logger = Mock()

    monkeypatch.setenv("SLACK_VERIFICATION_TOKEN", "valid-token-secret")
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.callbacks._get_firestore_client", lambda: firestore_client
    )
    monkeypatch.setattr(
        "zombie_saas_coordinator.api.callbacks._get_audit_logger", lambda: audit_logger
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/callbacks/approval",
        json={
            "token": "valid-token-secret",
            "action": "approve_consolidation",
            "proposal_id": "prop-expired",
            "user_id": "usr_ops",
        },
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()
