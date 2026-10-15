"""Data models for US-1 Identity & Access telemetry scanner."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class IdpAuthError(Exception):
    """Raised when authentication or token validation with the IdP fails."""


class AppTelemetry(BaseModel):
    """Telemetry data for a single application retrieved from IdP access logs."""

    model_config = ConfigDict(extra="ignore")

    app_id: str
    app_name: str
    vendor: str = ""
    category: str = "General"
    capabilities: list[str] = Field(default_factory=list)
    total_seats: int
    active_seats: int
    inactive_seats: int
    inactive_ratio: float = 0.0
    last_login_date: str | None = None
    is_flagged_inactive: bool = False


class RedundancyAssessment(BaseModel):
    """Capability redundancy assessment between an app and enterprise standards."""

    model_config = ConfigDict(extra="ignore")

    app_name: str
    enterprise_standard_match: str
    redundancy_score: int = Field(ge=0, le=100)
    overlapping_capabilities: list[str] = Field(default_factory=list)
    rationale: str = ""


class IdPScanRequest(BaseModel):
    """Request payload for triggering an on-demand or scheduled IdP scan."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    tenant_id: str = Field(min_length=1, max_length=128)
    days: int = Field(default=60, ge=1, le=365)
    raw_apps: list[dict[str, Any]] | None = Field(default=None, description="Optional custom IdP telemetry records to analyze")



class IdPScanResponse(BaseModel):
    """Response returned upon completion of an IdP access log scan."""

    model_config = ConfigDict(extra="ignore")

    status: str = "completed"
    scan_id: str = Field(default_factory=lambda: f"scan_{uuid4().hex[:12]}")
    tenant_id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    total_apps_scanned: int
    flagged_apps_count: int
    apps: list[dict[str, Any]] = Field(default_factory=list)
    flagged: list[dict[str, Any]] = Field(default_factory=list)
