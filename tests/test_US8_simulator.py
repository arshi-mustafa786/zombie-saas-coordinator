"""Tests for US-8 behavioral transition simulation."""

from zombie_saas_coordinator.agents.architect.tools import simulate_transition


def test_simulate_transition_detects_incompatible_auto_archive_behavior() -> None:
    contract = {
        "rule_name": "Archive done cards",
        "trigger": "status == Done",
        "action": "archive card",
        "scope": "board",
    }
    schema_diff = {
        "mappings": [
            {"source_field": "status", "target_field": "status", "classification": "green"},
            {"source_field": "archive", "target_field": None, "classification": "red"},
        ]
    }

    result = simulate_transition(contract, schema_diff)

    assert result["classification"] == "Incompatible"
    assert "archive" in result["reasoning"].lower()
    assert "webhook" in result["remediation"].lower() or "zapier" in result["remediation"].lower()


def test_simulate_transition_accepts_acceptable_custom_field_notification() -> None:
    contract = {
        "trigger": "custom field == Urgent",
        "action": "notify team channel",
    }
    schema_diff = {
        "mappings": [
            {"source_field": "custom_field", "target_field": "custom_field", "classification": "yellow"},
        ]
    }

    result = simulate_transition(contract, schema_diff)

    assert result["classification"] in {"Degraded but Acceptable", "Behaviorally Equivalent"}
