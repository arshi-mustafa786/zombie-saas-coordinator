"""HMAC-SHA256 validation for expense provider webhooks."""

import hashlib
import hmac
import os

from google.cloud import secretmanager


class InvalidSignatureError(ValueError):
    """Raised when an expense webhook signature is missing or invalid."""


class WebhookSecretError(RuntimeError):
    """Raised when the webhook signing secret cannot be resolved."""


def get_webhook_secret() -> str:
    """Load the signing secret from the environment or Secret Manager.

    ``EXPENSE_WEBHOOK_SECRET`` is supported for local development. Cloud Run
    resolves the latest version of ``EXPENSE_WEBHOOK_SECRET_ID`` from Secret
    Manager when the direct value is absent.
    """
    local_secret = os.getenv("EXPENSE_WEBHOOK_SECRET")
    if local_secret:
        return local_secret

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise WebhookSecretError("GOOGLE_CLOUD_PROJECT is required to load the webhook secret")

    secret_id = os.getenv("EXPENSE_WEBHOOK_SECRET_ID", "expense-webhook-secret")
    client = secretmanager.SecretManagerServiceClient()
    name = client.secret_version_path(project_id, secret_id, "latest")
    response = client.access_secret_version(request={"name": name})
    secret = response.payload.data.decode("utf-8")
    if not secret:
        raise WebhookSecretError("The configured webhook signing secret is empty")
    return secret


def verify_hmac_sha256(payload: bytes | str, signature: str, secret: str | None = None) -> None:
    """Verify a provider signature using constant-time comparison.

    Signatures may be sent as a raw hexadecimal digest or as ``sha256=<digest>``.

    Raises:
        InvalidSignatureError: If the signature is missing, malformed, or incorrect.
    """
    if not signature:
        raise InvalidSignatureError("Missing webhook signature")

    supplied = signature.removeprefix("sha256=").strip().lower()
    if len(supplied) != 64 or any(character not in "0123456789abcdef" for character in supplied):
        raise InvalidSignatureError("Malformed webhook signature")

    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    signing_secret = secret if secret is not None else get_webhook_secret()
    expected = hmac.new(
        signing_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise InvalidSignatureError("Invalid webhook signature")
