"""Read-only Trello REST API client for US-6 behavioral contract extraction.

Security notes:
- Credentials go in the ``Authorization: OAuth ...`` header, never the URL,
  so they cannot leak through access logs, error messages or audit entries.
- ``board_id`` is validated against Trello's ID formats before it is placed
  in a path, which blocks path/query injection into other endpoints.
- The base URL is fixed and redirects are not followed.
"""

import os
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from zombie_saas_coordinator.shared.constants import (
    TRELLO_ACTIONS_PAGE_SIZE,
    TRELLO_API_BASE_URL,
    TRELLO_API_KEY_SECRET_ID,
    TRELLO_API_TOKEN_SECRET_ID,
    TRELLO_MAX_ACTION_PAGES,
    TRELLO_MAX_RETRIES,
    TRELLO_MAX_RETRY_WAIT_SECONDS,
    TRELLO_RETRY_STATUSES,
    TRELLO_TIMEOUT_SECONDS,
)

# Trello board IDs are 24 hex chars; short links (from board URLs) are 8 alphanumerics.
_BOARD_ID_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{24}|[A-Za-z0-9]{8})$")

# Only the action types the activity inference understands.
_ACTION_FILTER = "createCard,updateCard,addLabelToCard,removeLabelFromCard"


class TrelloApiError(RuntimeError):
    """Raised when Trello cannot be reached or returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class TrelloCredentialsError(RuntimeError):
    """Raised when no Trello API key/token is configured."""


def validate_board_id(board_id: str) -> str:
    """Return the board ID if it is a valid Trello ID or short link, else raise ValueError."""
    candidate = (board_id or "").strip()
    if not _BOARD_ID_PATTERN.fullmatch(candidate):
        raise ValueError(
            "Invalid Trello board id: expected a 24-character hex id or an 8-character short link"
        )
    return candidate


def get_trello_credentials() -> tuple[str, str]:
    """Load the Trello API key and token from the environment or Secret Manager.

    ``TRELLO_API_KEY`` / ``TRELLO_API_TOKEN`` are used for local development.
    On Cloud Run the values come from Secret Manager.
    """
    key = os.getenv("TRELLO_API_KEY")
    token = os.getenv("TRELLO_API_TOKEN")
    if key and token:
        return key, token

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise TrelloCredentialsError(
            "Trello credentials are not configured (set TRELLO_API_KEY and TRELLO_API_TOKEN)"
        )
    try:
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()

        def read(secret_id: str) -> str:
            name = client.secret_version_path(project_id, secret_id, "latest")
            return client.access_secret_version(request={"name": name}).payload.data.decode()

        key, token = read(TRELLO_API_KEY_SECRET_ID), read(TRELLO_API_TOKEN_SECRET_ID)
    except Exception as error:
        raise TrelloCredentialsError(
            "Trello credentials could not be loaded from Secret Manager"
        ) from error
    if not key or not token:
        raise TrelloCredentialsError("Trello credentials in Secret Manager are empty")
    return key, token


class TrelloClient:
    """Minimal read-only Trello client that records every API call it makes."""

    def __init__(
        self,
        api_key: str,
        api_token: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(
            base_url=TRELLO_API_BASE_URL,
            timeout=TRELLO_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=transport,
            headers={
                "Accept": "application/json",
                "Authorization": f'OAuth oauth_consumer_key="{api_key}", oauth_token="{api_token}"',
            },
        )
        self._sleep = sleep
        # Audit trail of requests: method, path template, status, duration. No credentials.
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> "TrelloClient":
        return self

    def __exit__(self, *_: object) -> None:
        self._http.close()

    def fetch_board_bundle(self, board_id: str) -> dict[str, Any]:
        """Fetch everything US-6 needs about one board in a single pass."""
        board_id = validate_board_id(board_id)
        actions, truncated = self._fetch_actions(board_id)
        return {
            "board": self._get("/boards/{board_id}", board_id, {"fields": "name,url,closed"}),
            "lists": self._get(
                "/boards/{board_id}/lists", board_id, {"filter": "all", "fields": "name,closed"}
            ),
            "labels": self._get(
                "/boards/{board_id}/labels", board_id, {"fields": "name,color", "limit": "1000"}
            ),
            "custom_fields": self._get("/boards/{board_id}/customFields", board_id),
            "checklists": self._get("/boards/{board_id}/checklists", board_id),
            # Card names/descriptions are not requested: only structure and usage counts.
            "cards": self._get(
                "/boards/{board_id}/cards",
                board_id,
                {"filter": "all", "fields": "idList,idLabels,due,dueComplete,closed,idChecklists"},
            ),
            "plugins": self._get("/boards/{board_id}/plugins", board_id, {"filter": "enabled"}),
            "actions": actions,
            "actions_truncated": truncated,
        }

    def _fetch_actions(self, board_id: str) -> tuple[list[dict[str, Any]], bool]:
        """Board activity, newest first, paginated with Trello's ``before`` cursor."""
        actions: list[dict[str, Any]] = []
        before: str | None = None
        for _ in range(TRELLO_MAX_ACTION_PAGES):
            params = {"filter": _ACTION_FILTER, "limit": str(TRELLO_ACTIONS_PAGE_SIZE)}
            if before:
                params["before"] = before
            page = self._get("/boards/{board_id}/actions", board_id, params)
            actions.extend(page)
            if len(page) < TRELLO_ACTIONS_PAGE_SIZE:
                return actions, False
            before = page[-1]["id"]
        return actions, True

    def _get(self, path_template: str, board_id: str, params: dict[str, str] | None = None) -> Any:
        path = path_template.format(board_id=board_id)
        for attempt in range(TRELLO_MAX_RETRIES + 1):
            started = time.monotonic()
            try:
                response = self._http.get(path, params=params)
            except httpx.HTTPError as error:
                self._record(path_template, None, started, type(error).__name__)
                # The exception text is not propagated: keep the message credential-free.
                raise TrelloApiError(
                    f"Trello request to {path_template} failed: {type(error).__name__}"
                ) from error
            self._record(path_template, response.status_code, started)

            if response.status_code in TRELLO_RETRY_STATUSES and attempt < TRELLO_MAX_RETRIES:
                self._sleep(_retry_wait(response, attempt))
                continue
            if response.is_error:
                raise TrelloApiError(
                    f"Trello API returned HTTP {response.status_code} for {path_template}",
                    response.status_code,
                )
            try:
                return response.json()
            except ValueError as error:
                raise TrelloApiError(
                    f"Trello API returned non-JSON for {path_template}", response.status_code
                ) from error
        raise AssertionError("unreachable: the last attempt always returns or raises")

    def _record(
        self, path_template: str, status: int | None, started: float, error: str | None = None
    ) -> None:
        entry: dict[str, Any] = {
            "method": "GET",
            "path": path_template,
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
    return min(wait, TRELLO_MAX_RETRY_WAIT_SECONDS)
