---
story_id: US-8
story_title: "State-Transition Simulation (Semantic Validation)"
complexity: L
layers: [service, api]
depends_on: [US-7]
blocks: [US-9]
agent: architect_agent
framework: Google ADK (google-adk)
---

## Story Summary
As a Technical Lead, I want the system to simulate what happens when a Trello card transitions to a 'Done' state in Asana, so we verify downstream automations.

## Vertical Scope
This story is a complete vertical slice:
- **DB layer:** Updates validation report in Firestore `simulation_results`
- **Service layer:** ADK Tool function (`simulate_transition`) on the **Architect Agent** using **Gemini Pro** for chain-of-thought reasoning
- **API layer:** Cloud Run — invoked as part of the Architect Agent's validation pipeline
- **UI layer:** N/A

## Agent Architecture (Google ADK)

This tool is added to the `architect_agent`. It uses Gemini Pro's reasoning capabilities to simulate behavioral equivalence:

```python
def simulate_transition(contract: dict, schema_diff: dict) -> dict:
    """Simulates the execution of a behavioral contract in the
    target platform (Asana). For each contract rule:
    1. Maps source state transition to target equivalent
       (e.g., Trello 'Done' → Asana 'Completed')
    2. Queries Asana API to verify if the target status triggers
       the expected downstream action (e.g., auto-archive)
    3. Uses Gemini Pro chain-of-thought to reason about behavioral
       equivalence across platforms

    Classifies each simulation result as:
    - Behaviorally Equivalent: Target platform has native feature
    - Degraded but Acceptable: Custom webhook can replicate behavior
    - Incompatible: No reasonable mapping exists, quarantine required

    Stores simulation results in Firestore."""
    ...
```

**Note:** Complexity reduced from XL to L. The original XL rating assumed a custom simulation engine; with Gemini Pro doing the reasoning, the tool function itself is simpler. The complexity is in the prompt engineering, not the code.

## Module Interface Contract (draft)
| Tool Function | Signature | Returns | Raises | Docstring |
|---------------|-----------|---------|--------|-----------|
| `simulate_transition` | `simulate_transition(contract: dict, schema_diff: dict) -> dict` | `{"classification": str, "reasoning": str, "remediation": str}` | `None` | Uses Gemini Pro to simulate behavioral equivalence. |

## Acceptance Criteria
- Architect Agent simulates each behavioral contract in Asana context
- Maps Trello status changes to Asana status equivalents
- Checks if Asana can trigger notifications/automations on custom field changes
- Classifies results as: Behaviorally Equivalent, Degraded but Acceptable, or Incompatible
- Records incompatible items for quarantine
- All simulation results logged to Firestore validation report

## Test Outline
- [ ] Happy path: Equivalent behavior detected and classified correctly.
- [ ] Edge case: Complex multi-step automation with 3+ chained triggers.
- [ ] Security: Simulation logic does not accidentally trigger live Asana webhooks.
- [ ] Security: Prompt injection in behavioral contract text fed to Gemini.
- [ ] Error path: Vertex AI API timeout — tool returns error dict with retry flag.

## Files to Create or Modify
| Action   | File path                                    | Reason               |
|----------|----------------------------------------------|----------------------|
| MODIFY   | zombie_saas_coordinator/agents/architect/tools.py | Add simulation tool |
| MODIFY   | zombie_saas_coordinator/agents/architect/prompt.py | Update instructions |
| CREATE   | tests/test_US8_simulator.py                  | Tests                |

## Dependencies & Integration Points
- **US-7:** Reads schema diff report from Firestore.
- **US-6:** Reads behavioral contracts from Firestore.
- Downstream: US-9 (Semantic Mismatch Detection) processes incompatible results.
- Gemini Pro (Vertex AI) provides chain-of-thought reasoning.
