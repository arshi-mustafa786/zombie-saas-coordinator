---
story_id: US-6
module_name: behavioral_contract_extraction
layers: [service, api, db]
ancestor_stories: [US-5]
parent_techspec: docs/techspecs/TS-6.md
---

# US-6: Behavioral Contract Extraction Specification

## Capabilities
- After a human approves `PERMISSION_TO_INVESTIGATE` (US-5), the Architect Agent reads one Trello board through the Trello REST API (read-only).
- Records the board structure: lists, labels, custom fields (with dropdown options), checklists, due-date usage and enabled Power-Ups. Card titles and descriptions are never stored.
- Produces behavioral contracts in a canonical `{trigger, actions, scope}` form from two sources:
  1. **Inferred from board activity.** Trello has no public API for Butler automation rules, so repeated trigger→effect pairs in the board's action history (e.g. every card moved into "Done" is archived within seconds) are reported with a confidence score.
  2. **Butler rule text supplied by a user.** Rules copied from the Trello UI are parsed by a deterministic Butler grammar; Gemini Pro handles rules the grammar cannot read, and its output is validated against the canonical vocabulary. Anything still unrecognised is kept as an `unparsed` contract for manual review.
- Stores each extraction as an immutable document in Firestore `behavioral_contracts` (`create`, never overwrite) for US-7.
- Writes every Trello API call (method, path, status, duration — no credentials) and the extracted rules to Cloud Audit Logs, with a SHA-256 of the stored document.

## Acceptance Criteria
- AC-6.1: Architect Agent connects to the Trello API and parses all board configurations.
- AC-6.2: Extracts automation and Power-Up rules in structured format (trigger, action, scope).
- AC-6.3: Records trigger conditions (status change, label addition, ...) and actions (archive, move, notify, ...).
- AC-6.4: Records custom fields, due dates, card labels and checklists.
- AC-6.5: Exports the behavioral contract as a JSON document in Firestore for the audit trail.
- AC-6.6: Logs all API calls and extracted rules to Cloud Audit Logs.
- AC-6.7 (from US-5): Extraction is blocked unless `PERMISSION_TO_INVESTIGATE` is approved, active and unrevoked.

## Known limitation
Butler rules are not exposed by the Trello REST API. Inferred contracts describe observed behavior, not the rule definition, and carry `source: inferred_from_activity` and a `confidence` below 1.0 when the evidence is weaker. Exact rules require the user to supply the rule text (`butler_rules`).

## Integration Points
- Ancestor US-5: `check_approval_status(proposal_id, "PERMISSION_TO_INVESTIGATE")` from `shared/approvals/approvals.py`. If the check raises, `_investigation_gate` fails closed (`GATE_ERROR`).
- Downstream US-7 (Schema Diffing): reads `behavioral_contracts` documents by `proposal_id` and uses `board` (lists, labels, custom fields) as the Trello schema.
- Downstream US-8 (Simulation): uses `contracts[]`; `unparsed` contracts must be flagged for manual review.

## Data Contracts
- `BehavioralContract`: contract_id, source (`butler_rule_text` | `inferred_from_activity`), parser (`grammar` | `gemini` | `activity` | `unparsed`), trigger {event, conditions}, actions [{type, params}], scope, raw_text, confidence (0–1), evidence_count, metadata
- `TriggerEvent`: card_moved_to_list, card_created_in_list, label_added, label_removed, due_marked_complete, card_archived, checklist_completed
- `ActionType`: archive_card, move_card, add_label, remove_label, mark_due_complete, post_comment, notify, set_due_date, add_member
- `BoardSnapshot`: board_id, name, url, closed, lists, labels, custom_fields, power_ups, card/checklist/due-date counts, label_usage
- `ContractExtraction` (Firestore document): extraction_id, proposal_id, board, contracts, api_calls, warnings, extracted_at, extracted_by

## Security
- Trello key/token come from env (local) or Secret Manager (`trello-api-key`, `trello-api-token`) and are sent only in the `Authorization: OAuth` header, never in URLs, logs, results or Firestore.
- `board_id` must be a 24-char hex id or 8-char short link; anything else is rejected before any request (path/query injection).
- Rule text and Trello names are untrusted: they are flattened with `prompt_safe` inside a `<rule_data>` block, and Gemini output is accepted only if it matches the canonical vocabulary and allowed parameter keys.

## Out of Scope
- Comparing against the Asana schema (US-7), simulating transitions (US-8), remediation (US-9).
- Writing to Trello or creating webhooks.
