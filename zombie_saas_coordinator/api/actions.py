"""Interactive actions router for CISO & IT Ops Dashboard."""

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from zombie_saas_coordinator.agents.architect.tools import (
    diff_schemas,
    generate_remediation,
    parse_automation_rule,
    simulate_transition,
)
from zombie_saas_coordinator.agents.auditor.tools import flag_subscription
from zombie_saas_coordinator.agents.integrator.tools import build_dependency_graph
from zombie_saas_coordinator.shared.db.firestore_client import get_firestore_client
from zombie_saas_coordinator.shared.models.proposal import (
    ConsolidationProposal,
    ProposalStatus,
    RecommendationType,
    RiskAssessment,
    SavingsBreakdown,
)

router = APIRouter(prefix="/api/v1/actions", tags=["dashboard-actions"])


class CreateProposalRequest(BaseModel):
    app_name: str = Field(default="Trello")
    target_app: str = Field(default="Asana")
    tenant_id: str = Field(default="tenant-demo-corp")
    seats: int = Field(default=15, ge=1)
    monthly_cost: float = Field(default=675.0, ge=0.0)


class ExpenseSimulateRequest(BaseModel):
    merchant: str = Field(default="Trello")
    amount: float = Field(default=120.0, ge=0.0)
    frequency: str = Field(default="monthly")
    renewal_days_ahead: int = Field(default=25, ge=1)


@router.get("/overview")
def get_overview_stats() -> dict[str, Any]:
    """Provides high-level dashboard telemetry directly from Firestore collections."""
    db = get_firestore_client()
    stats = {
        "scans_count": 0,
        "proposals_count": 0,
        "manifests_count": 0,
        "quarantines_count": 0,
        "active_proposal": None,
        "recent_scans": [],
    }

    try:
        scans = list(db.collection("scans").order_by("timestamp", direction="DESCENDING").limit(5).stream())
        stats["scans_count"] = len(scans)
        stats["recent_scans"] = [s.to_dict() for s in scans]
    except Exception:
        # Fallback if unindexed or empty
        try:
            scans = list(db.collection("scans").limit(5).stream())
            stats["scans_count"] = len(scans)
            stats["recent_scans"] = [s.to_dict() for s in scans]
        except Exception:
            pass

    try:
        proposals = list(db.collection("consolidation_proposals").limit(10).stream())
        stats["proposals_count"] = len(proposals)
        if proposals:
            stats["active_proposal"] = proposals[0].to_dict()
    except Exception:
        pass

    try:
        manifests = list(db.collection("migration_manifests").limit(10).stream())
        stats["manifests_count"] = len(manifests)
    except Exception:
        pass

    try:
        quarantines = list(db.collection("quarantine_records").limit(10).stream())
        stats["quarantines_count"] = len(quarantines)
    except Exception:
        pass

    return {"status": "success", "stats": stats}


@router.post("/create-proposal")
def create_dashboard_proposal(payload: CreateProposalRequest) -> dict[str, Any]:
    """Generates an active consolidation proposal in Firestore for demonstration."""
    unique_id = uuid.uuid4().hex[:6]
    proposal_id = f"prop-{payload.app_name.lower()}-{unique_id}"
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=7)

    cost_per_seat = round(payload.monthly_cost / payload.seats, 2)
    annual_savings = round(payload.monthly_cost * 12, 2)

    proposal = ConsolidationProposal(
        proposal_id=proposal_id,
        app_id=f"app_{payload.app_name.lower()}_01",
        app_name=payload.app_name,
        target_app=payload.target_app,
        tenant_id=payload.tenant_id,
        savings=SavingsBreakdown(
            seats=payload.seats,
            monthly_cost=payload.monthly_cost,
            cost_per_seat_monthly=cost_per_seat,
            estimated_annual_savings=annual_savings,
        ),
        risk=RiskAssessment(
            risk_score=28,
            active_user_count=max(1, payload.seats // 4),
            inactive_ratio=0.75,
            risk_factors=[
                f"High inactivity ratio (75% of {payload.app_name} seats idle >60 days)",
                f"Redundant capability with enterprise standard ({payload.target_app})",
            ],
        ),
        redundancy_score=85,
        dependencies=["Zapier Webhook #42", "Slack Channel Notifications"],
        recommendation=RecommendationType.PROCEED_CONSOLIDATION,
        summary=(
            f"Consolidation proposal for {payload.app_name}. Cancelling it saves an estimated "
            f"${annual_savings:,.2f}/year (${payload.monthly_cost:,.2f}/month). Risk score 28/100."
        ),
        status=ProposalStatus.PENDING,
        created_at=now,
        expires_at=expires_at,
    )

    db = get_firestore_client()
    db.collection("consolidation_proposals").document(proposal_id).set(
        proposal.model_dump(mode="json")
    )

    return {"status": "created", "proposal": proposal.model_dump(mode="json")}


@router.post("/simulate-expense")
def simulate_expense_assessment(payload: ExpenseSimulateRequest) -> dict[str, Any]:
    """Simulates corporate expense ingestion (US-2) and runs auditor policy evaluation."""
    renewal_date = (date.today() + timedelta(days=payload.renewal_days_ahead)).isoformat()
    event_data = {
        "event_id": f"evt_{uuid.uuid4().hex[:8]}",
        "provider": "brex",
        "merchant": payload.merchant,
        "amount": payload.amount,
        "frequency": payload.frequency,
        "renewal_date": renewal_date,
        "transaction_id": f"txn_{uuid.uuid4().hex[:8]}",
    }
    assessment = flag_subscription(event_data)
    return {"event": event_data, "assessment": assessment}


@router.post("/run-architect")
def run_architect_validation(
    board_id: str = Query(default="board_trello_demo"),
    rule_text: str = Query(default="when a card is moved to Done, archive the card"),
    proposal_id: str = Query(default="prop-trello-demo"),
) -> dict[str, Any]:
    """Runs US-6, US-7, US-8, US-9: Behavioral contracts, schema diff, simulation & remediation."""
    # 1. Parse rule
    parsed_rule = parse_automation_rule(rule_text)

    # 2. Schema diff
    trello_schema = {
        "fields": ["name", "desc", "idList", "labels", "due", "customFields"],
        "entity": "card",
    }
    asana_schema = {
        "fields": ["name", "notes", "memberships.section", "tags", "due_on", "custom_fields"],
        "entity": "task",
    }
    diff = diff_schemas(trello_schema, asana_schema)

    # 3. Build contract & run state transition simulation
    contract = {
        "contract_id": f"cnt_{uuid.uuid4().hex[:8]}",
        "proposal_id": proposal_id,
        "trigger": parsed_rule.get("trigger", {"type": "card_moved", "target": "Done"}),
        "actions": [parsed_rule.get("action", {"type": "archive"})],
        "rule_text": rule_text,
    }
    simulation = simulate_transition(contract, diff)

    # 4. Remediation hypothesis
    remediation = generate_remediation(simulation)

    return {
        "status": "validated",
        "parsed_rule": parsed_rule,
        "schema_diff": diff,
        "simulation": simulation,
        "remediation": remediation,
    }



@router.post("/run-integrator")
def run_integrator_scan(
    app_name: str = Query(default="Trello"),
    proposal_id: str = Query(default="prop-trello-demo"),
) -> dict[str, Any]:
    """Runs US-10: Scans automation dependencies (Zapier / Make) and builds a graph."""
    workflows = [
        {
            "workflow_id": "zap_101",
            "hub": "zapier",
            "name": f"Sync new {app_name} cards to Google Sheets",
            "enabled": True,
            "trigger": {"kind": "trigger", "app": app_name, "title": "New Card in List"},
            "actions": [{"kind": "action", "app": "Google Sheets", "title": "Create Spreadsheet Row"}],
            "downstream_apps": ["Google Sheets"],
            "breaks_if_decommissioned": True,
        },
        {
            "workflow_id": "zap_102",
            "hub": "zapier",
            "name": f"Post urgent {app_name} updates to Slack",
            "enabled": True,
            "trigger": {"kind": "trigger", "app": app_name, "title": "Card Labeled Urgent"},
            "actions": [{"kind": "action", "app": "Slack", "title": "Send Channel Message"}],
            "downstream_apps": ["Slack"],
            "breaks_if_decommissioned": True,
        },
        {
            "workflow_id": "make_201",
            "hub": "make",
            "name": f"Archive completed {app_name} attachments to Drive",
            "enabled": True,
            "trigger": {"kind": "trigger", "app": app_name, "title": "Watch Archived Cards"},
            "actions": [{"kind": "action", "app": "Google Drive", "title": "Upload a File"}],
            "downstream_apps": ["Google Drive"],
            "breaks_if_decommissioned": True,
        },
    ]

    graph = build_dependency_graph(
        proposal_id=proposal_id,
        source_app=app_name,
        workflows=workflows,
    )
    return {"status": "completed", "dependency_graph": graph}

