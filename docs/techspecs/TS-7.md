---
story_id: US-7
story_title: "Schema Diffing & Structural Validation"
complexity: M
layers: [service, api, db]
depends_on: [US-6]
blocks: [US-8]
agent: architect_agent
framework: Google ADK (google-adk)
---

## Story Summary
As a Technical Lead, I want the system to compare the data schemas of Trello and Asana side-by-side, so we identify field-level mismatches before migration begins.

## Vertical Scope
This story is a complete vertical slice:
- **DB layer:** Firestore document `schema_diffs`
- **Service layer:** ADK Tool functions (`diff_schemas`, `classify_mapping`) on the **Architect Agent** using Gemini Pro
- **API layer:** Cloud Run — invoked by Architect Agent as part of validation pipeline
- **UI layer:** N/A

## Agent Architecture (Google ADK)

These tools are added to the `architect_agent` defined in US-6:

```python
def diff_schemas(source_schema: dict, target_schema: dict) -> dict:
    """Compares the data schemas of Trello and Asana side-by-side.
    Maps: card→task, list→section, board→project. For each field,
    compares data types and identifies: direct mappings, lossy
    transformations, and unmappable fields. Uses Gemini Pro for
    semantic type compatibility analysis. Stores diff report in Firestore."""
    ...

def classify_mapping(field_name: str, source_type: str, target_type: str) -> dict:
    """Classifies a single field mapping as:
    - Green (safe): Direct type equivalent exists
    - Yellow (lossy): Requires transformation (e.g., label → custom field)
    - Red (unmappable): No Asana equivalent (e.g., Power-Up data)
    Returns classification with reasoning."""
    ...
```

## Module Interface Contract (draft)
| Tool Function | Signature | Returns | Raises | Docstring |
|---------------|-----------|---------|--------|-----------|
| `diff_schemas` | `diff_schemas(source_schema: dict, target_schema: dict) -> dict` | `{"mappings": list, "green": int, "yellow": int, "red": int}` | `ValueError` | Generates schema diff report. |
| `classify_mapping` | `classify_mapping(field_name: str, source_type: str, target_type: str) -> dict` | `{"classification": str, "reason": str}` | `None` | Returns Green, Yellow, or Red. |

## Acceptance Criteria
- Architect Agent extracts Asana target schema (tasks, projects, sections, custom fields)
- Maps Trello schema to Asana schema (card→task, list→section, board→project)
- Compares custom fields and flags type compatibility issues
- Maps Trello labels to Asana custom fields or tags
- Generates categorized schema diff report (Green, Yellow, Red) stored in Firestore

## Test Outline
- [ ] Happy path: Exact field match (Trello Name → Asana Name) returns Green.
- [ ] Edge case: Trello custom field type has no Asana equivalent (returns Red).
- [ ] Security: Prompt injection in schema field names sent to Gemini.
- [ ] Error path: Asana API returns invalid schema layout.

## Files to Create or Modify
| Action   | File path                                    | Reason               |
|----------|----------------------------------------------|----------------------|
| MODIFY   | zombie_saas_coordinator/agents/architect/tools.py | Add schema tools   |
| CREATE   | zombie_saas_coordinator/shared/integrations/asana.py | Asana API client  |
| CREATE   | tests/test_US7_schema.py                     | Tests                |

## Dependencies & Integration Points
- **US-6:** Reads behavioral contracts to understand source schema structure.
- Downstream: US-8 (State-Transition Simulation) uses the diff report.
- Asana API accessed via OAuth token stored in Secret Manager.
