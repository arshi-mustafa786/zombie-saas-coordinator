# Zombie SaaS Consolidator - Architecture Document

## 1. System Overview
The Zombie SaaS Consolidator is an autonomous, event-driven **multi-agent orchestration platform** built on the **Google Agent Development Kit (ADK)**. It detects redundant SaaS tools and orchestrates migrations using a hierarchy of specialized AI agents coordinated by a root orchestrator.

## 2. Technology Stack (Google AI Builder Cup 2026)

### 2.1 Core AI & Agent Orchestration
*   **Language:** Python 3.11+
*   **Orchestration Framework:** **Google Agent Development Kit (ADK)** (`google-adk`) — Google's open-source framework for multi-agent systems
*   **LLM Provider:** Google Vertex AI
*   **Foundation Models (Gemini):**
    *   **Gemini Pro:** Complex reasoning — schema diffing, semantic contract extraction, mismatch hypothesis generation, code skeleton generation
    *   **Gemini Flash:** Fast operations — telemetry classification, triage routing, webhook parsing
*   **Agent Types Used:**
    *   `Agent` (LLM Agent) — Auditor, Architect, Integrator agents with tools
    *   `SequentialAgent` — Pipeline execution for the Architect validation workflow (US-6→US-7→US-8→US-9)
    *   `ParallelAgent` — Fan-out execution for Architect + Integrator after HITL gate (US-6 ∥ US-10)
*   **Protocols:**
    *   **Model Context Protocol (MCP)** — Tool definitions follow MCP-compatible schemas
    *   **Agent2Agent (A2A)** — Inter-agent communication via ADK sub_agents hierarchy

### 2.2 Compute & Execution
*   **Workload Hosting (Cloud Run):** Google Cloud Run hosts the ADK agent runtime and API endpoints. Deployment via `adk deploy cloud_run`.
*   **Event Scheduling:** Google Cloud Scheduler (Cron-based triggers for the Auditor Agent).
*   **Asynchronous Messaging:** Google Cloud Pub/Sub (Event decoupling for webhooks and agent handoffs).

### 2.3 Data Persistence (DB Layer)
*   **Relational Storage:** Google Cloud SQL (PostgreSQL). Stores structured data: approval records, ROI metrics, billing history.
*   **Document Storage (Firebase Firestore):** The core NoSQL state engine. Stores behavioral contracts, schema diff reports, simulation results, dependency graphs, and **ADK session state** via `FirestoreSessionService`.

### 2.4 Security, Governance & UI
*   **Frontend & UI:** **Firebase Hosting** serves the CISO Compliance Dashboard.
*   **Identity & Access Management:** **Firebase Authentication** handles SSO for HITL approval gates.
*   **Secret Management:** Google Secret Manager (API keys, OAuth tokens for Trello, Asana, Zapier, Make).
*   **Compliance & Auditing:** Google Cloud Audit Logs (Immutable logs of all AI decisions, API calls, and HITL actions).

## 3. Multi-Agent Architecture (Google ADK)

### 3.1 Agent Hierarchy

```
zombie_saas_coordinator (Root Orchestrator)
├── auditor_agent (Gemini Flash)
│   ├── Tools: scan_idp_logs, calculate_redundancy
│   ├── Tools: validate_webhook, flag_subscription
│   ├── Tools: generate_proposal, calculate_roi
│   └── Tools: send_approval_card
├── architect_agent (Gemini Pro)  [SequentialAgent pipeline]
│   ├── Tools: extract_trello_rules, parse_automation_rule
│   ├── Tools: diff_schemas, classify_mapping
│   ├── Tools: simulate_transition
│   └── Tools: generate_remediation
└── integrator_agent (Gemini Flash)
    └── Tools: scan_zapier, scan_make, build_dependency_graph
```

### 3.2 Root Orchestrator Definition

```python
from google.adk.agents import Agent

root_agent = Agent(
    name="zombie_saas_coordinator",
    model="gemini-2.0-pro",
    description="Root orchestrator for the Zombie SaaS Consolidator platform",
    instruction="""You are the Zombie SaaS Coordinator. You orchestrate three 
    specialized agents to detect, validate, and plan migrations for redundant 
    SaaS applications.
    
    Workflow:
    1. Delegate to auditor_agent for detection and proposal generation
    2. Wait for human approval (HITL gate) before proceeding
    3. After approval, delegate SIMULTANEOUSLY to:
       - architect_agent for semantic validation
       - integrator_agent for dependency scanning
    4. Aggregate results into a final migration report
    
    CRITICAL: Never proceed past the HITL gate without explicit human approval.""",
    sub_agents=[auditor_agent, architect_agent, integrator_agent],
)
```

### 3.3 ADK Project Structure

```
zombie_saas_coordinator/
├── __init__.py                     # Exports root_agent for ADK CLI
├── agent.py                        # Root orchestrator definition
├── agents/
│   ├── auditor/
│   │   ├── __init__.py
│   │   ├── agent.py                # auditor_agent definition
│   │   ├── tools.py                # All Auditor tools
│   │   └── prompt.py               # System instructions
│   ├── architect/
│   │   ├── __init__.py
│   │   ├── agent.py                # architect_agent definition
│   │   ├── tools.py                # All Architect tools
│   │   └── prompt.py               # System instructions
│   └── integrator/
│       ├── __init__.py
│       ├── agent.py                # integrator_agent definition
│       ├── tools.py                # All Integrator tools
│       └── prompt.py               # System instructions
├── api/
│   ├── callbacks.py                # Slack/Teams callback handler
│   └── approvals.py                # HITL authorization endpoint
├── shared/
│   ├── db/
│   │   ├── firestore_client.py     # Firestore access layer
│   │   └── cloudsql_client.py      # Cloud SQL access layer
│   ├── models/
│   │   ├── telemetry.py
│   │   ├── expense.py
│   │   ├── proposal.py
│   │   └── approval.py
│   ├── auth/
│   │   ├── firebase_auth.py        # Firebase Auth utilities
│   │   └── hmac_validator.py       # Webhook HMAC validation
│   └── integrations/
│       ├── trello.py               # Trello API client
│       ├── asana.py                # Asana API client
│       ├── zapier.py               # Zapier API client
│       ├── make.py                 # Make API client
│       └── slack.py                # Slack Block Kit client
├── tests/
│   ├── test_US1_scanner.py
│   ├── test_US2_expense.py
│   ├── test_US3_proposal.py
│   ├── test_US4_notifications.py
│   ├── test_US5_approvals.py
│   ├── test_US6_extractor.py
│   ├── test_US7_schema.py
│   ├── test_US8_simulator.py
│   ├── test_US9_hypothesis.py
│   └── test_US10_integrator.py
├── Dockerfile
└── pyproject.toml
```

## 4. Execution Flow

1. **Trigger:** Cloud Scheduler or expense webhook → Cloud Run → Auditor Agent
2. **Detection:** Auditor Agent scans IdP logs and expense data, generates consolidation proposal
3. **Notification:** Auditor Agent sends interactive approval card to Slack/Teams
4. **HITL Gate:** Human approves via Firebase Auth SSO → approval stored in Cloud SQL
5. **Parallel Validation:** Root Orchestrator simultaneously delegates to:
   - **Architect Agent:** Extracts contracts → Diffs schemas → Simulates transitions → Generates remediations
   - **Integrator Agent:** Scans Zapier/Make for dependency graphs
6. **Aggregation:** Root Orchestrator compiles final migration report in Firestore

## 5. Deployment

```bash
# Local development
adk web zombie_saas_coordinator

# Deploy to Cloud Run
adk deploy cloud_run \
  --project=zombie-saas-coordinator \
  --region=asia-south1 \
  --service-name=zombie-coordinator
```
