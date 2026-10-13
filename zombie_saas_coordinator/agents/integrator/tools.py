"""Integrator Agent — Tool Functions.

Tool ownership by user story:
- US-10: scan_zapier, scan_make, build_dependency_graph
"""

import os
import re
from typing import Any

from google.cloud import firestore, logging
from pydantic import ValidationError

from zombie_saas_coordinator.shared.approvals.approvals import check_approval_status
from zombie_saas_coordinator.shared.constants import (
    CUSTOMER_FACING_APP_KEYWORDS,
    DEPENDENCY_GRAPHS_COLLECTION,
    DEPENDENCY_SCAN_AUDIT_LOG,
    INVESTIGATION_GATE,
    MAX_BLUEPRINT_DEPTH,
    MAX_TEXT_FIELD_LENGTH,
    MAX_WORKFLOWS_PER_SCAN,
    SCHEDULE_APP_KEYWORDS,
)
from zombie_saas_coordinator.shared.integrations.make import (
    MakeApiError,
    MakeClient,
    MakeCredentialsError,
    get_make_credentials,
)
from zombie_saas_coordinator.shared.integrations.zapier import (
    ZapierApiError,
    ZapierClient,
    ZapierCredentialsError,
    get_zapier_token,
)
from zombie_saas_coordinator.shared.models.dependency import (
    AutomationHub,
    DependencyGraph,
    DependencyScan,
    DependentWorkflow,
    StepKind,
    WorkflowStep,
)

# ──────────────────────────────────────────────
# US-10: Automation Hub Scanning
# ──────────────────────────────────────────────


def _get_firestore_client() -> firestore.Client:
    """Build the Firestore client lazily so importing the agent has no cloud side effects."""
    database = os.getenv("FIRESTORE_DATABASE_ID") or None
    return firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database=database)


def _get_audit_logger() -> Any:
    """Append-only structured logger for automation hub scanning events."""
    client = logging.Client(  # type: ignore[no-untyped-call]
        project=os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    return client.logger(DEPENDENCY_SCAN_AUDIT_LOG)  # type: ignore[no-untyped-call]


def _audit(entry: dict[str, Any], severity: str) -> bool:
    """Write one audit entry; report failure instead of raising."""
    try:
        _get_audit_logger().log_struct(entry, severity=severity)
    except Exception:
        return False
    return True


def _investigation_gate(proposal_id: str) -> dict[str, Any]:
    """US-5 HITL gate: has a human granted PERMISSION_TO_INVESTIGATE for this proposal?

    Fails closed: if the approval check errors, scanning is blocked.
    """
    try:
        return check_approval_status(proposal_id, INVESTIGATION_GATE)
    except Exception as error:
        return {
            "approved": False,
            "status": "GATE_ERROR",
            "message": f"Could not verify approval: {type(error).__name__}",
        }


def _blocked(proposal_id: str, hub: str, gate: dict[str, Any]) -> dict[str, Any]:
    """Audit and report a scan refused by the HITL gate."""
    _audit(
        {
            "event": "hub_scan_blocked",
            "proposal_id": proposal_id,
            "hub": hub,
            "required_gate": INVESTIGATION_GATE,
            "gate_status": gate.get("status"),
        },
        "WARNING",
    )
    return {
        "status": "blocked",
        "error": f"{INVESTIGATION_GATE} is not approved: {gate.get('message', '')}",
        "gate_status": gate.get("status"),
        "workflows": [],
    }


def _matches(app_name: str, *values: str) -> bool:
    """Does any value name the source app? Hub app keys vary (Trello, TrelloAPI, trello)."""
    wanted = app_name.strip().casefold()
    return any(wanted and wanted in str(value).casefold() for value in values if value)


def _clean(value: Any) -> str:
    """Bound and flatten third-party text before it is stored.

    Control characters are stripped so a workflow name cannot forge log lines or
    inject newlines, and the length is capped. Punctuation is kept as-is: these
    names are read by people ("Trello card -> email"), and any tool that later
    puts them in an LLM prompt must call ``prompt_safe`` itself.
    """
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    return text.strip()[:MAX_TEXT_FIELD_LENGTH]


def _zap_step(raw_step: dict[str, Any], kind: StepKind) -> WorkflowStep:
    """One zap step; the app is only present when the request expanded steps.action."""
    action = raw_step.get("action")
    app = action.get("app") if isinstance(action, dict) else None
    app = app if isinstance(app, dict) else {}
    return WorkflowStep(
        kind=kind,
        app=_clean(app.get("title")),
        app_key=_clean(app.get("key")),
        title=_clean(raw_step.get("title")),
    )


def _parse_zap(zap: dict[str, Any], app_name: str) -> DependentWorkflow | None:
    """Turn one zap into a DependentWorkflow, or None if it never touches the source app."""
    raw_steps = [step for step in (zap.get("steps") or []) if isinstance(step, dict)]
    if not raw_steps:
        return None
    # A zap is "a read, followed by one or more writes": the first step is the trigger.
    trigger = _zap_step(raw_steps[0], StepKind.TRIGGER)
    actions = [_zap_step(step, StepKind.ACTION) for step in raw_steps[1:]]

    source_steps = [
        step.kind for step in [trigger, *actions] if _matches(app_name, step.app, step.app_key)
    ]
    if not source_steps:
        return None

    downstream = sorted(
        {
            step.app
            for step in actions
            if step.app and not _matches(app_name, step.app, step.app_key)
        }
    )
    return DependentWorkflow(
        workflow_id=_clean(zap.get("id")) or "unknown",
        hub=AutomationHub.ZAPIER,
        name=_clean(zap.get("title")),
        enabled=bool(zap.get("is_enabled", True)),
        trigger=trigger,
        actions=actions,
        source_app_steps=list(dict.fromkeys(source_steps)),
        downstream_apps=downstream,
        last_successful_run=_clean(zap.get("last_successful_run_date")) or None,
        url=str((zap.get("links") or {}).get("html_editor") or "")[:500],
    )


def _module_app(module: Any) -> str:
    """Make module names look like 'trello:watchCards'; the app is the part before ':'."""
    return str(module or "").split(":")[0]


def _flow_modules(blueprint: dict[str, Any], _depth: int = 0) -> list[dict[str, Any]]:
    """All modules in a blueprint, in flow order, including router branches.

    Order matters: the first module is the scenario's trigger.
    """
    if _depth > MAX_BLUEPRINT_DEPTH:
        return []
    modules: list[dict[str, Any]] = []
    for node in blueprint.get("flow") or []:
        if not isinstance(node, dict):
            continue
        if node.get("module"):
            modules.append(node)
        for branch in node.get("routes") or []:
            if isinstance(branch, dict):
                modules.extend(_flow_modules(branch, _depth + 1))
        if node.get("flow"):
            modules.extend(_flow_modules(node, _depth + 1))
    return modules


def _parse_make_scenario(
    scenario: dict[str, Any], blueprint: dict[str, Any], app_name: str
) -> DependentWorkflow | None:
    """Turn one Make scenario into a DependentWorkflow, or None if it skips the source app."""
    modules = _flow_modules(blueprint)
    if not modules:
        return None
    steps = [
        WorkflowStep(
            kind=StepKind.TRIGGER if index == 0 else StepKind.ACTION,
            app=_clean(_module_app(module.get("module"))),
            app_key=_clean(module.get("module")),
            title=_clean((module.get("metadata") or {}).get("designer", {}).get("name")),
        )
        for index, module in enumerate(modules)
    ]
    source_steps = [step.kind for step in steps if _matches(app_name, step.app, step.app_key)]
    if not source_steps:
        return None

    actions = steps[1:]
    downstream = sorted(
        {
            step.app
            for step in actions
            # 'builtin' modules are routers/filters, not a downstream SaaS tool.
            if step.app and step.app != "builtin" and not _matches(app_name, step.app, step.app_key)
        }
    )
    return DependentWorkflow(
        workflow_id=_clean(scenario.get("id")) or "unknown",
        hub=AutomationHub.MAKE,
        name=_clean(scenario.get("name")),
        enabled=bool(scenario.get("isActive", scenario.get("is_active", True))),
        trigger=steps[0],
        actions=actions,
        source_app_steps=list(dict.fromkeys(source_steps)),
        downstream_apps=downstream,
        last_successful_run=_clean(scenario.get("lastEdit")) or None,
        url="",
    )


def _assess_criticality(workflow: DependentWorkflow) -> tuple[bool, list[str]]:
    """Heuristic: is this workflow critical? Always returns the reasons behind the verdict.

    A disabled workflow is never critical: it is not running, so nothing breaks today.
    It is still reported, because re-enabling it after the migration would break it.
    """
    if not workflow.enabled:
        return False, ["Workflow is currently disabled, so it is not running today"]

    reasons: list[str] = []
    trigger_text = ""
    if workflow.trigger:
        trigger_text = f"{workflow.trigger.app} {workflow.trigger.app_key}".casefold()
    if any(keyword in trigger_text for keyword in SCHEDULE_APP_KEYWORDS):
        reasons.append("Scheduled trigger: runs on a timer (e.g. a daily sync)")

    customer_facing = sorted(
        {
            app
            for app in workflow.downstream_apps
            if any(keyword in app.casefold() for keyword in CUSTOMER_FACING_APP_KEYWORDS)
        }
    )
    if customer_facing:
        reasons.append(f"Customer-facing downstream app(s): {', '.join(customer_facing)}")
    if StepKind.TRIGGER in workflow.source_app_steps:
        reasons.append("The source app is this workflow's trigger, so the workflow stops entirely")
    return bool(reasons), reasons


def scan_zapier(proposal_id: str, app_name: str) -> dict[str, Any]:
    """Connects to the Zapier API (OAuth 2.0) and queries for all active zaps
    containing the specified app as a trigger or action. Requires the US-5
    PERMISSION_TO_INVESTIGATE gate to be approved for the proposal.

    For each matching zap it records the name, trigger, actions and downstream
    app dependencies, and handles pagination for accounts with many zaps.

    Args:
        proposal_id: The approved consolidation proposal this scan belongs to.
        app_name: Name of the SaaS app to search for (e.g., "Trello").

    Returns:
        dict with keys: status, workflows (list), scanned (int), truncated (bool),
        api_calls, warnings. On failure: status "error"/"blocked" with error.
    """
    if not app_name or not app_name.strip():
        return {"status": "error", "error": "app_name must not be empty", "workflows": []}

    gate = _investigation_gate(proposal_id)
    if not gate.get("approved"):
        return _blocked(proposal_id, AutomationHub.ZAPIER.value, gate)

    try:
        token = get_zapier_token()
    except ZapierCredentialsError as error:
        return {"status": "error", "error": str(error), "workflows": []}

    with ZapierClient(token) as client:
        try:
            zaps, truncated = client.fetch_zaps()
        except ZapierApiError as error:
            _audit(
                {
                    "event": "hub_scan_failed",
                    "proposal_id": proposal_id,
                    "hub": AutomationHub.ZAPIER.value,
                    "error": str(error),
                    "api_calls": client.calls,
                },
                "ERROR",
            )
            return {
                "status": "error",
                "error": str(error),
                "status_code": error.status_code,
                "workflows": [],
            }
        api_calls = client.calls

    warnings: list[str] = []
    if truncated:
        warnings.append(
            f"Zapier returned more than {MAX_WORKFLOWS_PER_SCAN} zaps; the scan was truncated."
        )
    try:
        matched = [
            workflow
            for workflow in (_parse_zap(zap, app_name) for zap in zaps if isinstance(zap, dict))
            if workflow is not None
        ]
    except ValidationError as error:
        return {"status": "error", "error": f"Zapier data failed validation: {error}"}

    if matched and all(not workflow.trigger or not workflow.trigger.app for workflow in matched):
        warnings.append("Zap steps carried no app details; the token may lack the zap:all scope.")
    _audit(
        {
            "event": "hub_scan_completed",
            "proposal_id": proposal_id,
            "hub": AutomationHub.ZAPIER.value,
            "app_name": app_name,
            "zaps_scanned": len(zaps),
            "matched": len(matched),
            "api_calls": api_calls,
        },
        "NOTICE",
    )
    return {
        "status": "success",
        "hub": AutomationHub.ZAPIER.value,
        "workflows": [workflow.model_dump(mode="json") for workflow in matched],
        "scanned": len(zaps),
        "truncated": truncated,
        "api_calls": api_calls,
        "warnings": warnings,
    }


def scan_make(proposal_id: str, app_name: str) -> dict[str, Any]:
    """Connects to the Make (Integromat) API and queries for all active scenarios
    referencing the specified app. Requires the US-5 PERMISSION_TO_INVESTIGATE
    gate to be approved for the proposal.

    The scenario list carries no module details, so each scenario's blueprint is
    fetched to find the apps it connects to.

    Args:
        proposal_id: The approved consolidation proposal this scan belongs to.
        app_name: Name of the SaaS app to search for (e.g., "Trello").

    Returns:
        dict with keys: status, workflows (list), scanned (int), truncated (bool),
        api_calls, warnings. On failure: status "error"/"blocked" with error.
    """
    if not app_name or not app_name.strip():
        return {"status": "error", "error": "app_name must not be empty", "workflows": []}

    gate = _investigation_gate(proposal_id)
    if not gate.get("approved"):
        return _blocked(proposal_id, AutomationHub.MAKE.value, gate)

    try:
        token, zone, team_id = get_make_credentials()
    except MakeCredentialsError as error:
        return {"status": "error", "error": str(error), "workflows": []}

    warnings: list[str] = []
    with MakeClient(token, zone, team_id) as client:
        try:
            scenarios, truncated = client.fetch_scenarios()
        except MakeApiError as error:
            _audit(
                {
                    "event": "hub_scan_failed",
                    "proposal_id": proposal_id,
                    "hub": AutomationHub.MAKE.value,
                    "error": str(error),
                    "api_calls": client.calls,
                },
                "ERROR",
            )
            return {
                "status": "error",
                "error": str(error),
                "status_code": error.status_code,
                "workflows": [],
            }

        matched: list[DependentWorkflow] = []
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                continue
            try:
                blueprint = client.fetch_blueprint(scenario.get("id"))
            except (MakeApiError, ValueError) as error:
                # One unreadable blueprint must not discard the whole scan.
                warnings.append(
                    f"Scenario {_clean(scenario.get('id'))}: blueprint unavailable ({error})"
                )
                continue
            try:
                workflow = _parse_make_scenario(scenario, blueprint, app_name)
            except ValidationError as error:
                warnings.append(f"Scenario {_clean(scenario.get('id'))} failed validation: {error}")
                continue
            if workflow is not None:
                matched.append(workflow)
        api_calls = client.calls

    if truncated:
        warnings.append(
            f"Make returned more than {MAX_WORKFLOWS_PER_SCAN} scenarios; the scan was truncated."
        )
    _audit(
        {
            "event": "hub_scan_completed",
            "proposal_id": proposal_id,
            "hub": AutomationHub.MAKE.value,
            "app_name": app_name,
            "scenarios_scanned": len(scenarios),
            "matched": len(matched),
            "api_calls": api_calls,
        },
        "NOTICE",
    )
    return {
        "status": "success",
        "hub": AutomationHub.MAKE.value,
        "workflows": [workflow.model_dump(mode="json") for workflow in matched],
        "scanned": len(scenarios),
        "truncated": truncated,
        "api_calls": api_calls,
        "warnings": warnings,
    }


def build_dependency_graph(
    proposal_id: str, source_app: str, workflows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compiles the Zapier and Make workflows discovered for a source app into a
    dependency graph (Source App -> Automation Hub -> downstream apps), flags the
    workflows that break if the app is decommissioned, marks critical ones
    (scheduled syncs, customer-facing downstream apps), stores the graph in
    Firestore `dependency_graphs` and writes an audit log entry.

    Args:
        proposal_id: The approved consolidation proposal this scan belongs to.
        source_app: The app being decommissioned (e.g., "Trello").
        workflows: The `workflows` lists returned by scan_zapier and scan_make.

    Returns:
        dict with keys: status, scan_id, graph, critical, breaking_count,
        critical_count, workflows_count, warnings, stored, storage_error,
        audit_logged.
    """
    if not source_app or not source_app.strip():
        return {"status": "error", "error": "source_app must not be empty"}
    if not isinstance(workflows, list):
        return {"status": "error", "error": "workflows must be a list"}

    warnings: list[str] = []
    parsed: list[DependentWorkflow] = []
    for entry in workflows[:MAX_WORKFLOWS_PER_SCAN]:
        if not isinstance(entry, dict):
            warnings.append("Skipped a workflow entry that was not an object.")
            continue
        try:
            parsed.append(DependentWorkflow.model_validate(entry))
        except ValidationError as error:
            warnings.append(f"Skipped an invalid workflow entry: {error.errors()[0]['msg']}")
    if len(workflows) > MAX_WORKFLOWS_PER_SCAN:
        warnings.append(f"Only the first {MAX_WORKFLOWS_PER_SCAN} workflows were graphed.")

    assessed: list[DependentWorkflow] = []
    edges: list[dict[str, str]] = []
    downstream: set[str] = set()
    for workflow in parsed:
        critical, reasons = _assess_criticality(workflow)
        assessed.append(
            workflow.model_copy(update={"critical": critical, "criticality_reasons": reasons})
        )
        for app in workflow.downstream_apps:
            downstream.add(app)
            edges.append(
                {
                    "from": source_app,
                    "via": workflow.hub.value,
                    "to": app,
                    "workflow_id": workflow.workflow_id,
                }
            )
        if not workflow.downstream_apps:
            edges.append(
                {
                    "from": source_app,
                    "via": workflow.hub.value,
                    "to": "(no downstream app)",
                    "workflow_id": workflow.workflow_id,
                }
            )

    breaking = [workflow for workflow in assessed if workflow.breaks_if_decommissioned]
    critical = [workflow for workflow in assessed if workflow.critical]
    try:
        scan = DependencyScan(
            proposal_id=proposal_id,
            source_app=source_app,
            workflows=assessed,
            graph=DependencyGraph(
                source_app=source_app,
                hubs=sorted({workflow.hub for workflow in assessed}),
                downstream_apps=sorted(downstream),
                edges=edges,
            ),
            breaking_count=len(breaking),
            critical_count=len(critical),
            hubs_scanned=sorted({workflow.hub for workflow in assessed}),
            warnings=warnings,
            api_calls=[],
        )
    except ValidationError as error:
        return {"status": "error", "error": f"Dependency graph failed validation: {error}"}

    record = scan.model_dump(mode="json")
    stored, storage_error = True, None
    try:
        # ``create`` never overwrites: each scan is an immutable audit record.
        _get_firestore_client().collection(DEPENDENCY_GRAPHS_COLLECTION).document(
            scan.scan_id
        ).create(record)
    except Exception as error:
        stored, storage_error = False, f"Dependency graph could not be stored: {error}"

    audit_logged = _audit(
        {
            "event": "dependency_graph_built",
            "scan_id": scan.scan_id,
            "proposal_id": proposal_id,
            "source_app": source_app,
            "workflows": len(assessed),
            "breaking_count": len(breaking),
            "critical_count": len(critical),
            "downstream_apps": sorted(downstream),
            "stored": stored,
            "warnings": warnings,
        },
        "NOTICE",
    )
    return {
        "status": "success",
        "scan_id": scan.scan_id,
        "proposal_id": proposal_id,
        "source_app": source_app,
        "graph": record["graph"],
        "workflows": record["workflows"],
        "workflows_count": len(assessed),
        "breaking_count": len(breaking),
        "critical_count": len(critical),
        "critical": [
            {
                "workflow_id": workflow.workflow_id,
                "hub": workflow.hub.value,
                "name": workflow.name,
                "reasons": workflow.criticality_reasons,
            }
            for workflow in critical
        ],
        "warnings": warnings,
        "stored": stored,
        "storage_error": storage_error,
        "audit_logged": audit_logged,
    }
