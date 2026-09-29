# Zombie SaaS Consolidator - Architecture Document

## 1. System Overview
The Zombie SaaS Consolidator is an autonomous, event-driven multi-agent platform designed to detect redundant SaaS tools and orchestrate migrations. It implements a graph-based state machine executing across discrete agentic nodes.

## 2. Technology Stack (Google AI Builder Cup 2026)

### 2.1 Core AI & Agent Orchestration
*   **Language:** Python 3.11+
*   **Orchestration Framework:** LangGraph
*   **LLM Provider:** Google Vertex AI
*   **Foundation Models:**
    *   **Gemini Pro (e.g., 3.x Pro):** Used for complex reasoning, schema diffing, semantic contract extraction, and mismatch hypothesis generation.
    *   **Gemini Flash (e.g., 3.x Flash):** Used for fast, structured data extraction, classification, and triage routing.

### 2.2 Compute & Execution
*   **Workload Hosting:** Google Cloud Run (Serverless containers, scaling to zero).
*   **Event Scheduling:** Google Cloud Scheduler (Cron-based triggers for the Auditor Agent).
*   **Asynchronous Messaging:** Google Cloud Pub/Sub (Event decoupling for webhooks and agent handoffs).

### 2.3 Data Persistence (DB Layer)
*   **Relational Storage:** Google Cloud SQL (PostgreSQL). Stores active consolidation proposals, migration states, human approval records, and structured metric data.
*   **Document Storage:** Google Cloud Firestore (NoSQL). Stores unstructured behavioral contracts, third-party API payloads (Trello/Asana/Zapier), and schema diff reports.

### 2.4 Security & Governance
*   **Identity & Access Management (IAM):** Google Workspace Identity for SSO, gating HITL (Human-in-the-Loop) approvals.
*   **Secret Management:** Google Secret Manager (API keys, OAuth tokens for integrations).
*   **Compliance & Auditing:** Google Cloud Audit Logs (Immutable logs of all AI decisions, API calls, and HITL actions).

## 3. High-Level Agent Architecture
*   **Auditor Agent:** Triggered by Cloud Scheduler or Webhooks. Analyzes IdP logs and expense events to generate Consolidation Proposals.
*   **Architect Agent:** Executes Semantic Contract Validation. Extracts Trello behavioral rules and validates them against the Asana schema using Vertex AI.
*   **Integrator Agent:** Scans Zapier and Make for dependencies. Generates risk graphs for downstream workflow breakages.

## 4. Execution Flow
1. **Trigger:** Event arrives via Pub/Sub (from Scheduler or Webhook).
2. **Analysis:** Auditor Agent instances spin up on Cloud Run, process data, and store a proposal in Cloud SQL.
3. **Approval:** A notification is dispatched. A human approves via SSO, updating the database record.
4. **Validation:** Architect and Integrator agents execute LangGraph DAGs to simulate the migration and map behavioral contracts.
5. **Report Generation:** Final validation report is generated and stored in Firestore for audit.
