"""Tests for US-7 schema diffing and mapping classification."""

import pytest

from zombie_saas_coordinator.agents.architect.tools import classify_mapping, diff_schemas


def test_classify_mapping_green_for_direct_equivalent() -> None:
    result = classify_mapping("name", "string", "string")

    assert result["classification"].lower() == "green"
    assert "direct" in result["reason"].lower()


def test_classify_mapping_yellow_for_label_to_tag_conversion() -> None:
    result = classify_mapping("labels", "list", "string")

    assert result["classification"].lower() == "yellow"
    assert "transform" in result["reason"].lower() or "tag" in result["reason"].lower()


def test_diff_schemas_reports_safe_and_unmappable_fields() -> None:
    source_schema = {
        "card_title": "string",
        "list_name": "string",
        "labels": "list",
        "power_up_data": "object",
        "story_points": "integer",
    }
    target_schema = {
        "task_name": "string",
        "section_name": "string",
        "tags": "string",
        "story_points": "number",
    }

    result = diff_schemas(source_schema, target_schema)

    assert result["green"] >= 2
    assert result["yellow"] >= 1
    assert result["red"] >= 1
    assert any(item["source_field"] == "power_up_data" for item in result["mappings"])


def test_diff_schemas_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        diff_schemas("not-a-dict", {})
