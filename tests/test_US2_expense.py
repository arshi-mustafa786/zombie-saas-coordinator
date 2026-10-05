"""Tests for US-2 expense webhook ingestion."""

# ruff: noqa: N999, S106, S107

import hashlib
import hmac
import json
from datetime import date, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import AlreadyExists

from zombie_saas_coordinator.agents.auditor import tools
from zombie_saas_coordinator.main import app
from zombie_saas_coordinator.shared.auth.hmac_validator import (
    InvalidSignatureError,
    verify_hmac_sha256,
)
from zombie_saas_coordinator.shared.constants import SAAS_WHITELIST_COLLECTION
from zombie_saas_coordinator.shared.models.expense import ExpenseEvent


def _signature(payload: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _firestore(approved: bool = False, exists: bool = True) -> tuple[Mock, Mock]:
    client = Mock()
    whitelist_snapshot = Mock()
    whitelist_snapshot.exists = exists
    whitelist_snapshot.to_dict.return_value = {"approved": approved}
    whitelist_document = Mock()
    whitelist_document.get.return_value = whitelist_snapshot
    expense_document = Mock()

    def collection(name: str) -> Mock:
        result = Mock()
        result.document.return_value = (
            whitelist_document if name == SAAS_WHITELIST_COLLECTION else expense_document
        )
        return result

    client.collection.side_effect = collection
    return client, expense_document


def test_verify_hmac_accepts_valid_signature() -> None:
    payload = b'{"merchant":"Trello"}'
    verify_hmac_sha256(payload, _signature(payload), secret="test-secret")


def test_verify_hmac_rejects_invalid_signature() -> None:
    with pytest.raises(InvalidSignatureError):
        verify_hmac_sha256(b"payload", "sha256=" + "0" * 64, secret="test-secret")


def test_expense_event_id_is_stable_for_webhook_retries() -> None:
    payload = {
        "provider": "brex",
        "transaction_id": "txn_123",
        "merchant": "Trello",
        "amount": "120.00",
        "frequency": "monthly",
    }

    first = ExpenseEvent.model_validate(payload)
    retry = ExpenseEvent.model_validate(payload)
    enriched_retry = ExpenseEvent.model_validate({**payload, "amount": "125.00"})
    different = ExpenseEvent.model_validate({**payload, "transaction_id": "txn_456"})

    assert first.event_id == retry.event_id
    assert first.event_id == enriched_retry.event_id
    assert first.event_id != different.event_id
    assert first.event_id.startswith("expense_")


def test_flag_subscription_routes_high_value_renewal(monkeypatch: pytest.MonkeyPatch) -> None:
    firestore_client, expense_document = _firestore(approved=False, exists=False)
    audit_logger = Mock()
    monkeypatch.setattr(tools, "_get_firestore_client", lambda: firestore_client)
    monkeypatch.setattr(tools, "_get_audit_logger", lambda: audit_logger)

    result = tools.flag_subscription(
        {
            "merchant": "Unknown SaaS",
            "amount": 750,
            "frequency": "monthly",
            "renewal_date": (date.today() + timedelta(days=10)).isoformat(),
        }
    )

    assert result["flagged"] is True
    assert result["priority"] == "immediate"
    assert result["route_to"] == "finance_lead"
    assert result["renewal_opportunity"] is True
    assert result["confidence"] == "low"
    expense_document.create.assert_called_once()
    audit_logger.log_struct.assert_called_once()


def test_approved_subscription_is_not_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    firestore_client, _ = _firestore(approved=True)
    monkeypatch.setattr(tools, "_get_firestore_client", lambda: firestore_client)
    monkeypatch.setattr(tools, "_get_audit_logger", Mock)

    result = tools.flag_subscription(
        {"merchant": "Approved SaaS", "amount": 120, "frequency": "monthly"}
    )

    assert result["flagged"] is False
    assert result["status"] == "approved"


def test_duplicate_webhook_is_an_idempotent_success(monkeypatch: pytest.MonkeyPatch) -> None:
    firestore_client, expense_document = _firestore(approved=False, exists=False)
    expense_document.create.side_effect = AlreadyExists(  # type: ignore[no-untyped-call]
        "event already stored"
    )
    audit_logger = Mock()
    monkeypatch.setattr(tools, "_get_firestore_client", lambda: firestore_client)
    monkeypatch.setattr(tools, "_get_audit_logger", lambda: audit_logger)

    result = tools.flag_subscription(
        {
            "provider": "ramp",
            "transaction_id": "txn_retry",
            "merchant": "Unknown SaaS",
            "amount": 99,
            "frequency": "monthly",
        }
    )

    assert result["duplicate"] is True
    expense_document.create.assert_called_once()
    audit_logger.log_struct.assert_called_once()


def test_webhook_rejects_invalid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPENSE_WEBHOOK_SECRET", "test-secret")
    response = TestClient(app).post(
        "/webhooks/expense-notification",
        content=b"{}",
        headers={"X-Webhook-Signature": "sha256=" + "0" * 64},
    )
    assert response.status_code == 403


def test_webhook_rejects_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPENSE_WEBHOOK_SECRET", "test-secret")
    payload = b"not-json"
    response = TestClient(app).post(
        "/webhooks/expense-notification",
        content=payload,
        headers={"X-Webhook-Signature": _signature(payload)},
    )
    assert response.status_code == 400


def test_webhook_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from zombie_saas_coordinator.api import webhooks

    monkeypatch.setenv("EXPENSE_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(
        webhooks,
        "flag_subscription",
        lambda event: {"status": "flagged", "flagged": True, "reason": "unapproved"},
    )
    payload = json.dumps(
        {"merchant": "Trello", "amount": 120, "frequency": "monthly"},
        separators=(",", ":"),
    ).encode()
    response = TestClient(app).post(
        "/webhooks/expense-notification",
        content=payload,
        headers={"X-Webhook-Signature": _signature(payload)},
    )
    assert response.status_code == 202
    assert response.json()["assessment"]["flagged"] is True


def test_webhook_returns_retryable_503(monkeypatch: pytest.MonkeyPatch) -> None:
    from zombie_saas_coordinator.api import webhooks

    monkeypatch.setenv("EXPENSE_WEBHOOK_SECRET", "test-secret")

    def fail(_: dict[str, object]) -> dict[str, object]:
        raise TimeoutError("Firestore timeout")

    monkeypatch.setattr(webhooks, "flag_subscription", fail)
    payload = b'{"merchant":"Trello","amount":120,"frequency":"monthly"}'
    response = TestClient(app).post(
        "/webhooks/expense-notification",
        content=payload,
        headers={"X-Webhook-Signature": _signature(payload)},
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
