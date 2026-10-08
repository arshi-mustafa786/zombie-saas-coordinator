---
story_id: US-8
module_name: simulate_transition
mic_version: 1.0
max_public_methods: 7
public_method_count: 1
---

# Module Interface Contract — US-8 State-Transition Simulation

## Public Methods

| # | Method | Signature | Returns | Raises | Docstring |
|---|--------|-----------|---------|--------|-----------|
| 1 | `simulate_transition` | `simulate_transition(contract: dict, schema_diff: dict) -> dict` | `{"classification": str, "reasoning": str, "remediation_needed": bool, "quarantine": bool}` | `ValueError` if contract is missing required fields; `RuntimeError` on Vertex AI timeout | Uses Gemini Pro chain-of-thought to simulate behavioral equivalence of a Trello automation contract in the Asana platform. Persists result to Firestore `simulation_results`. |

## Classification Vocabulary (contract)

The `classification` field in the returned dict is ALWAYS one of:

| Value | Meaning |
|-------|---------|
| `"Behaviorally Equivalent"` | Asana has a native feature that replicates the behavior |
| `"Degraded but Acceptable"` | A webhook/connector can bridge the gap |
| `"Incompatible"` | No reasonable mapping; `quarantine=True` set |

## Private Helpers (not exposed)

- `_map_status(trello_status: str) -> str` — maps Trello list names to Asana task status strings
- `_check_asana_automation(mapped_status: str, action_type: str) -> bool` — queries Asana API read-only
- `_call_gemini(prompt: str) -> dict` — wraps Vertex AI GenerativeModel call with retry + timeout
- `_build_simulation_prompt(contract, schema_diff, asana_capability) -> str` — constructs chain-of-thought prompt
- `_persist_result(result: dict) -> None` — writes to Firestore `simulation_results`

## Depth Metrics Target

| Metric | Target |
|--------|--------|
| Public methods | 1 (well within ≤7 limit) |
| Avg cyclomatic complexity | ≥ 4 (achieved via multi-branch status map + classification logic) |
| Afferent couplings | ≤ 8 |
| Test coverage | ≥ 85% |
