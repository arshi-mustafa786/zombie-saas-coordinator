```yaml
---
title: "Zombie SaaS Consolidator: Autonomous Multi-Agent Migration Platform"
product: "SDLC Sentinel - Zombie SaaS Consolidator"
version: "1.0.0"
date: "2025-01-15"
author: "Grill-Me Agent (Product Requirements)"
status: "Ready for Development"
target_event: "Google AI Builder Cup 2026 JAPAC"
primary_platforms: "Trello (Source) → Asana (Target)"
demo_duration: "3 minutes"
---

# Zombie SaaS Consolidator: Product Requirements Document

## Executive Summary

The **Zombie SaaS Consolidator** is an autonomous multi-agent orchestration platform that identifies, validates, and safely migrates data from redundant or unused SaaS applications to approved enterprise standards. Rather than relying on manual IT workflows or simple alerting dashboards, the system autonomously detects overlapping licenses, proposes consolidations, validates semantic compatibility, executes migrations with zero data loss, and maintains immutable compliance records throughout the entire lifecycle.

The Hackathon Prototype targets migration from **Trello (lightweight shadow IT tool)** to **Asana (structured enterprise standard)**, deliberately choosing this pairing to demonstrate:
- Semantic contract validation to catch behavioral mismatches before they cause silent data corruption
- Agentic triage to filter false positives and reduce operational friction
- Enterprise-grade governance with multi-signature approval gates and immutable audit trails
- Real-time escalation and human-in-the-loop (HITL) execution gates at critical decision points

**Business Impact:** Eliminates redundant SaaS licensing costs, closes security gaps from unmanaged credentials, and proves that AI agents can orchestrate complex enterprise infrastructure beyond text generation.

---

## AI Builder Cup: Submission Description

**Zombie SaaS Consolidator** is an autonomous multi-agent orchestration platform that identifies redundant SaaS applications and safely migrates data to enterprise standards. 
- **Cloud Run:** Hosts our event-driven Python microservices, exposing scalable webhook endpoints to ingest telemetry and expense reports.
- **Gemini (via Vertex AI):** Powers our Architect and Auditor agents, performing complex semantic reasoning to validate if behavioral contracts (e.g., Trello automations) can be safely migrated to target platforms (e.g., Asana).
- **Firestore:** Serves as the dynamic state store for our multi-agent LangGraph workflows, persisting unstructured behavioral contracts and schema diffs.
- **Firebase:** Provides Firebase Authentication for secure Human-in-the-Loop (HITL) approval gates and Firebase Hosting to serve the CISO compliance dashboard.

---

## Problem Statement

### Current State

1. **Zombie SaaS Prevalence:** Organizations accumulate unused, forgotten, or duplicate software subscriptions that silently drain budgets and create security vulnerabilities. Industry data shows >50% of SaaS licenses remain unused.

2. **Shadow IT & License Sprawl:** Teams organically adopt lightweight tools (e.g., Trello) that duplicate capabilities already purchased at the enterprise level (e.g., Asana), creating redundancy and data fragmentation.

3. **Manual Consolidation Friction:** IT departments hesitate to cancel or consolidate subscriptions because:
   - Fear of breaking interconnected workflows and automation rules
   - Risk of losing fragmented data across disconnected systems
   - Uncertainty about which users/teams are actually dependent on the old system
   - Compliance liability if historical audit trails are not preserved

4. **Unmanaged Access Risk:** Former employees often retain credentials to forgotten systems months after departure, creating persistent security exposure.

5. **Lack of Semantic Validation:** Existing migration tools compare database schemas structurally but miss behavioral logic mismatches (e.g., a Trello automation rule that archives cards has no equivalent in Asana's task model), leading to silent data corruption post-migration.

### Why It Matters

Every month of delay costs the organization:
- Direct: Duplicate subscription fees (often $10K–$100K+ annually per redundant tool)
- Indirect: Security liability from unrevoked credentials, compliance risk from poor audit trails, operational overhead from fragmented workflows

---

## User Personas

### 1. **Chief Information Security Officer (CISO)**
- **Goals:** Eliminate unmanaged credentials, enforce zero-trust access controls, maintain immutable compliance records
- **Pain Points:** Cannot track who has access to zombie systems; cannot audit decommissioning decisions; fears silent data loss during migrations
- **Interaction with Product:** Reviews high-risk consolidation proposals; approves final disposal decisions; queries audit logs during compliance investigations

### 2. **IT Operations Manager (IT Ops)**
- **Goals:** Reduce manual toil; consolidate redundant tools; maintain uptime; avoid breaking active workflows
- **Pain Points:** Manually identifies zombie systems; painstakingly maps data before migration; worries about breaking Zapier/Make automations; lacks confidence that migration is complete and safe
- **Interaction with Product:** Receives anomaly alerts; clicks [Approve Full Consolidation]; monitors migration progress; escalates blockers to CISO

### 3. **Compliance Officer / Records Manager**
- **Goals:** Ensure data is classified correctly; maintain audit trails; prove lawful disposal; survive regulatory inspections
- **Pain Points:** Cannot prove data was migrated correctly; unclear who authorized disposal; no cryptographic evidence of compliance; compliance clock resets are unpredictable
- **Interaction with Product:** Reviews quarantined items before disposal window expires; approves multi-signature disposal gates; retrieves Certificates of Destruction during audits

### 4. **Finance / Procurement Lead**
- **Goals:** Reduce SaaS spend; identify cost-saving opportunities; automate subscription management
- **Pain Points:** Struggles to map license usage to actual business value; unaware of duplicate tools; cannot easily justify cancellations to leadership
- **Interaction with Product:** Receives estimated savings reports; approves consolidation based on ROI; tracks post-migration cost reductions

### 5. **Enterprise Architect / Technical Lead**
- **Goals:** Consolidate toolchains; reduce technical debt; improve system interoperability
- **Pain Points:** Unaware of all the tools teams are using; unclear on data dependencies; cannot predict impact of consolidation on downstream workflows
- **Interaction with Product:** Reviews semantic contract validation reports; understands which automations cannot be migrated; informs decision to quarantine high-risk items

---

## Functional Requirements

### FR1: Autonomous Anomaly Detection & Trigger Engine

#### FR1.1: Scheduled Identity & Access Telemetry (Pull Trigger)
**User Story:**
> As an IT Operations Manager, I want the system to automatically scan IdP logs every 24–72 hours and flag applications with zero activity or redundant capabilities, so I don't have to manually hunt for zombie systems.

**Acceptance Criteria:**
- System connects to identity providers (Okta, Google Workspace, Azure AD) using **Firebase Authentication** (via OAuth 2.0 or SAML federation)
- Cron-based Auditor Agent executes on a configurable schedule (default: every 48 hours)
- Flags application when ≥60% of assigned seats show zero SAML/OIDC logins over 60+ days
- Detects capability redundancy by matching application tags/categories (e.g., `kanban_board`) against enterprise standards
- Generates structured JSON payload with application name, seat count, inactivity duration, and redundancy confidence score
- Logs all detection logic to Cloud Audit Logs for forensic reconstruction

#### FR1.2: Expense & Webhook Ingestion (Push Trigger)
**User Story:**
> As a Finance Lead, I want the system to receive webhook notifications from Brex/Ramp/Expensify when a new software subscription appears on a corporate card, so we can catch shadow IT purchases in real-time.

**Acceptance Criteria:**
- System exposes a secure webhook endpoint (`POST /webhooks/expense-notification`) authenticated via HMAC-SHA256
- Accepts expense payloads containing: merchant name, amount, billing frequency, contract renewal date
- Identifies unapproved recurring subscriptions by comparing against a whitelist of approved SaaS tools
- Detects auto-renewal windows (e.g., "renewal in 60 days") and flags for cancellation opportunity
- Routes high-value subscriptions (>$500/month) directly to Finance Lead for immediate review
- All webhook events are immutably logged in Cloud Audit Logs

---

### FR2: Consolidation Proposal & Human-in-the-Loop Approval Gate

#### FR2.1: Auditor Agent – Consolidation Proposal Generation
**User Story:**
> As an IT Ops Manager, I want the system to create a detailed, human-readable consolidation proposal before any migration begins, so I understand what's at risk and can make an informed decision.

**Acceptance Criteria:**
- Auditor Agent generates structured JSON payload containing:
  - Redundant application identifier (e.g., "Trello: 12 seats")
  - Target enterprise standard (e.g., "Asana")
  - Estimated annual savings calculation (seats × cost per seat × months remaining)
  - Risk score (0–100) based on: active user count, connected integrations, data age, compliance sensitivity
  - Summary of detected dependencies (Zapier webhooks, custom fields, automation rules)
  - Recommendation: Proceed to Full Consolidation, Proceed with Manual Review, or Ignore/Whitelist
- Payload is human-readable and includes links to source data (IdP logs, expense reports)
- Proposal is timestamped and signed with system identity for audit trail

#### FR2.2: Interactive Approval Card
**User Story:**
> As an IT Ops Manager, I want to receive an interactive notification (Slack, Teams, or email) that lets me review the consolidation proposal and take action without leaving my communication tool.

**Acceptance Criteria:**
- System sends formatted message card to Slack workspace (or Microsoft Teams channel) designated by IT Ops
- Card displays:
  - Plaintext summary: "[ALERT] Redundant Tool Detected: Trello (12 seats, 0 logins in 45 days)"
  - Target platform: "Asana"
  - Estimated savings: "$1,440/year"
  - Dependencies found: "1 Zapier webhook, 4 active boards"
- Three interactive buttons:
  1. `[Simulate Migration]` – Dry-run the migration in a sandbox environment
  2. `[Approve Full Consolidation]` – Authorize the system to proceed with validation and execution
  3. `[Ignore/Whitelist]` – Exclude this tool from future consolidation recommendations
- User clicks [Approve Full Consolidation] → System records approver identity, timestamp, and SSO context
- User clicks [Simulate Migration] → Triggers a dry-run that executes all validation steps without making permanent changes; results are appended to the interactive card
- All user interactions are logged to Cloud Audit Logs with full context (user ID, SSO session, IP address, action taken)

#### FR2.3: HITL Execution Gate
**User Story:**
> As a CISO, I want a mandatory human approval gate before the system executes any irreversible actions (data migration, account revocation, subscription cancellation), so we maintain accountability and can halt the process if new information emerges.

**Acceptance Criteria:**
- Clicking [Approve Full Consolidation] serves as the formal authorization trigger
- System does not proceed beyond the Validation Phase without explicit human approval
- Approval is tied to authenticated SSO identity verified via **Firebase Authentication** (not a generic API token)
- Approval expires after 7 days; if migration is not completed within this window, the approval must be re-issued
- System can be halted at any stage if IT Ops or CISO revokes approval
- All halts are logged with reason and authorizing identity

---

### FR3: Semantic Contract Validation Phase

#### FR3.1: Behavioral Contract Extraction
**User Story:**
> As a Technical Lead, I want the system to automatically extract automation rules and behavioral logic from the source system (Trello) so we can verify that the target system (Asana) can enforce the same rules after migration.

**Acceptance Criteria:**
- Architect Agent connects to Trello API (`GET /1/boards/{id}/cards`, `GET /1/boards/{id}/lists`) and parses all board configurations
- Extracts automation and power-up rules in structured format:
  - **Trello Example:** "IF card.status == 'Done' THEN action == Archive" 
  - **Trello Example:** "IF card.label == 'Urgent' THEN notify(@channel)"
  - Custom fields, due dates, card labels, and checklists
- For each automation, the agent records:
  - Trigger condition (e.g., status change, label addition)
  - Action to execute (e.g., archive, move, notify)
  - Scope (all cards in board, or specific list)
- Exports behavioral contract as a JSON specification document for audit trail
- Logs all API calls and extracted rules to Cloud Audit Logs

#### FR3.2: Schema Diffing & Structural Validation
**User Story:**
> As a Technical Lead, I want the system to compare the data schemas of Trello and Asana side-by-side, so we identify field-level mismatches before migration begins.

**Acceptance Criteria:**
- Architect Agent reads Asana API documentation and extracts target schema:
  - Asana task model: `id`, `name`, `description`, `assignee`, `due_date`, `custom_fields`, `sections`, `projects`
  - Asana project model: `id`, `name`, `owner`, `sections`, `teams`
  - Asana section model: `id`, `name`, `project`
- Compares Trello schema to Asana schema:
  - Trello `card` → Asana `task` (straightforward mapping)
  - Trello `list` → Asana `section` (straightforward mapping)
  - Trello `board` → Asana `project` (straightforward mapping)
  - Trello custom field (e.g., `custom_field_type: "text"`) → Asana custom field (if type-compatible; flag if not)
  - Trello `label` → Asana custom field or `tags` (requires mapping decision)
- Generates a schema diff report identifying:
  - **Green** (safe mapping): Fields with direct type equivalents
  - **Yellow** (lossy mapping): Fields that require transformation (e.g., label → custom field)
  - **Red** (unmappable): Fields with no Asana equivalent (e.g., Trello power-up data)
- Reports are included in the Consolidation Proposal

#### FR3.3: State-Transition Simulation (Semantic Validation)
**User Story:**
> As a Technical Lead, I want the system to simulate what happens when a Trello card transitions to a "Done" state in Asana, so we verify that all downstream automations still trigger correctly.

**Acceptance Criteria:**
- Architect Agent takes each extracted behavioral contract and simulates its execution in Asana
- **Simulation Logic:**
  - For "IF card.status == 'Done' THEN Archive," the system:
    1. Maps Trello `Done` status → Asana `Completed` task status
    2. Queries Asana API to determine if a task in `Completed` status automatically triggers archival
    3. Result: Asana does NOT auto-archive completed tasks (mismatch detected)
  - For "IF card.label == 'Urgent' THEN notify(@channel)," the system:
    1. Maps Trello `label` → Asana custom field or tag
    2. Checks if Asana can send notifications when a custom field changes
    3. Result: May require a Zapier/Make webhook to replicate behavior
- Simulation results are classified as:
  - **Behaviorally Equivalent:** The target platform has a native feature that satisfies the contract
  - **Degraded but Acceptable:** The target platform lacks a native feature, but a custom webhook can replicate it
  - **Incompatible:** No reasonable mapping exists; record must be quarantined
- All simulation results are logged to the validation report

#### FR3.4: Semantic Mismatch Detection & Hypothesis Formation
**User Story:**
> As a Technical Lead, I want the system to clearly identify when a behavioral contract cannot be satisfied in the target platform, and propose a concrete remediation, so I understand what will break during migration.

**Acceptance Criteria:**
- If simulation detects a mismatch (e.g., Asana lacks auto-archive for completed tasks), Architect Agent generates a **Semantic Mismatch Report** containing:
  - Original contract: "IF status == Done THEN Archive"
  - Target capability: "Asana tasks in Completed status do not auto-archive"
  - Remediation hypothesis: "Create a Zapier/Make webhook that listens for task completion events and moves the task to an Archive section"
  - Risk: "Medium – Requires custom automation and introduces a third-party dependency"
- Report includes code skeleton for the proposed webhook (e.g., Zapier trigger + action)
- Mismatch is flagged as a **High-Risk** item in the Consolidation Proposal
- IT Ops is notified that manual review or custom development may be required

---

### FR4: Integrator Agent – Workflow Dependency Scanning & Rewriting

#### FR4.1: Automation Hub Scanning
**User Story:**
> As an IT Ops Manager, I want the system to automatically find all Zapier and Make workflows that depend on the Trello integration, so we know which automations will break if we decommission Trello.

**Acceptance Criteria:**
- Integrator Agent connects to Zapier API (OAuth 2.0) and Make API (OAuth 2.0)
- Queries for all active zaps/workflows that contain Trello as a trigger or action:
  - `GET /v1/zaps` (Zapier) – retrieve all zaps
  - `GET /automations` (Make) – retrieve all scenarios
- For each Zapier/Make workflow that references