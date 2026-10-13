"""Read-only Make (Integromat) API client for US-10 automation hub scanning.

Scenarios are listed through ``GET /api/v2/scenarios?teamId=...``. The list only
carries names and state, so the apps a scenario uses come from its blueprint
(``GET /api/v2/scenarios/{id}/blueprint``), whose modules name the connected app.

Security notes:
- Make authenticates with ``Authorization: Token <token>`` (not OAuth bearer),
  sent as a header so it cannot leak through URLs or logs.
- The host is zone-specific and operator-configured, so it is validated against
  ``.make.com`` over HTTPS before any request (SSRF guard).
"""

import os
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from zombie_saas_coordinator.shared.constants import (
    HUB_MAX_RETRIES,
    HUB_MAX_RETRY_WAIT_SECONDS,
    HUB_RETRY_STATUSES,
    HUB_TIMEOUT_SECONDS,
    MAKE_ALLOWED_ZONE_SUFFIX,
    MAKE_API_ZONE,
    MAKE_MAX_PAGES,
    MAKE_PAGE_SIZE,
    MAKE_TOKEN_SECRET_ID,
    MAX_WORKFLOWS_PER_SCAN,
)

_ZONE_PATTERN = re.compile(r"^[a-z0-9.-]+$")
# Make scenario IDs are numeric; anything else must not reach a URL path.
_SCENARIO_ID_PATTERN = re.compile(r"^[0-9]{1,20}$")


class MakeApiError(RuntimeError):
    """Raised when Make cannot be reached or returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MakeCredentialsError(RuntimeError):
    """Raised when the Make API token or team ID is not configured."""


def validate_make_zone(zone: str) -> str:
    """Return the zone host if it is a real Make zone, else raise ValueError."""
    candidate = (zone or "").strip().lower().removeprefix("https://").rstrip("/")
    if not _ZONE_PATTERN.fullmatch(candidate) or not candidate.endswith(MAKE_ALLOWED_ZONE_SUFFIX):
        raise ValueError(
            f"Invalid Make zone '{zone}': expected a host ending in {MAKE_ALLOWED_ZONE_SUFFIX}"
        )
    return candidate


def validate_scenario_id(scenario_id: Any) -> str:
    """Return the scenario ID if it is numeric, else raise ValueError (path injection)."""
    candidate = str(scenario_id).strip()
    if not _SCENARIO_ID_PATTERN.fullmatch(candidate):
        raise ValueError(f"Invalid Make scenario id: {scenario_id!r}")
    return candidate


def get_make_credentials() -> tuple[str, str, str]:
    """Load the Make API token, zone host and team ID.

    ``MAKE_API_TOKEN`` / ``MAKE_TEAM_ID`` / ``MAKE_API_ZONE`` are used for local
    development; on Cloud Run the token comes from Secret Manager.
    """
    team_id = os.getenv("MAKE_TEAM_ID", "").strip()
    if not team_id:
        raise MakeCredentialsError("MAKE_TEAM_ID is not configured")
    zone = validate_make_zone(os.getenv("MAKE_API_ZONE") or MAKE_API_ZONE)

    token = os.getenv("MAKE_API_TOKEN")
    if token:
        return token, zone, team_id

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise MakeCredentialsError("Make credentials are not configured (set MAKE_API_TOKEN)")
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = client.secret_version_path(project_id, MAKE_TOKEN_SECRET_ID, "latest")
        token = client.access_secret_version(request={"name": name}).payload.data.decode()
    except Exception as error:
        raise MakeCredentialsError("Make token could not be loaded from Secret Manager") from error
    if not token:
        raise MakeCredentialsError("Make token in Secret Manager is empty")
    return token, zone, team_id


class MakeClient:
    """Minimal read-only Make client that records every API call it makes."""

    def __init__(
        self,
        api_token: str,
        zone: str,
        team_id: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.team_id = team_id
        self._http = httpx.Client(
            base_url=f"https://{validate_make_zone(zone)}/api/v2",
            timeout=HUB_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
            headers={
                "Accept": "application/json",
                "Authorization": f"Token {api_token}",
            },
        )
        self._sleep = sleep
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> "MakeClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._http.close()

    def fetch_scenarios(self) -> tuple[list[dict[str, Any]], bool]:
        """All scenarios for the configured team. Returns (scenarios, truncated)."""
        scenarios: list[dict[str, Any]] = []
        for page in range(MAKE_MAX_PAGES):
            payload = self._get(
                "/scenarios",
                {
                    "teamId": self.team_id,
                    "pg[limit]": str(MAKE_PAGE_SIZE),
                    "pg[offset]": str(page * MAKE_PAGE_SIZE),
                },
            )
            batch = payload.get("scenarios") or []
            if not isinstance(batch, list):
                raise MakeApiError("Make returned a malformed scenario list")
            scenarios.extend(batch)
            if len(scenarios) >= MAX_WORKFLOWS_PER_SCAN:
                return scenarios[:MAX_WORKFLOWS_PER_SCAN], True
            if len(batch) < MAKE_PAGE_SIZE:
                return scenarios, False
        return scenarios, True

    def fetch_blueprint(self, scenario_id: Any) -> dict[str, Any]:
        """The scenario's blueprint, whose modules name the connected apps."""
        payload = self._get(f"/scenarios/{validate_scenario_id(scenario_id)}/blueprint")
        blueprint = payload.get("response", payload).get("blueprint", payload)
        return blueprint if isinstance(blueprint, dict) else {}

    def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        for attempt in range(HUB_MAX_RETRIES + 1):
            started = time.monotonic()
            try:
                response = self._http.get(path, params=params)
            except httpx.HTTPError as error:
                self._record(path, None, started, type(error).__name__)
                raise MakeApiError(
                    f"Make request to {path} failed: {type(error).__name__}"
                ) from error
            self._record(path, response.status_code, started)

            if response.status_code in HUB_RETRY_STATUSES and attempt < HUB_MAX_RETRIES:
                self._sleep(_retry_wait(response, attempt))
                continue
            if response.status_code in (401, 403):
                raise MakeApiError(
                    f"Make rejected the API token (HTTP {response.status_code}); it must be "
                    "valid, carry the scenarios:read scope and match the configured zone/team",
                    response.status_code,
                )
            if response.is_error:
                raise MakeApiError(
                    f"Make API returned HTTP {response.status_code} for {path}",
                    response.status_code,
                )
            try:
                payload = response.json()
            except ValueError as error:
                raise MakeApiError(
                    f"Make API returned non-JSON for {path}", response.status_code
                ) from error
            if not isinstance(payload, dict):
                raise MakeApiError(f"Make API returned a malformed body for {path}")
            return payload
        raise AssertionError("unreachable: the last attempt always returns or raises")

    def _record(
        self, path: str, status: int | None, started: float, error: str | None = None
    ) -> None:
        entry: dict[str, Any] = {
            "hub": "make",
            "method": "GET",
            # Scenario IDs are validated as numeric, so the path carries no injected text.
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
