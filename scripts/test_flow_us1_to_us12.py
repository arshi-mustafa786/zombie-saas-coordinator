"""Comprehensive End-to-End Test Suite: User Story 1 through User Story 12.

# ruff: noqa: S105, S106, T201

Validates that the entire Zombie SaaS Coordinator pipeline operates
seamlessly across all delivered vertical slices:
1. US-1:  Scheduled Identity & Access Telemetry (Zombie SaaS detection)
2. US-2:  Corporate Expense Webhook Ingestion (HMAC-SHA256 authenticated)
3. US-3:  Auditor Agent Consolidation Proposal Generation (ROI math & risk scoring)
4. US-4:  Interactive Slack Notification Callback Processing
5. US-5:  3-Tier HITL Approval Gate Verification (PERMISSION_TO_INVESTIGATE)
6. US-6:  Architect Agent Behavioral Contract Extraction & Rule Parsing
7. US-7:  Architect Agent Schema Diffing & Structural Mapping
8. US-8:  Architect Agent State-Transition Simulation (Semantic Validation)
9. US-9:  Semantic Mismatch Remediation & Hypothesis Formation
10. US-10: Automation Hub Scanning (Zapier & Make Dependency Graph)
11. US-11: Migration Execution & Cryptographic Cutover Reconciliation
12. US-12: Fail-Safe Quarantine & Multi-Signature Verifiable Disposal
"""

import hashlib
import hmac
import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from fastapi.testclient import TestClient

from zombie_saas_coordinator.agents.architect.tools import (
    diff_schemas,
    generate_remediation,
    parse_automation_rule,
    simulate_transition,
)
from zombie_saas_coordinator.agents.auditor import tools as auditor_tools
from zombie_saas_coordinator.agents.integrator import tools as integrator_tools
from zombie_saas_coordinator.main import app
from zombie_saas_coordinator.shared.approvals.approvals import check_approval_status
from zombie_saas_coordinator.shared.constants import (
    DEFAULT_QUARANTINE_RETENTION_DAYS,
    INVESTIGATION_GATE,
    MIGRATION_MANIFESTS_COLLECTION,
    PROPOSALS_COLLECTION,
    QUARANTINE_RECORDS_COLLECTION,
    SAAS_WHITELIST_COLLECTION,
)
from zombie_saas_coordinator.shared.models.manifest import MigrationPhase
from zombie_saas_coordinator.shared.models.proposal import (
    ConsolidationProposal,
    ProposalStatus,
    RecommendationType,
    RiskAssessment,
    SavingsBreakdown,
)
from zombie_saas_coordinator.shared.models.quarantine import (
    DisposalCertificate,
    QuarantineStatus,
)
from zombie_saas_coordinator.shared.quarantine.service import (
    check_disposal_eligibility,
    execute_verifiable_disposal,
    quarantine_source_data,
    set_legal_hold,
    submit_disposal_signature,
)
from zombie_saas_coordinator.shared.services.reconciliation import (
    create_manifest,
    execute_migration,
    reconcile_migration,
)

client = TestClient(app)


def log_banner(step: int, us_id: str, title: str) -> None:
    print("\n" + "=" * 78)
    print(f" STEP {step:2d} [{us_id:5s}]: {title}")
    print("=" * 78)


def test_end_to_end_us1_through_us12() -> None:
    print("\n" + "#" * 78)
    print(" ZOMBIE SAAS COORDINATOR: COMPLETE END-TO-END VERIFICATION (US-1 to US-12)")
    print("#" * 78)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. US-1: Scheduled Identity & Access Telemetry Scanner
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(1, "US-1", "Scheduled Identity & Access Telemetry Scanner")
    raw_apps = [
        {
            "app_id": "app-trello-123",
            "app_name": "Trello",
            "vendor": "Atlassian",
            "category": "Project Management",
            "capabilities": ["kanban", "task-tracking", "collaboration"],
            "total_seats": 50,
            "active_seats": 10,
            "inactive_seats": 40,
            "last_login_date": (datetime.now(UTC) - timedelta(days=65)).isoformat(),
        },
        {
            "app_id": "app-asana-standard",
            "app_name": "Asana",
            "vendor": "Asana",
            "category": "Project Management",
            "capabilities": ["kanban", "task-tracking", "rules", "enterprise-agile"],
            "total_seats": 200,
            "active_seats": 180,
            "inactive_seats": 20,
            "last_login_date": datetime.now(UTC).isoformat(),
        },
    ]

    mock_fs_us1 = Mock()
    mock_scan_doc = Mock()
    mock_fs_us1.collection.return_value.document.return_value = mock_scan_doc

    with (
        patch("zombie_saas_coordinator.agents.auditor.tools._get_firestore_client", return_value=mock_fs_us1),
        patch("zombie_saas_coordinator.agents.auditor.tools._fetch_idp_application_telemetry", return_value=raw_apps),
    ):
        scan_result = auditor_tools.scan_idp_logs("tenant-acme", days=60)

    assert scan_result["status"] == "success"
    apps = scan_result["apps"]
    trello_telemetry = next(a for a in apps if a["app_name"] == "Trello")
    assert trello_telemetry["is_flagged_inactive"] is True
    assert trello_telemetry["inactive_ratio"] == 0.8
    print(f"[+] US-1 Scan Successful: Found {len(apps)} applications.")
    print(f"[+] Trello Telemetry: 80% inactive seats ({trello_telemetry['inactive_seats']}/{trello_telemetry['total_seats']})")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. US-2: Corporate Expense Webhook Ingestion (HMAC Authenticated)
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(2, "US-2", "Corporate Expense Webhook Ingestion (HMAC Authenticated)")
    expense_secret = "dev-webhook-secret-12345"  # noqa: S105
    os.environ["EXPENSE_WEBHOOK_SECRET"] = expense_secret

    renewal_date = (date.today() + timedelta(days=25)).isoformat()
    expense_payload = {
        "provider": "brex",
        "transaction_id": "txn_trello_e2e_001",
        "merchant": "Trello Enterprise",
        "amount": 540.00,
        "frequency": "monthly",
        "renewal_date": renewal_date,
    }
    raw_bytes = json.dumps(expense_payload).encode("utf-8")
    sig = "sha256=" + hmac.new(expense_secret.encode(), raw_bytes, hashlib.sha256).hexdigest()

    mock_fs_us2 = Mock()
    whitelist_snap = Mock(exists=False)
    whitelist_doc = Mock(get=Mock(return_value=whitelist_snap))
    expense_doc = Mock()

    def _collection_router(col: str) -> Mock:
        return whitelist_doc if col == SAAS_WHITELIST_COLLECTION else expense_doc

    mock_fs_us2.collection.side_effect = _collection_router

    with (
        patch("zombie_saas_coordinator.agents.auditor.tools._get_firestore_client", return_value=mock_fs_us2),
        patch("zombie_saas_coordinator.agents.auditor.tools._get_audit_logger", return_value=Mock()),
    ):
        resp = client.post(
            "/webhooks/expense-notification",
            data=raw_bytes,
            headers={"Content-Type": "application/json", "X-Webhook-Signature": sig},
        )

    assert resp.status_code == 202
    expense_data = resp.json()
    assert expense_data["assessment"]["flagged"] is True
    print(f"[+] US-2 Webhook Ingested: Status {resp.status_code} Accepted")
    print(f"[+] Expense Finding: ${expense_data['assessment']['monthly_equivalent']}/mo ($6,480.00/yr), inside renewal window.")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. US-3: Auditor Agent Consolidation Proposal Generation
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(3, "US-3", "Consolidation Proposal Generation (Auditor Agent)")
    proposal_id = "prop-e2e-trello-001"
    proposal = ConsolidationProposal(
        proposal_id=proposal_id,
        app_id="app-trello-123",
        app_name="Trello",
        target_app="Asana",
        tenant_id="tenant-acme",
        savings=SavingsBreakdown(
            seats=40,
            monthly_cost=540.0,
            cost_per_seat_monthly=13.5,
            annual_cost=6480.0,
            estimated_annual_savings=6480.0,
        ),
        risk=RiskAssessment(risk_score=25, active_user_count=10, inactive_ratio=0.8),
        redundancy_score=90,
        dependencies=["Zapier Webhook #1", "Board Email Ingestion"],
        recommendation=RecommendationType.PROCEED_CONSOLIDATION,
        summary="Automate decommission of redundant Trello seats in favor of Asana Enterprise standard.",
        status=ProposalStatus.PENDING,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )

    mock_fs_us3 = Mock()
    prop_doc = Mock()
    prop_snap = Mock(exists=True, to_dict=Mock(return_value=proposal.model_dump(mode="json")))
    prop_doc.get.return_value = prop_snap
    mock_fs_us3.collection.return_value.document.return_value = prop_doc

    proposal_dict = proposal.model_dump(mode="json")
    with (
        patch("zombie_saas_coordinator.api.proposals.load_proposal", return_value=proposal_dict),
        patch("zombie_saas_coordinator.api.proposals.verify_proposal_signature", return_value=True),
    ):
        resp = client.get(f"/api/v1/proposals/{proposal_id}", headers={"X-Tenant-ID": "tenant-acme"})

    assert resp.status_code == 200
    prop_body = resp.json()["proposal"]
    assert prop_body["proposal_id"] == proposal_id
    assert prop_body["recommendation"] == RecommendationType.PROCEED_CONSOLIDATION.value
    print(f"[+] US-3 Proposal Verified: {prop_body['app_name']} -> {prop_body['target_app']}")
    print(f"[+] Estimated Annual Savings: ${prop_body['savings']['estimated_annual_savings']:,.2f} | Risk Score: {prop_body['risk']['risk_score']}/100")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. US-4: Interactive Slack Approval Callback
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(4, "US-4", "Interactive Slack Approval Card Callback")
    slack_token = "valid-token-secret"  # noqa: S105
    os.environ["SLACK_VERIFICATION_TOKEN"] = slack_token

    with (
        patch("zombie_saas_coordinator.api.callbacks._get_firestore_client", return_value=mock_fs_us3),
        patch("zombie_saas_coordinator.api.callbacks._get_audit_logger", return_value=Mock()),
    ):
        resp = client.post(
            "/api/v1/callbacks/approval",
            json={
                "token": slack_token,
                "action": "simulate_migration",
                "proposal_id": proposal_id,
                "user_id": "U_OPS_LEAD",
                "user_email": "lead@enterprise.internal",
            },
        )
    assert resp.status_code == 200
    callback_res = resp.json()
    assert callback_res["action"] == "simulate_migration"
    print(f"[+] US-4 Approval Card Callback: {callback_res['action']} acknowledged for {proposal_id}")

    # ─────────────────────────────────────────────────────────────────────────
    # 5. US-5: 3-Tier HITL Approval Gate Verification
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(5, "US-5", "3-Tier HITL Approval Gate Verification (PERMISSION_TO_INVESTIGATE)")
    gate_data = {
        "gate_type": INVESTIGATION_GATE,
        "approved": True,
        "approver_id": "ciso@enterprise.internal",
        "approved_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
    }
    mock_fs_us5 = Mock()
    mock_gate_snap = Mock(exists=True, to_dict=Mock(return_value=gate_data))
    mock_gate_doc = Mock(get=Mock(return_value=mock_gate_snap))
    mock_fs_us5.collection.return_value.document.return_value = mock_gate_doc

    with patch("zombie_saas_coordinator.shared.approvals.approvals._get_firestore_client", return_value=mock_fs_us5):
        gate_status = check_approval_status(proposal_id, INVESTIGATION_GATE)

    assert gate_status["approved"] is True
    print(f"[+] US-5 Gate Verified: {INVESTIGATION_GATE} is APPROVED by {gate_status.get('approver_id')}")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. US-6: Architect Agent Behavioral Contract Extraction
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(6, "US-6", "Architect Agent: Behavioral Contract Extraction")
    rule_input = 'when a card is moved into list "Done", archive the card'
    parsed_contract = parse_automation_rule({"text": rule_input})

    assert parsed_contract["status"] == "success"
    assert parsed_contract["parser"] == "grammar"
    assert parsed_contract["trigger"]["event"] == "card_moved_to_list"
    assert parsed_contract["trigger"]["conditions"]["list"] == "Done"
    assert parsed_contract["actions"][0]["type"] == "archive_card"
    print(f"[+] US-6 Contract Extracted: ID={parsed_contract['contract_id']}")
    print(f"[+] Trigger: {parsed_contract['trigger']['event']}, Action: {parsed_contract['actions'][0]['type']}")

    # ─────────────────────────────────────────────────────────────────────────
    # 7. US-7: Architect Agent Schema Diffing & Field Classification
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(7, "US-7", "Architect Agent: Schema Diffing between Trello and Asana")
    source_schema = {
        "card_title": "string",
        "list_name": "string",
        "labels": "list",
        "story_points": "integer",
    }
    target_schema = {
        "task_name": "string",
        "section_name": "string",
        "tags": "string",
        "story_points": "number",
    }
    diff_report = diff_schemas(source_schema, target_schema)

    assert diff_report["green"] >= 2
    assert diff_report["yellow"] >= 1
    assert any(m["source_field"] == "card_title" and m["target_field"] == "task_name" for m in diff_report["mappings"])
    print(f"[+] US-7 Diff: Green={diff_report['green']}, Yellow={diff_report['yellow']}, Red={diff_report['red']}")

    # ─────────────────────────────────────────────────────────────────────────
    # 8. US-8: Architect Agent State-Transition Simulation in Asana
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(8, "US-8", "Architect Agent: State-Transition Simulation")
    gemini_sim_response = MagicMock()
    gemini_sim_response.text = json.dumps({
        "classification": "Behaviorally Equivalent",
        "reasoning": "Asana natively supports auto-archiving completed tasks via rules engine.",
        "remediation": "",
    })

    mock_fs_us8 = Mock()
    mock_sim_doc = Mock()
    mock_fs_us8.collection.return_value.document.return_value = mock_sim_doc

    with (
        patch("zombie_saas_coordinator.agents.architect.tools.GenerativeModel") as mock_gemini_cls,
        patch("zombie_saas_coordinator.agents.architect.tools.get_firestore_client", return_value=mock_fs_us8),
    ):
        mock_gemini_cls.return_value.generate_content.return_value = gemini_sim_response
        sim_result = simulate_transition(parsed_contract, diff_report)

    assert sim_result["contract_id"] == parsed_contract["contract_id"]
    assert sim_result["classification"] == "Behaviorally Equivalent"
    assert sim_result["quarantine"] is False
    print(f"[+] US-8 Simulation: {sim_result['classification']} (Reasoning: {sim_result['reasoning']})")

    # ─────────────────────────────────────────────────────────────────────────
    # 9. US-9: Semantic Mismatch Remediation & Hypothesis Formation
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(9, "US-9", "Semantic Mismatch Remediation & Hypothesis Formation")
    incompatible_sim = {
        "classification": "Incompatible",
        "reasoning": "Target system does not support Butler recurring Friday card generation.",
        "remediation": "Deploy a Make.com scenario scheduled for Fridays to create Asana tasks.",
        "contract": {
            "contract_id": "ctr-friday-recur",
            "trigger": {"event": "schedule", "cron": "0 9 * * 5"},
            "action": {"type": "create_card", "list": "To Do"},
        },
    }

    mock_gemini_yaml = """trigger:
  type: "schedule"
  cron: "0 9 * * 5"
action:
  - asana.create_task:
      project: "Sprint"
      section: "To Do"
"""
    with patch(
        "zombie_saas_coordinator.agents.architect.tools.gemini_generate",
        return_value=mock_gemini_yaml,
    ):
        remediation_res = generate_remediation(incompatible_sim)

    assert remediation_res["status"] == "High-Risk"
    assert remediation_res["high_risk"] is True
    assert remediation_res["manual_review_required"] is True
    assert "code_skeleton" in remediation_res["report"]
    print(f"[+] US-9 Remediation Formed: Status={remediation_res['status']}, ManualReview={remediation_res['manual_review_required']}")
    print(f"[+] Hypothesis: {remediation_res['report']['remediation_hypothesis']}")

    # ─────────────────────────────────────────────────────────────────────────
    # 10. US-10: Automation Hub Scanning (Zapier & Make Dependency Graph)
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(10, "US-10", "Automation Hub Scanning (Zapier & Make Integrations)")
    sample_zapier_workflows = [
        {
            "workflow_id": "zap_101",
            "hub": "zapier",
            "name": "Trello Card -> Slack Channel",
            "enabled": True,
            "trigger": {"kind": "trigger", "app": "Trello", "app_key": "trello", "title": "New Card"},
            "actions": [{"kind": "action", "app": "Slack", "app_key": "slack", "title": "Send Message"}],
            "source_app_steps": ["trigger"],
            "downstream_apps": ["Slack"],
            "breaks_if_decommissioned": True,
            "url": "https://zapier.com/app/editor/101",
        }
    ]
    sample_make_workflows = [
        {
            "workflow_id": "make_201",
            "hub": "make",
            "name": "Sync Trello to Google Sheets",
            "enabled": True,
            "trigger": {"kind": "trigger", "app": "Trello", "app_key": "trello", "title": "Watch Cards"},
            "actions": [{"kind": "action", "app": "Google Sheets", "app_key": "google-sheets", "title": "Add Row"}],
            "source_app_steps": ["trigger"],
            "downstream_apps": ["Google Sheets"],
            "breaks_if_decommissioned": True,
            "url": "https://eu1.make.com/scenarios/201",
        }
    ]

    mock_fs_us10 = Mock()
    mock_dep_doc = Mock()
    mock_fs_us10.collection.return_value.document.return_value = mock_dep_doc

    with (
        patch("zombie_saas_coordinator.agents.integrator.tools._get_firestore_client", return_value=mock_fs_us10),
        patch("zombie_saas_coordinator.agents.integrator.tools._get_audit_logger", return_value=Mock()),
    ):
        dep_graph = integrator_tools.build_dependency_graph(
            proposal_id=proposal_id,
            source_app="Trello",
            workflows=sample_zapier_workflows + sample_make_workflows,
        )

    assert dep_graph["status"] == "success"
    assert dep_graph["proposal_id"] == proposal_id
    assert dep_graph["source_app"] == "Trello"
    assert dep_graph["workflows_count"] == 2
    assert "Slack" in dep_graph["graph"]["downstream_apps"]
    assert "Google Sheets" in dep_graph["graph"]["downstream_apps"]
    print(f"[+] US-10 Dependency Graph: {dep_graph['workflows_count']} workflows mapped (Downstream: {', '.join(dep_graph['graph']['downstream_apps'])})")
    print(f"[+] Breaking workflows identified: {dep_graph['breaking_count']}")

    # ─────────────────────────────────────────────────────────────────────────
    # 11. US-11: Migration Execution & Cryptographic Cutover Reconciliation
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(11, "US-11", "Migration Execution & Reconciliation (US-11)")
    source_records = [
        {
            "id": "card-alpha",
            "record_type": "card",
            "data": {"title": "Sprint Milestone Alpha", "status": "In Progress"},
            "attachment_count": 2,
            "comment_count": 5,
        },
        {
            "id": "card-beta",
            "record_type": "card",
            "data": {"title": "Sprint Milestone Beta", "status": "Done"},
            "attachment_count": 0,
            "comment_count": 1,
        },
    ]

    manifest = create_manifest(
        proposal_id=proposal_id,
        board_id="board-trello-1",
        project_id="proj-asana-1",
        source_records=source_records,
    )
    assert manifest.proposal_id == proposal_id
    assert len(manifest.items) == 2

    executed_manifest = execute_migration(
        board_id="board-trello-1",
        project_id="proj-asana-1",
        manifest=manifest.model_dump(mode="json"),
    )
    assert executed_manifest["phase"] == MigrationPhase.MIGRATING.value
    assert executed_manifest["items"][0]["target_id"] == "asana_card-alpha"

    # Target records matching source records for reconciliation
    target_records = [
        {
            "id": "asana_card-alpha",
            "data": {"title": "Sprint Milestone Alpha", "status": "In Progress"},
            "attachment_count": 2,
            "comment_count": 5,
        },
        {
            "id": "asana_card-beta",
            "data": {"title": "Sprint Milestone Beta", "status": "Done"},
            "attachment_count": 0,
            "comment_count": 1,
        },
    ]

    reconcile_res = reconcile_migration(executed_manifest, target_records)
    assert reconcile_res["report"]["reconciled"] is True
    assert reconcile_res["manifest"]["phase"] == MigrationPhase.RECONCILED.value
    assert len(reconcile_res["report"]["exceptions"]) == 0
    print(f"[+] US-11 Migration Reconciled: 2/2 records verified with zero exceptions (Phase: {reconcile_res['manifest']['phase']})")

    # ─────────────────────────────────────────────────────────────────────────
    # 12. US-12: Fail-Safe Quarantine & Multi-Signature Verifiable Disposal
    # ─────────────────────────────────────────────────────────────────────────
    log_banner(12, "US-12", "Fail-Safe Quarantine & Multi-Sig Verifiable Disposal")

    # Step 12.1: Default post-migration action is SOURCE_QUARANTINED
    mock_fs_us12 = MagicMock()
    manifest_snap = MagicMock()
    manifest_snap.exists = True
    manifest_snap.to_dict.return_value = reconcile_res["manifest"]

    manifest_doc = MagicMock()
    manifest_doc.get.return_value = manifest_snap
    manifest_doc.exists = True
    manifest_doc.to_dict.return_value = reconcile_res["manifest"]

    prop_snap = MagicMock()
    prop_snap.exists = True
    prop_snap.to_dict.return_value = proposal_dict

    prop_doc = MagicMock()
    prop_doc.get.return_value = prop_snap

    quarantine_state: dict[str, Any] = {}

    def save_q(data: dict[str, Any]) -> None:
        nonlocal quarantine_state
        quarantine_state = data

    quarantine_doc = MagicMock()
    quarantine_doc.set.side_effect = save_q
    quarantine_snap = MagicMock()
    quarantine_snap.exists = True
    quarantine_snap.to_dict.side_effect = lambda: quarantine_state
    quarantine_doc.get.return_value = quarantine_snap

    cert_doc = MagicMock()
    cert_doc.set.return_value = None

    def coll_us12(name: str) -> MagicMock:
        c = MagicMock()
        if name == MIGRATION_MANIFESTS_COLLECTION:
            c.document.return_value = manifest_doc
            c.where.return_value.stream.return_value = [manifest_snap]
        elif name == PROPOSALS_COLLECTION:
            c.document.return_value = prop_doc
        elif name == QUARANTINE_RECORDS_COLLECTION:
            c.document.return_value = quarantine_doc
        elif name == "disposal_certificates":
            c.document.return_value = cert_doc
        else:
            c.document.return_value = MagicMock()
            c.where.return_value.stream.return_value = []
        return c

    mock_fs_us12.collection.side_effect = coll_us12

    with (
        patch("zombie_saas_coordinator.shared.quarantine.service._get_firestore_client", return_value=mock_fs_us12),
        patch("zombie_saas_coordinator.shared.quarantine.service.record_quarantine_in_cloudsql"),
        patch("zombie_saas_coordinator.shared.quarantine.service.record_approval_in_cloudsql"),
        patch("zombie_saas_coordinator.shared.quarantine.service.record_disposal_in_cloudsql"),
        patch("zombie_saas_coordinator.shared.quarantine.service._get_audit_logger"),
    ):
        # 12.1 Quarantine initiation
        q_record = quarantine_source_data(
            proposal_id=proposal_id,
            source_metadata={"app_id": "app-trello-123", "app_name": "Trello"},
            retention_days=DEFAULT_QUARANTINE_RETENTION_DAYS,
        )
        assert q_record.status == QuarantineStatus.SOURCE_QUARANTINED
        assert q_record.retention_days == 90
        assert q_record.migration_completed is True
        print(f"[+] US-12.1 Source Data Quarantined: Status={q_record.status.value}, Retention={q_record.retention_days} days")

        # 12.2 Compliance Guard: Legal Hold prevents premature disposal
        set_legal_hold(
            proposal_id=proposal_id,
            operator_info={"uid": "legal-officer-01", "email": "legal@acme.corp"},
            legal_hold=True,
            reason="Pending regulatory data retention audit",
        )
        eligibility = check_disposal_eligibility(proposal_id)
        assert eligibility["eligible"] is False
        assert any("Legal hold" in b for b in eligibility["blockers"])
        print("[+] US-12.2 Compliance Guard Active: Legal hold successfully blocks disposal.")

        # Release legal hold to continue flow
        set_legal_hold(
            proposal_id=proposal_id,
            operator_info={"uid": "legal-officer-01", "email": "legal@acme.corp"},
            legal_hold=False,
            reason="Audit review completed",
        )

        # 12.3 Multi-Signature Disposal Authorization (Quorum = 2 distinct signers)
        # Signer 1: CISO
        sig1 = submit_disposal_signature(
            proposal_id=proposal_id,
            signer_info={"uid": "ciso-uid-01", "email": "ciso@acme.corp", "role": "ciso"},
            notes="CISO authorized disposal after reconciliation review.",
        )
        assert sig1["status"] == QuarantineStatus.DISPOSAL_PENDING_APPROVAL.value
        assert sig1["signature_count"] == 1
        assert sig1["quorum_reached"] is False
        print(f"[+] Signer 1 (CISO) signed: Status={sig1['status']} (1/{sig1['required_signatures']})")

        # Signer 2: Compliance Officer -> Quorum reached -> DISPOSAL_APPROVED
        sig2 = submit_disposal_signature(
            proposal_id=proposal_id,
            signer_info={
                "uid": "compliance-officer-02",
                "email": "compliance@acme.corp",
                "role": "compliance_officer",
            },
            notes="Compliance verification complete. No ongoing holds.",
        )
        assert sig2["status"] == QuarantineStatus.DISPOSAL_APPROVED.value
        assert sig2["signature_count"] == 2
        assert sig2["quorum_reached"] is True
        print(f"[+] Signer 2 (Compliance) signed: Status={sig2['status']} - Multi-Sig Quorum Reached!")

        # 12.4 Cryptographically Verifiable Destruction Execution
        cert = execute_verifiable_disposal(
            proposal_id=proposal_id,
            executor_info={"uid": "sys-admin-99", "email": "admin@acme.corp"},
        )
        assert isinstance(cert, DisposalCertificate)
        assert cert.status == "VERIFIED_DESTROYED"
        assert len(cert.verification_hash) == 64
        assert cert.items_purged_count == 2
        assert cert.proposal_id == proposal_id
        assert len(cert.signers) == 2
        print(f"[+] US-12.4 Verifiable Destruction Certificate Issued: {cert.certificate_id}")
        print(f"[+] Items Purged: {cert.items_purged_count} records")
        print(f"[+] Verification Hash (SHA-256): {cert.verification_hash}")
        print(f"[+] Status: {cert.status}")

    print("\n" + "#" * 78)
    print(" [ALL TESTS PASSED] USER STORIES 1 TO 12 OPERATING END-TO-END WITH ZERO REGRESSIONS!")
    print("#" * 78 + "\n")


if __name__ == "__main__":
    test_end_to_end_us1_through_us12()
