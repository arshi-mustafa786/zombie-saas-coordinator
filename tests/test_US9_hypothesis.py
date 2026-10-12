"""Tests for US-9 semantic mismatch remediation."""

from zombie_saas_coordinator.agents.architect.tools import generate_remediation


def test_generate_remediation_builds_high_risk_report() -> None:
    simulation_result = {
        "classification": "Incompatible",
        "reasoning": "Asana tasks in Completed state do not auto-archive.",
        "remediation": "Create a Zapier webhook to move completed tasks to an Archive section.",
        "contract": {
            "trigger": "status == Done",
            "action": "archive card",
        },
    }

    result = generate_remediation(simulation_result)

    assert result["status"] == "High-Risk"
    assert result["high_risk"] is True
    report = result["report"]
    assert report["original_contract"]["trigger"] == "status == Done"
    assert "archive" in report["target_capability_gap"].lower()
    assert "zapier" in report["remediation_hypothesis"].lower() or "make" in report["remediation_hypothesis"].lower()
    assert "code_skeleton" in report
