---
story_id: US-8
module_name: simulate_transition
layers: [service, api]
ancestor_stories: [US-6, US-7]
---

## Capabilities

- Accepts a behavioral contract (from US-6 `behavioral_contracts` Firestore collection) and a
  schema diff report (from US-7 `schema_diffs` Firestore collection) as inputs.
- Maps each Trello state transition (e.g., card moved to "Done" list) to its nearest Asana
  equivalent (e.g., task marked "Completed").
- Queries the Asana API to verify whether the mapped status change triggers the expected
  downstream action (notification, automation rule, archive).
- Uses Gemini Pro chain-of-thought reasoning to judge behavioral equivalence when the mapping
  is ambiguous or involves multi-step automation chains.
- Classifies every simulation result into exactly one of three categories:
  - **Behaviorally Equivalent** - Asana has a native feature that replicates the Trello behavior.
  - **Degraded but Acceptable** - A custom webhook or low-code connector can replicate behavior.
  - **Incompatible** - No reasonable mapping exists; item is quarantined for US-9 remediation.
- Persists all simulation results (classification, reasoning, remediation flag) to the Firestore
  `simulation_results` collection with a timestamp and signed system identity.
- Does NOT trigger live Asana webhooks or mutations during simulation (dry-run only).

## Acceptance Criteria

- AC-8.1: Architect Agent simulates each behavioral contract extracted from Trello in Asana context.
- AC-8.2: Trello status changes are mapped to Asana status equivalents before simulation.
- AC-8.3: Checks whether Asana can trigger notifications/automations on custom field changes.
- AC-8.4: Each result is classified as Behaviorally Equivalent, Degraded but Acceptable, or Incompatible.
- AC-8.5: Incompatible items are flagged with `quarantine: true` for downstream US-9 processing.
- AC-8.6: All simulation results are written to Firestore `simulation_results` collection.

## Integration Points

- **US-6 (extract_trello_rules):** Provides the `contract` dict.
  Expected shape: {trigger: str, action: str, scope: str, metadata: dict}.
- **US-7 (diff_schemas):** Provides the `schema_diff` dict.
  Expected shape: {mappings: list[{source_field, target_field, classification}], green_count, yellow_count, red_count}.
- **Gemini Pro (Vertex AI):** Called via google-cloud-aiplatform SDK for chain-of-thought reasoning.
- **Asana API:** Queried read-only to confirm automation capability existence.
- **Firestore simulation_results:** Written to by this tool; read by US-9.

> **Note (US-6/US-7 not yet merged):** During development of US-8, Firestore reads from
> `behavioral_contracts` and `schema_diffs` are replaced by in-memory stub fixtures.
> The production code paths remain correct; stubs are test-only.

## Data Contracts

### Input - contract (from US-6)
```json
{
  "contract_id": "ctr-001",
  "trigger": {"type": "status_change", "from": "In Progress", "to": "Done"},
  "action": {"type": "archive", "target": "card"},
  "scope": "board",
  "metadata": {"butler_rule_id": "rule-abc"}
}
```

### Input - schema_diff (from US-7)
```json
{
  "mappings": [
    {"source_field": "card", "target_field": "task", "classification": "Green"},
    {"source_field": "list", "target_field": "section", "classification": "Green"},
    {"source_field": "Done (list)", "target_field": "Completed (status)", "classification": "Yellow"}
  ],
  "green_count": 2,
  "yellow_count": 1,
  "red_count": 0
}
```

### Output - simulation_result (to Firestore simulation_results)
```json
{
  "contract_id": "ctr-001",
  "classification": "Behaviorally Equivalent",
  "reasoning": "Asana natively archives completed tasks via its rules engine...",
  "remediation_needed": false,
  "quarantine": false,
  "simulated_at": "2026-10-08T12:00:00Z",
  "system_identity": "architect_agent@zombie-saas"
}
```

## Out of Scope

- Executing live Asana mutations during simulation (read-only mode only).
- Writing remediation code skeletons - that is US-9's responsibility.
- Extracting behavioral contracts from Trello - that is US-6's responsibility.
- Diffing schemas - that is US-7's responsibility.
- Handling Zapier/Make workflow dependencies - that is US-10's responsibility.
