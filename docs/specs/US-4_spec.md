---
story_id: US-4
module_name: notifications_and_callbacks
layers: [api, service, ui]
ancestor_stories: [US-3]
parent_techspec: docs/techspecs/TS-4.md
---

# US-4: Interactive Approval Card Specification

## Capabilities
- Dispatch interactive Slack/Teams Block Kit message cards summarizing consolidation proposals.
- Display application details, target platform, annual savings, risk score, and dependencies.
- Provide three interactive action buttons: [Simulate Migration], [Approve Full Consolidation], and [Ignore/Whitelist].
- Handle callback webhook events triggered when buttons are clicked in Slack/Teams.
- Authenticate incoming callback events against a shared verification secret or signature to prevent spoofing.
- Prevent SSRF attacks by strictly validating webhook URLs against approved domains (e.g., `hooks.slack.com`).
- Record approver identity and update proposal status in Firestore.
- Emit structured Cloud Audit Log events for every interaction.
- Provide dummy proposal data fallback when US-3 proposals are not yet populated in Firestore.

## Acceptance Criteria
- AC-4.1: Auditor Agent sends formatted message card to designated Slack/Teams channel.
- AC-4.2: Card displays summary, target platform, estimated savings, and dependencies found.
- AC-4.3: Provides three interactive buttons: [Simulate Migration], [Approve Full Consolidation], [Ignore/Whitelist].
- AC-4.4: [Simulate Migration] triggers dry-run simulation mode without permanent changes.
- AC-4.5: [Approve Full Consolidation] records approver identity, timestamp, and SSO context in Firestore.
- AC-4.6: [Ignore/Whitelist] marks proposal as whitelisted/ignored.
- AC-4.7: All user interactions are logged to Cloud Audit Logs with full context.

## Module Interface Contract (MIC)
Public interfaces exposed (≤ 7 public methods):
1. `send_approval_card(proposal_id: str, channel: str) -> dict[str, Any]`
   - Tool on Auditor Agent. Dispatches approval card to Slack/Teams channel.
2. `build_slack_approval_card(proposal: ConsolidationProposal) -> dict[str, Any]`
   - Constructs standard Slack Block Kit interactive message payload.
3. `dispatch_slack_message(channel_or_webhook: str, payload: dict[str, Any]) -> dict[str, Any]`
   - Validates URL for SSRF protection and executes HTTP POST to Slack.
4. `POST /api/v1/notifications/send` (`send_notification_endpoint`)
   - Cloud Run API endpoint to trigger card dispatch.
5. `POST /api/v1/callbacks/approval` (`handle_approval_callback`)
   - Cloud Run API endpoint to handle interactive button callback webhooks.

## Data Contracts
- `ConsolidationProposal` (in `zombie_saas_coordinator/shared/models/proposal.py`)
  - `proposal_id`: str
  - `app_id`: str
  - `app_name`: str
  - `target_platform`: str (default: "Asana")
  - `annual_savings`: float
  - `risk_score`: int (0-100)
  - `recommendation`: str
  - `detected_dependencies`: list[str]
  - `status`: str (PENDING, APPROVED, SIMULATING, WHITELISTED, EXPIRED)
  - `created_at`: datetime
  - `expires_at`: datetime
- `ApprovalCallbackPayload` (in `zombie_saas_coordinator/api/callbacks.py`)
  - `token`: str
  - `action`: Literal["simulate_migration", "approve_consolidation", "ignore_whitelist"]
  - `proposal_id`: str
  - `user_id`: str
  - `user_email`: str | None

## Out of Scope
- Automatic migration execution (reserved for US-11).
- Multi-signature cryptographic disposal authorizations (reserved for US-12).
- Native MS Teams Adaptive Card binary protocol (Slack Block Kit is primary, Teams incoming webhook JSON format supported).
