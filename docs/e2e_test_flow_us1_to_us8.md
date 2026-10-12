# 🧟 End-to-End Test Guide: User Story 1 to User Story 8

A complete step-by-step testing guide for end users to validate the **Zombie SaaS Consolidator** multi-agent pipeline directly from the **Google ADK Web UI**.

---

## 🎯 Test Pipeline Overview

```
[US-1: IdP Telemetry Scan]
        │
        ▼
[US-2 & US-3: Expense Analysis & Signed Proposal Generation]
        │
        ▼
[US-4: Interactive Slack Approval Notification]
        │
        ▼
[US-5: 3-Tier HITL Governance Gate (PERMISSION_TO_INVESTIGATE)]
        │
        ▼
[US-6: Behavioral Contract Extraction (Butler Grammar)]
        │
        ▼
[US-7: Schema Diffing & Field Mapping (Trello → Asana)]
        │
        ▼
[US-8: State-Transition Simulation (Gemini Semantic Validation)]
```

---

## 🛠️ Prerequisites & Setup

1. **Launch the ADK Web Server**:
   In your project directory terminal, start the ADK Web interface:
   ```powershell
   adk web adk_app
   ```
2. **Open the Web UI**:
   Navigate to **`http://127.0.0.1:8000`** in your browser.
3. **Select Agent**:
   In the agent dropdown (top-left), choose **`coordinator`** (Root Orchestrator).

---

## 💬 Step-by-Step Interactive Test Runbook

### Step 1 · US-1: Identity & Access Telemetry Scanner
* **Goal**: Detect underutilized applications from SAML/OIDC access logs (>60% inactive seats).
* **Copy-Paste Prompt**:
  ```text
  Scan identity provider telemetry for tenant "tenant-acme" over the last 60 days to detect zombie or underutilized SaaS applications.
  ```
* **Expected Agent Action**:
  * Root coordinator invokes `auditor_agent` $\rightarrow$ `scan_idp_logs`.
* **Expected Response**:
  * Identifies **Trello** as a candidate for consolidation with ~75–80% inactive seats (>60 days idle).

---

### Step 2 · US-2 & US-3: Expense Analysis & Signed Proposal Generation
* **Goal**: Correlate recurring spend with seat count, calculate ROI math, and generate a tamper-evident signed proposal.
* **Copy-Paste Prompt**:
  ```text
  Trello costs $540/month ($6,480/year) across 40 inactive seats and renews in 25 days. Generate a formal consolidation proposal to migrate Trello to Asana for tenant "tenant-acme".
  ```
* **Expected Agent Action**:
  * Invokes `generate_proposal` and `calculate_roi`.
  * Signs proposal cryptographically with HMAC-SHA256 (`PROPOSAL_SIGNING_SECRET`).
* **Expected Response**:
  * Outputs proposal summary:
    * **Proposal ID**: e.g., `prop_7674ec4f8c9a` *(save this ID for next steps)*
    * **Estimated Annual Savings**: ~$6,480.00 to $8,100.00 / year
    * **Risk Score**: ~25–28 / 100 (Low Risk)
    * **Status**: `PENDING`

---

### Step 3 · US-4: Interactive Slack Approval Notification
* **Goal**: Send a rich Block Kit notification to IT Ops with actionable decision buttons.
* **Copy-Paste Prompt**:
  ```text
  Send an interactive approval card for proposal "prop_7674ec4f8c9a" to Slack.
  ```
* **Expected Agent Action**:
  * Calls `send_approval_card(proposal_id="prop_7674ec4f8c9a")`.
  * Dispatches payload to the configured Slack incoming webhook.
* **Expected Response**:
  * Confirms card dispatch: status `sent = True` with `message_id`.
  * Renders interactive card in Slack with buttons: *[Simulate Migration]*, *[Approve Full Consolidation]*, *[Ignore/Whitelist]*.

---

### Step 4 · US-5: Human-in-the-Loop (HITL) Governance Gate
* **Goal**: Verify that no downstream migration or architecture deep-dive can begin without human sign-off (`PERMISSION_TO_INVESTIGATE`).
* **Copy-Paste Prompt**:
  ```text
  Check the approval status for proposal "prop_7674ec4f8c9a" for the PERMISSION_TO_INVESTIGATE gate.
  ```
* **Expected Agent Action**:
  * Calls `check_approval_status(proposal_id="prop_7674ec4f8c9a", required_gate="PERMISSION_TO_INVESTIGATE")`.
* **Expected Response**:
  * Returns `approved = True`, confirming authorization to delegate to the Architect Agent.

---

### Step 5 · US-6: Behavioral Contract Extraction & Normalization
* **Goal**: Parse Trello Butler automation rules into a deterministic canonical contract schema.
* **Copy-Paste Prompt**:
  ```text
  As the Architect Agent, parse this Trello Butler automation rule:
  'when a card is moved into list "Done", archive the card'
  ```
* **Expected Agent Action**:
  * Calls `parse_automation_rule`.
* **Expected Response**:
  * **Status**: `success`, **Parser**: `grammar`
  * **Trigger Event**: `card_moved_to_list` with condition `list = "Done"`
  * **Action**: `archive_card`

---

### Step 6 · US-7: Schema Diffing & Field Mapping
* **Goal**: Compute structural mapping between Trello (source) and Asana (target) data structures.
* **Copy-Paste Prompt**:
  ```text
  Perform a schema diff between:
  Trello Source Schema: {"card_title": "string", "list_name": "string", "labels": "list", "story_points": "integer"}
  Asana Target Schema: {"task_name": "string", "section_name": "string", "tags": "string", "story_points": "number"}
  ```
* **Expected Agent Action**:
  * Calls `diff_schemas`.
* **Expected Response**:
  * **Green (Direct Equivalents)**: `card_title` $\rightarrow$ `task_name`, `list_name` $\rightarrow$ `section_name`
  * **Yellow (Transforms Required)**: `labels` $\rightarrow$ `tags`, `story_points` (integer $\rightarrow$ number)
  * **Red (Unmappable)**: 0

---

### Step 7 · US-8: State-Transition Simulation in Asana Context
* **Goal**: Verify if Asana natively supports the automated transition and persist the result in Firestore.
* **Copy-Paste Prompt**:
  ```text
  Simulate the state transition for this contract using the schema diff to verify if Asana natively supports auto-archiving completed tasks.
  ```
* **Expected Agent Action**:
  * Calls `simulate_transition(contract=..., schema_diff=...)`.
  * Runs semantic reasoning via Gemini.
  * Writes record to Firestore collection `simulation_results`.
* **Expected Response**:
  * **Classification**: `Behaviorally Equivalent`
  * **Quarantine Required**: `False`
  * **Remediation Needed**: `False`
  * **Reasoning**: Explanation showing Asana natively supports completion triggers via its rules engine.

---

## 🔮 How to Add Future Tests (US-9, US-10)

When expanding tests in future releases:

### Adding User Story 9 (Remediation Hypotheses)
* **Goal**: Test automated remediation for *Incompatible* or *Degraded* automation rules.
* **Prompt Template**:
  ```text
  Generate a remediation hypothesis for rule 'when card due date is today, send SMS' that is marked Incompatible in Asana.
  ```

### Adding User Story 10 (Integrator Dependency Scanning)
* **Goal**: Test discovery of third-party integration pipelines (Zapier & Make).
* **Prompt Template**:
  ```text
  Scan Zapier and Make automation hubs for active workflows touching Trello, and build a dependency graph.
  ```
