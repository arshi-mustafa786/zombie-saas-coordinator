"""Automation hub dependency models (US-10).

A ``DependencyScan`` is the audit-trail document for one source app: every
Zapier zap and Make scenario that references it, plus the graph
Source App -> Automation Hub -> downstream apps.

All text comes from third-party APIs and is therefore untrusted: callers bound
and strip it with ``prompt_safe`` before building these models.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from zombie_saas_coordinator.shared.constants import MAX_TEXT_FIELD_LENGTH


class AutomationHub(StrEnum):
    """Automation platforms US-10 scans."""

    ZAPIER = "zapier"
    MAKE = "make"


class StepKind(StrEnum):
    """Where a step sits in a workflow."""

    TRIGGER = "trigger"
    ACTION = "action"


class WorkflowStep(BaseModel):
    """One step of a zap or scenario, and the app it connects to."""

    model_config = ConfigDict(frozen=True)

    kind: StepKind
    app: str = Field(default="", max_length=MAX_TEXT_FIELD_LENGTH)
    app_key: str = Field(default="", max_length=MAX_TEXT_FIELD_LENGTH)
    title: str = Field(default="", max_length=MAX_TEXT_FIELD_LENGTH)


class DependentWorkflow(BaseModel):
    """A workflow that references the source app.

    ``breaks_if_decommissioned`` is a fact: the workflow has a step on the source
    app, so decommissioning it stops that step. ``critical`` is a heuristic and
    always carries the reasons that produced it.
    """

    model_config = ConfigDict(frozen=True)

    workflow_id: str = Field(min_length=1, max_length=MAX_TEXT_FIELD_LENGTH)
    hub: AutomationHub
    name: str = Field(default="", max_length=MAX_TEXT_FIELD_LENGTH)
    enabled: bool = True
    trigger: WorkflowStep | None = None
    actions: list[WorkflowStep] = Field(default_factory=list)
    source_app_steps: list[StepKind] = Field(
        default_factory=list, description="Where the source app appears in this workflow"
    )
    downstream_apps: list[str] = Field(
        default_factory=list, description="Other apps this workflow writes to"
    )
    breaks_if_decommissioned: bool = True
    critical: bool = False
    criticality_reasons: list[str] = Field(default_factory=list)
    last_successful_run: str | None = None
    url: str = Field(default="", max_length=500)


class DependencyGraph(BaseModel):
    """Source App -> Automation Hub -> downstream apps."""

    model_config = ConfigDict(frozen=True)

    source_app: str = Field(min_length=1, max_length=MAX_TEXT_FIELD_LENGTH)
    hubs: list[AutomationHub] = Field(default_factory=list)
    downstream_apps: list[str] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(
        default_factory=list, description="{'from': ..., 'via': hub, 'to': ..., 'workflow_id': ...}"
    )


class DependencyScan(BaseModel):
    """Audit-trail document stored in ``dependency_graphs`` for one source app."""

    model_config = ConfigDict(frozen=True)

    scan_id: str = Field(default_factory=lambda: f"dep_{uuid4().hex[:12]}", min_length=1)
    proposal_id: str = Field(min_length=1)
    source_app: str = Field(min_length=1, max_length=MAX_TEXT_FIELD_LENGTH)
    workflows: list[DependentWorkflow] = Field(default_factory=list)
    graph: DependencyGraph
    breaking_count: int = Field(default=0, ge=0)
    critical_count: int = Field(default=0, ge=0)
    hubs_scanned: list[AutomationHub] = Field(default_factory=list)
    api_calls: list[dict[str, Any]] = Field(
        default_factory=list, description="Hub requests made (no credentials)"
    )
    warnings: list[str] = Field(default_factory=list)
    scanned_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    scanned_by: str = Field(default="system:integrator_agent", min_length=1)
