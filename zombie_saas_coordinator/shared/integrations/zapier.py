"""Read-only Zapier API client for US-10 automation hub scanning.

Zaps are listed through ``GET /v2/zaps``. A step only names its app when the
request asks for ``expand=steps.action``, so that expansion is always requested;
without it a zap's steps are opaque IDs and the source app cannot be matched.

Security notes:
- The OAuth token goes in the ``Authorization`` header, never the URL, so it
  cannot leak through access logs, error messages or audit entries.
- The base URL is fixed and redirects are not followed.
"""

import os
import time
from collections.abc import Callable
from typing import Any

import httpx

from zombie_saas_coordinator.shared.constants import (
    HUB_MAX_RETRIES,
    HUB_MAX_RETRY_WAIT_SECONDS,
    HUB_RETRY_STATUSES,
    HUB_TIMEOUT_SECONDS,
    MAX_WORKFLOWS_PER_SCAN,
    ZAPIER_API_BASE_URL,
    ZAPIER_MAX_PAGES,
    ZAPIER_PAGE_SIZE,
    ZAPIER_TOKEN_SECRET_ID,
)


class ZapierApiError(RuntimeError):
    """Raised when Zapier cannot be reached or returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ZapierCredentialsError(RuntimeError):
    """Raised when no Zapier access token is configured."""


def get_zapier_token() -> str:
    """Load the Zapier OAuth access token from the environment or Secret Manager.

    ``ZAPIER_ACCESS_TOKEN`` is used for local development; on Cloud Run the
    value comes from Secret Manager. The token needs the ``zap:all`` scope,
    otherwise Zapier returns only zaps that use the caller's own integration.
    """
    token = os.getenv("ZAPIER_ACCESS_TOKEN")
    if token:
        return token

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ZapierCredentialsError(
            "Zapier credentials are not configured (set ZAPIER_ACCESS_TOKEN)"
        )
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = client.secret_version_path(project_id, ZAPIER_TOKEN_SECRET_ID, "latest")
        token = client.access_secret_version(request={"name": name}).payload.data.decode()
    except Exception as error:
        raise ZapierCredentialsError(
            "Zapier token could not be loaded from Secret Manager"
        ) from error
    if not token:
        raise ZapierCredentialsError("Zapier token in Secret Manager is empty")
    return token


class ZapierClient:
    """Minimal read-only Zapier client that records every API call it makes."""

    def __init__(
        self,
        access_token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=ZAPIER_API_BASE_URL,
            timeout=HUB_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        )
        self._sleep = sleep
        # Audit trail of requests: method, path, status, duration. No credentials.
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> "ZapierClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._http.close()

    def fetch_zaps(self) -> tuple[list[dict[str, Any]], bool]:
        """All zaps with their steps expanded. Returns (zaps, truncated)."""
        zaps: list[dict[str, Any]] = []
        for page in range(ZAPIER_MAX_PAGES):
            payload = self._get(
                "/zaps",
                {
                    "expand": "steps.action",
                    "limit": str(ZAPIER_PAGE_SIZE),
                    "offset": str(page * ZAPIER_PAGE_SIZE),
                },
            )
            batch = payload.get("data") or []
            if not isinstance(batch, list):
                raise ZapierApiError("Zapier returned a malformed zap list")
            zaps.extend(batch)
            if len(zaps) >= MAX_WORKFLOWS_PER_SCAN:
                return zaps[:MAX_WORKFLOWS_PER_SCAN], True
            # Zapier paginates with links.next; a short page also means the end.
            if len(batch) < ZAPIER_PAGE_SIZE or not (payload.get("links") or {}).get("next"):
                return zaps, False
        return zaps, True

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        for attempt in range(HUB_MAX_RETRIES + 1):
            started = time.monotonic()
            try:
                response = self._http.get(path, params=params)
            except httpx.HTTPError as error:
                self._record(path, None, started, type(error).__name__)
                # The exception text is not propagated: keep the message credential-free.
                raise ZapierApiError(
                    f"Zapier request to {path} failed: {type(error).__name__}"
                ) from error
            self._record(path, response.status_code, started)

            if response.status_code in HUB_RETRY_STATUSES and attempt < HUB_MAX_RETRIES:
                self._sleep(_retry_wait(response, attempt))
                continue
            if response.status_code in (401, 403):
                raise ZapierApiError(
                    f"Zapier rejected the access token (HTTP {response.status_code}); "
                    "it must be valid and carry the zap:all scope",
                    response.status_code,
                )
            if response.is_error:
                raise ZapierApiError(
                    f"Zapier API returned HTTP {response.status_code} for {path}",
                    response.status_code,
                )
            try:
                payload = response.json()
            except ValueError as error:
                raise ZapierApiError(
                    f"Zapier API returned non-JSON for {path}", response.status_code
                ) from error
            if not isinstance(payload, dict):
                raise ZapierApiError(f"Zapier API returned a malformed body for {path}")
            return payload
        raise AssertionError("unreachable: the last attempt always returns or raises")

    def _record(
        self, path: str, status: int | None, started: float, error: str | None = None
    ) -> None:
        entry: dict[str, Any] = {
            "hub": "zapier",
            "method": "GET",
            "path": path,
            "status": status,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }
        if error:
            entry["error"] = error
        self.calls.append(entry)


def _retry_wait(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait before retrying: honour Retry-After, else exponential backoff."""
    retry_after = response.headers.get("Retry-After", "")
    wait = float(retry_after) if retry_after.isdigit() else float(2**attempt)
    return min(wait, HUB_MAX_RETRY_WAIT_SECONDS)
