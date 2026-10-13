---
story_id: US-10
module_name: automation_hub_scanning
layers: [service, api, db]
ancestor_stories: [US-5]
parent_techspec: docs/techspecs/TS-10.md
---

# US-10: Automation Hub Scanning Specification

## Capabilities
- After a human approves `PERMISSION_TO_INVESTIGATE` (US-5), the Integrator Agent reads the organisation's Zapier and Make accounts (read-only) to find every workflow that depends on the app being decommissioned.
- **Zapier:** lists zaps through `GET /v2/zaps` with `expand=steps.action`, paginated with `limit`/`offset`. Without the expansion a step's app is an opaque ID and the source app cannot be matched.
- **Make:** lists scenarios through `GET /api/v2/scenarios?teamId=...`, then fetches each scenario's blueprint (`GET /api/v2/scenarios/{id}/blueprint`), because the list carries no module details. Modules nested inside router branches are included, in flow order.
- For each matching workflow it records the name, trigger, actions, where the source app appears, and the downstream apps the workflow writes to.
- Compiles a dependency graph `Source App -> Automation Hub -> downstream apps` and stores it as an immutable document in Firestore `dependency_graphs` (`create`, never overwrite).
- Writes every hub API call (hub, method, path, status, duration - no credentials) and the dependency summary to Cloud Audit Logs.

## Acceptance Criteria
- AC-10.1: Integrator Agent connects to the Zapier and Make APIs with operator-supplied credentials.
- AC-10.2: Queries all workflows containing the target app as a trigger or an action, with pagination.
- AC-10.3: For each workflow, records name, trigger, actions and downstream dependencies.
- AC-10.4: Identifies critical workflows (scheduled syncs, customer-facing downstream apps).
- AC-10.5: Generates the dependency graph and stores it in Firestore.
- AC-10.6: Flags workflows that break if the app is decommissioned.
- AC-10.7: All API calls and dependencies logged to Cloud Audit Logs.
- AC-10.8 (from US-5): Both scans are blocked unless `PERMISSION_TO_INVESTIGATE` is approved, active and unrevoked.

## Facts vs heuristics
- `breaks_if_decommissioned` is a **fact**: the workflow has a step on the source app, so decommissioning stops that step.
- `critical` is a **heuristic** and always ships with `criticality_reasons` (scheduled trigger, customer-facing downstream app, source app is the trigger). It must never be presented as certain, and a workflow with no reasons is simply not flagged - it still breaks.
- **Disabled workflows** are reported with `enabled: false` and are never marked critical, because they are not running today. They are still listed: re-enabling one after the migration would break it. TS-10 says "all active workflows"; reporting the paused ones too, clearly flagged, is a deliberate deviation so a latent dependency is not hidden.

## Deviations from TS-10
- `scan_zapier` / `scan_make` take `proposal_id` as well as `app_name` (needed for the US-5 gate and to link the scan to the proposal). `build_dependency_graph` takes `proposal_id` and `source_app` alongside `workflows`, so it can store the graph and name the graph's root.
- TS-10 describes Make as OAuth 2.0 at `GET /automations`. Make actually authenticates with `Authorization: Token <token>` against a zone-specific host (`{zone}.make.com/api/v2`) and the endpoint is `/scenarios`.
- TS-10 lists `GET /v1/zaps`; this uses the current `https://api.zapier.com/v2/zaps`.

## Integration Points
- Ancestor US-5: `check_approval_status(proposal_id, "PERMISSION_TO_INVESTIGATE")` from `shared/approvals/approvals.py`. If the check raises, `_investigation_gate` fails closed (`GATE_ERROR`).
- Runs independently of the Architect pipeline (US-6 to US-9); the root orchestrator delegates to both after the gate passes.
- Terminal node: no story reads `dependency_graphs` yet. US-3 proposals currently mark automation dependencies as unknown ("not yet scanned (US-10)"); wiring this scan into the proposal is follow-up work.

## Data Contracts
- `WorkflowStep`: kind (`trigger` | `action`), app, app_key, title
- `DependentWorkflow`: workflow_id, hub (`zapier` | `make`), name, enabled, trigger, actions, source_app_steps, downstream_apps, breaks_if_decommissioned, critical, criticality_reasons, last_successful_run, url
- `DependencyGraph`: source_app, hubs, downstream_apps, edges `{from, via, to, workflow_id}`
- `DependencyScan` (Firestore document): scan_id, proposal_id, source_app, workflows, graph, breaking_count, critical_count, hubs_scanned, api_calls, warnings, scanned_at, scanned_by

## Security
- Zapier and Make tokens come from env (local) or Secret Manager (`zapier-access-token`, `make-api-token`) and are sent only in the `Authorization` header, never in URLs, logs, results or Firestore.
- The Make zone host is operator-configured, so it is validated against `.make.com` over HTTPS before any request (SSRF guard); scenario IDs must be numeric before they reach a URL path.
- Workflow and app names come from third-party accounts: control characters are stripped and every text field is capped at 200 characters before it is stored. Readable punctuation is preserved, so any tool that later puts these names in an LLM prompt must call `prompt_safe` itself.
- 401/403 fail fast with a message naming the missing scope; 429 and transient gateway errors are retried, honouring `Retry-After`.

## Known limitations
- Zapier's `zap:all` scope requires a public integration OAuth app; with only the default `zap` scope Zapier returns just the zaps using the caller's own integration, so the scan is incomplete. A scan that matches zaps with no app details warns about this.
- Make scans one team at a time (`MAKE_TEAM_ID`); an organisation with several teams needs one scan per team.
- Scans are capped at 1000 workflows per hub and report `truncated` when the cap is hit.
- Not tested against live Zapier/Make accounts; all tests use mocked HTTP transports.

## Out of Scope
- Rewriting or disabling workflows, and creating replacement automations (FR4.2 onwards).
- Feeding the discovered dependencies back into the US-3 consolidation proposal.
