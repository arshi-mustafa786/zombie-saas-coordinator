"""Architect Agent — Tool Functions.

Tool ownership by user story:
- US-6: extract_trello_rules, parse_automation_rule
- US-7: diff_schemas, classify_mapping
- US-8: simulate_transition
- US-9: generate_remediation
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from vertexai.generative_models import GenerativeModel

from zombie_saas_coordinator.shared.db.firestore_client import get_firestore_client

# ──────────────────────────────────────────────
# US-8 constants
# ──────────────────────────────────────────────

SIMULATION_RESULTS_COLLECTION = "simulation_results"
SYSTEM_IDENTITY = "architect_agent@zombie-saas"
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-001")

# Canonical classification values (AC-8.4)
CLASSIFICATION_EQUIVALENT = "Behaviorally Equivalent"
CLASSIFICATION_DEGRADED = "Degraded but Acceptable"
CLASSIFICATION_INCOMPATIBLE = "Incompatible"
VALID_CLASSIFICATIONS = {
    CLASSIFICATION_EQUIVALENT,
    CLASSIFICATION_DEGRADED,
    CLASSIFICATION_INCOMPATIBLE,
}

# Trello list name → Asana task status mapping (AC-8.2)
_TRELLO_TO_ASANA_STATUS: dict[str, str] = {
    "done": "Completed",
    "complete": "Completed",
    "completed": "Completed",
    "finished": "Completed",
    "closed": "Completed",
    "in progress": "In Progress",
    "doing": "In Progress",
    "active": "In Progress",
    "to do": "To Do",
    "todo": "To Do",
    "backlog": "Backlog",
    "blocked": "On Hold",
    "on hold": "On Hold",
}

# ──────────────────────────────────────────────
# US-6: Behavioral Contract Extraction
# ──────────────────────────────────────────────


def extract_trello_rules(board_id: str) -> dict[str, Any]:
    """Connects to Trello API and extracts all automation rules,
    Butler commands, and Power-Up configurations from the specified board.

    Args:
        board_id: The Trello board identifier.

    Returns:
        dict with keys: status, contracts (list of behavioral contracts).
    """
    # TODO: Implement in US-6
    raise NotImplementedError("US-6: extract_trello_rules")


def parse_automation_rule(raw_rule: dict[str, Any]) -> dict[str, Any]:
    """Normalizes a raw Trello Butler/Power-Up rule into a canonical
    contract format: {trigger, action, scope, metadata}.

    Args:
        raw_rule: Raw rule object from Trello API.

    Returns:
        dict with keys: trigger, action, scope, metadata.
    """
    # TODO: Implement in US-6
    raise NotImplementedError("US-6: parse_automation_rule")


# ──────────────────────────────────────────────
# US-7: Schema Diffing & Structural Validation
# ──────────────────────────────────────────────


def diff_schemas(source_schema: dict[str, Any], target_schema: dict[str, Any]) -> dict[str, Any]:
    """Compares the data schemas of Trello and Asana side-by-side.
    Maps: card→task, list→section, board→project.

    Args:
        source_schema: Trello schema definition.
        target_schema: Asana schema definition.

    Returns:
        dict with keys: mappings, green_count, yellow_count, red_count.
    """
    # TODO: Implement in US-7
    raise NotImplementedError("US-7: diff_schemas")


def classify_mapping(field_name: str, source_type: str, target_type: str) -> dict[str, Any]:
    """Classifies a single field mapping as Green (safe),
    Yellow (lossy), or Red (unmappable).

    Args:
        field_name: The field being mapped.
        source_type: The source field data type.
        target_type: The target field data type.

    Returns:
        dict with keys: classification, reason.
    """
    # TODO: Implement in US-7
    raise NotImplementedError("US-7: classify_mapping")


# ──────────────────────────────────────────────
# US-8: State-Transition Simulation (implementation)
# ──────────────────────────────────────────────


def _map_status(trello_status: str) -> str:
    """Maps a Trello list name to its nearest Asana task status equivalent.

    Normalises the input to lowercase for case-insensitive matching before
    looking up the canonical Asana status. Falls back to the original value
    if no mapping is found so the Gemini prompt still receives the raw text.

    Args:
        trello_status: A Trello list name (e.g. "Done", "In Progress").

    Returns:
        The equivalent Asana status string (e.g. "Completed").
    """
    normalised = trello_status.strip().lower()
    return _TRELLO_TO_ASANA_STATUS.get(normalised, trello_status)


def _check_asana_automation(mapped_status: str, action_type: str) -> bool:
    """Queries the Asana API (read-only) to verify whether the target status
    change can trigger the expected downstream action natively.

    Only GET requests are issued — no mutations are performed (AC-8 security).

    Args:
        mapped_status: The Asana status label (e.g. "Completed").
        action_type: The action to check support for (e.g. "archive", "notify").

    Returns:
        True if Asana natively supports the action for that status, else False.
    """
    asana_token = os.getenv("ASANA_ACCESS_TOKEN", "")
    headers = {"Authorization": f"Bearer {asana_token}"} if asana_token else {}

    # Query Asana automation rules endpoint (read-only GET)
    try:
        response = httpx.get(
            "https://app.asana.com/api/1.0/projects",
            params={"opt_fields": "automation_rules,status_options"},
            headers=headers,
            timeout=10.0,
        )
        if response.status_code != 200:
            return False
        data = response.json()
    except (httpx.RequestError, httpx.TimeoutException):
        return False

    # Heuristic: check if Asana supports archiving/notifications on completion
    action_lower = action_type.lower()
    status_lower = mapped_status.lower()
    asana_text = json.dumps(data).lower()

    if "completed" in status_lower and action_lower in {"archive", "notify", "move"}:
        # Asana natively supports these actions on task completion via Rules
        return True
    if action_lower == "notify" and "notification" in asana_text:
        return True
    return (
        action_lower == "custom_field_change" and "custom_fields" in asana_text
    )


def _build_simulation_prompt(
    contract: dict[str, Any],
    schema_diff: dict[str, Any],
    asana_capability: bool,
    mapped_status: str,
) -> str:
    """Constructs the Gemini Pro chain-of-thought prompt for behavioral equivalence.

    The prompt uses structured JSON context blocks so that Gemini reasons about
    concrete data rather than free-form text. Contract field values are embedded
    as JSON-encoded strings to prevent prompt injection from raw user content.

    Args:
        contract: The behavioral contract dict.
        schema_diff: The schema diff dict from US-7.
        asana_capability: Whether Asana natively supports the action.
        mapped_status: The Asana-equivalent status for the Trello trigger.

    Returns:
        A fully constructed prompt string.
    """
    # Encode contract and schema_diff as JSON to contain any injected content
    contract_json = json.dumps(contract, ensure_ascii=True, indent=2)
    schema_json = json.dumps(schema_diff, ensure_ascii=True, indent=2)

    return (
        "You are a SaaS migration expert analyzing behavioral equivalence "
        "between Trello and Asana.\n\n"
        "## Behavioral Contract (source: Trello)\n"
        f"```json\n{contract_json}\n```\n\n"
        "## Schema Diff Report\n"
        f"```json\n{schema_json}\n```\n\n"
        "## Trigger Status Mapping\n"
        f"Trello status '{contract.get('trigger', {}).get('to', '')}' "
        f"maps to Asana status '{mapped_status}'\n\n"
        "## Asana Native Capability Check\n"
        f"Asana API confirms native support for this transition+action: {asana_capability}\n\n"
        "## Task\n"
        "Reason step-by-step about whether the behavioral contract can be "
        "satisfied in Asana.\n"
        "Consider: status equivalence, action support, scope, metadata fields, "
        "and any platform limitations.\n\n"
        "Then output ONLY a JSON object with these exact keys:\n"
        '{"classification": "<Behaviorally Equivalent | Degraded but Acceptable | Incompatible>",\n'
        ' "reasoning": "<concise plain-English explanation>",\n'
        ' "remediation": "<suggestion if Degraded/Incompatible, else empty string>"}\n\n'
        "Do not include any text outside the JSON object."
    )


def _call_gemini(prompt: str) -> dict[str, Any]:
    """Calls Vertex AI GenerativeModel with the simulation prompt.

    Parses the JSON response and validates the classification field.
    Re-raises google.api_core.exceptions.DeadlineExceeded on timeout so
    the caller can return the expected error dict.

    Args:
        prompt: The fully constructed chain-of-thought prompt string.

    Returns:
        dict with keys: classification, reasoning, remediation.

    Raises:
        google.api_core.exceptions.DeadlineExceeded: On Vertex AI timeout.
        ValueError: If response cannot be parsed as valid JSON.
    """
    model = GenerativeModel(GEMINI_MODEL_NAME)
    response = model.generate_content(prompt)

    raw_text = response.text.strip()
    # Strip markdown code fences if Gemini wraps the JSON
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]

    parsed = json.loads(raw_text)

    # Normalise and validate classification
    classification = parsed.get("classification", "").strip()
    if classification not in VALID_CLASSIFICATIONS:
        # Default to Incompatible to avoid false positives
        classification = CLASSIFICATION_INCOMPATIBLE

    return {
        "classification": classification,
        "reasoning": parsed.get("reasoning", ""),
        "remediation": parsed.get("remediation", ""),
    }


def _persist_result(result: dict[str, Any]) -> None:
    """Writes the simulation result document to Firestore simulation_results.

    Args:
        result: The complete simulation result dict including contract_id,
                classification, reasoning, etc.

    Raises:
        Exception: Propagates any Firestore write exception to the caller.
    """
    client = get_firestore_client()
    doc_ref = client.collection(SIMULATION_RESULTS_COLLECTION).document(result["contract_id"])
    doc_ref.set(result)


def simulate_transition(contract: dict[str, Any], schema_diff: dict[str, Any]) -> dict[str, Any]:
    """Simulates the execution of a behavioral contract in Asana.

    Pipeline:
    1. Validates required contract fields (contract_id, trigger).
    2. Maps the Trello trigger status to its Asana equivalent (AC-8.2).
    3. Queries Asana API (read-only) to check native automation support (AC-8.3).
    4. Builds a chain-of-thought prompt and calls Gemini Pro (AC-8.1).
    5. Classifies result as Behaviorally Equivalent / Degraded / Incompatible (AC-8.4).
    6. Sets quarantine=True for Incompatible results (AC-8.5).
    7. Persists the full result to Firestore simulation_results (AC-8.6).

    Args:
        contract: A behavioral contract from extract_trello_rules (US-6).
                  Required keys: contract_id, trigger.
        schema_diff: The schema diff report from diff_schemas (US-7).

    Returns:
        On success: dict with keys classification, reasoning, remediation_needed,
                    quarantine, contract_id, simulated_at, system_identity.
        On Vertex AI timeout: dict with error=True, retry=True.
        On Firestore write failure: classification dict is still returned plus
                                    firestore_write_error=True.

    Raises:
        ValueError: If contract is missing contract_id or trigger.
    """
    import google.api_core.exceptions as gcp_exc

    # ── Step 1: Validate required contract fields ──────────────────────────
    if "contract_id" not in contract:
        raise ValueError("contract is missing required field: contract_id")
    if "trigger" not in contract:
        raise ValueError("contract is missing required field: trigger")

    contract_id: str = contract["contract_id"]
    trigger: dict[str, Any] = contract["trigger"]
    action: dict[str, Any] = contract.get("action", {})
    action_type: str = action.get("type", "")

    # ── Step 2: Map Trello status → Asana status (AC-8.2) ─────────────────
    trello_to_status: str = trigger.get("to", "")
    mapped_status: str = _map_status(trello_to_status)

    # ── Step 3: Check Asana native capability (AC-8.3, read-only) ─────────
    asana_capable: bool = _check_asana_automation(mapped_status, action_type)

    # ── Step 4: Build prompt and call Gemini Pro ───────────────────────────
    prompt = _build_simulation_prompt(contract, schema_diff, asana_capable, mapped_status)

    try:
        gemini_result = _call_gemini(prompt)
    except gcp_exc.DeadlineExceeded:
        return {"error": True, "retry": True}

    # ── Step 5 & 6: Derive remediation_needed and quarantine flags ─────────
    classification: str = gemini_result["classification"]
    is_incompatible = classification == CLASSIFICATION_INCOMPATIBLE
    is_degraded = classification == CLASSIFICATION_DEGRADED
    remediation_needed = is_incompatible or is_degraded
    quarantine = is_incompatible

    # ── Step 7: Persist to Firestore (AC-8.6) ─────────────────────────────
    result: dict[str, Any] = {
        "contract_id": contract_id,
        "classification": classification,
        "reasoning": gemini_result["reasoning"],
        "remediation_needed": remediation_needed,
        "quarantine": quarantine,
        "simulated_at": datetime.now(UTC).isoformat(),
        "system_identity": SYSTEM_IDENTITY,
    }

    firestore_write_error = False
    try:
        _persist_result(result)
    except Exception:
        firestore_write_error = True

    if firestore_write_error:
        result["firestore_write_error"] = True

    return result


# ──────────────────────────────────────────────
# US-9: Semantic Mismatch Detection
# ──────────────────────────────────────────────


def generate_remediation(simulation_result: dict[str, Any]) -> dict[str, Any]:
    """For incompatible simulation results, generates a Semantic Mismatch
    Report with a concrete remediation hypothesis and code skeleton.

    Args:
        simulation_result: Output from simulate_transition.

    Returns:
        dict with keys: report, code_skeleton, risk_level.
    """
    # TODO: Implement in US-9
    raise NotImplementedError("US-9: generate_remediation")
