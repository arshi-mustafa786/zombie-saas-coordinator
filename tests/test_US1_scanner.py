from zombie_saas_coordinator.agents.auditor import tools


def test_scan_idp_logs_returns_usage_snapshot() -> None:
    result = tools.scan_idp_logs("tenant-demo", days=60)

    assert result["status"] == "ok"
    assert isinstance(result["apps"], list)
    assert len(result["apps"]) >= 2

    trello = next(app for app in result["apps"] if app["app_name"] == "Trello")
    assert trello["assigned_seats"] >= 1
    assert trello["inactive_seats"] >= 0
    assert trello["inactive_ratio"] >= 0
    assert trello["days_since_last_login"] >= 0


def test_calculate_redundancy_flags_trello_against_asana() -> None:
    apps = tools.scan_idp_logs("tenant-demo", days=60)["apps"]
    result = tools.calculate_redundancy(apps)

    assert result["status"] == "ok"
    assert any(item["app_name"] == "Trello" for item in result["flagged"])
    assert any(item["standard_tool"] == "Asana" for item in result["flagged"])
    assert all(item["confidence"] >= 0 for item in result["flagged"])
