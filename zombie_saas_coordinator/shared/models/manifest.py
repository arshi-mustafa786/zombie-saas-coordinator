"""Immutable migration manifest and reconciliation models (US-11)."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class MigrationPhase(StrEnum):
    """Lifecycle states recorded for an approved migration."""

    PLANNED = "PLANNED"
    MIGRATING = "MIGRATING"
    RECONCILING = "RECONCILING"
    RECONCILED = "RECONCILED"
    EXCEPTIONS_FOUND = "EXCEPTIONS_FOUND"


class MigrationItem(BaseModel):
    """One source record and its immutable source-to-target mapping."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=256)
    target_id: str | None = Field(default=None, max_length=256)
    record_type: str = Field(default="record", min_length=1, max_length=100)
    source_hash: str = Field(min_length=64, max_length=64)
    target_hash: str | None = Field(default=None, min_length=64, max_length=64)
    source_attachment_count: int = Field(default=0, ge=0)
    source_comment_count: int = Field(default=0, ge=0)
    target_attachment_count: int | None = Field(default=None, ge=0)
    target_comment_count: int | None = Field(default=None, ge=0)
    migration_attempts: int = Field(default=0, ge=0)
    last_error: str | None = Field(default=None, max_length=1000)


class MigrationManifest(BaseModel):
    """Audit document for a planned migration and its reconciliation evidence."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str = Field(default_factory=lambda: f"mig_{uuid4().hex[:16]}")
    proposal_id: str = Field(min_length=1, max_length=256)
    board_id: str = Field(min_length=1, max_length=256)
    project_id: str = Field(min_length=1, max_length=256)
    source_app: str = Field(default="trello", min_length=1, max_length=100)
    target_app: str = Field(default="asana", min_length=1, max_length=100)
    phase: MigrationPhase = MigrationPhase.PLANNED
    items: list[MigrationItem] = Field(default_factory=list)
    source_page_count: int = Field(default=1, ge=1)
    target_page_count: int | None = Field(default=None, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReconciliationException(BaseModel):
    """An isolated discrepancy that prevents a clean cutover."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    source_id: str | None = Field(default=None, max_length=256)
    target_id: str | None = Field(default=None, max_length=256)
    message: str = Field(min_length=1, max_length=1000)
    retryable: bool = False


class ReconciliationReport(BaseModel):
    """Cryptographic evidence and exception list produced by RECONCILING."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(default_factory=lambda: f"rec_{uuid4().hex[:16]}")
    manifest_id: str = Field(min_length=1, max_length=256)
    source_count: int = Field(ge=0)
    target_count: int = Field(ge=0)
    source_page_count: int = Field(ge=1)
    target_page_count: int = Field(ge=1)
    mapped_count: int = Field(ge=0)
    verified_count: int = Field(ge=0)
    exceptions: list[ReconciliationException] = Field(default_factory=list)
    reconciled: bool
    reconciled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
