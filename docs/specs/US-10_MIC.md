# Module Interface Contract (MIC) — US-10: Automation Hub Scanning

| # | Component / Method | Signature | Return Type | Raised Exceptions | Docstring |
|---|-------------------|-----------|-------------|-------------------|-----------|
| 1 | `scan_zapier` (Agent Tool) | `scan_zapier(proposal_id: str, app_name: str) -> dict[str, Any]` | `dict[str, Any]` | `None` (errors returned as `{"status": "error" \| "blocked", ...}`) | Lists zaps referencing the app after the INVESTIGATE gate passes; paginated and audited. |
| 2 | `scan_make` (Agent Tool) | `scan_make(proposal_id: str, app_name: str) -> dict[str, Any]` | `dict[str, Any]` | `None` (errors returned as `{"status": "error" \| "blocked", ...}`) | Lists Make scenarios and reads each blueprint to find modules on the app. |
| 3 | `build_dependency_graph` (Agent Tool) | `build_dependency_graph(proposal_id: str, source_app: str, workflows: list[dict]) -> dict[str, Any]` | `dict[str, Any]` | `None` (errors returned as `{"status": "error"}`) | Compiles the graph, flags breaking and critical workflows, stores it in Firestore. |
| 4 | `ZapierClient.fetch_zaps` | `fetch_zaps() -> tuple[list[dict[str, Any]], bool]` | `(zaps, truncated)` | `ZapierApiError` | Paginated read of `/v2/zaps` with `expand=steps.action`. |
| 5 | `MakeClient.fetch_scenarios` | `fetch_scenarios() -> tuple[list[dict[str, Any]], bool]` | `(scenarios, truncated)` | `MakeApiError` | Paginated read of `/api/v2/scenarios` for the configured team. |
| 6 | `MakeClient.fetch_blueprint` | `fetch_blueprint(scenario_id: Any) -> dict[str, Any]` | `dict[str, Any]` | `MakeApiError`, `ValueError` | Reads one scenario's blueprint; the scenario ID must be numeric. |
| 7 | `validate_make_zone` | `validate_make_zone(zone: str) -> str` | `str` | `ValueError` | Accepts only an HTTPS host ending in `.make.com` (SSRF guard). |

Credential loaders (`get_zapier_token`, `get_make_credentials`) and the model classes in `shared/models/dependency.py` are supporting code, not part of the public interface.

Deviation from the TS-10 draft: all three tools take `proposal_id` (for the US-5 gate and to link the scan to the proposal) and `build_dependency_graph` also takes `source_app`, since the graph needs a named root. See `docs/specs/US-10_spec.md` for the Zapier/Make endpoint and auth corrections.

### Public Interface Count Gate
- Count: 7 methods
- Limit: ≤ 7 methods
- Status: **PASSED**
