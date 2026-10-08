# Module Interface Contract (MIC) — US-6: Behavioral Contract Extraction

| # | Component / Method | Signature | Return Type | Raised Exceptions | Docstring |
|---|-------------------|-----------|-------------|-------------------|-----------|
| 1 | `extract_trello_rules` (Agent Tool) | `extract_trello_rules(proposal_id: str, board_id: str, butler_rules: list[str] \| None = None) -> dict[str, Any]` | `dict[str, Any]` | `None` (errors returned as `{"status": "error" \| "blocked", ...}`) | Extracts a board's behavioral contract after the INVESTIGATE gate passes; stores it in Firestore and audits every API call. |
| 2 | `parse_automation_rule` (Agent Tool) | `parse_automation_rule(raw_rule: dict[str, Any]) -> dict[str, Any]` | `dict[str, Any]` | `None` (errors returned as `{"status": "error"}`) | Normalizes one Butler rule text into `{trigger, actions, scope, metadata}` via grammar, then validated Gemini. |
| 3 | `TrelloClient.fetch_board_bundle` | `fetch_board_bundle(board_id: str) -> dict[str, Any]` | `dict[str, Any]` | `TrelloApiError`, `ValueError` | Read-only fetch of board, lists, labels, custom fields, checklists, cards, Power-Ups and paginated activity. |
| 4 | `validate_board_id` | `validate_board_id(board_id: str) -> str` | `str` | `ValueError` | Accepts only a 24-char hex id or 8-char short link. |
| 5 | `get_trello_credentials` | `get_trello_credentials() -> tuple[str, str]` | `tuple[str, str]` | `TrelloCredentialsError` | Loads the Trello key/token from env or Secret Manager. |
| 6 | `infer_contracts` | `infer_contracts(actions: list[dict[str, Any]], board_id: str) -> list[BehavioralContract]` | `list[BehavioralContract]` | `None` | Reports trigger→effect pairs that repeat consistently in board activity. |
| 7 | `parse_butler_rule` | `parse_butler_rule(text: str) -> tuple[ContractTrigger \| None, list[ContractAction], list[str]]` | `tuple` | `None` | Deterministic Butler grammar; returns trigger, actions and unparsed fragments. |

Deviation from TS-6 draft: `extract_trello_rules` also takes `proposal_id` (needed for the US-5 gate and to link contracts to the proposal) and optional `butler_rules` (Butler rules have no public API). `parse_automation_rule` returns `actions` (a list) because one Butler rule can perform several actions.

### Public Interface Count Gate
- Count: 7 methods
- Limit: ≤ 7 methods
- Status: **PASSED**
