---
story_id: US-1
module_name: idp_scanner
layers: [db, service, api]
ancestor_stories: []
---

# Spec: US-1 Scheduled Identity & Access Telemetry

## Capabilities
- Connects to identity providers (Okta, Google Workspace, Azure AD) using Firebase Authentication federation (OAuth 2.0 / SAML).
- Scans SAML/OIDC access logs for SaaS application usage over a configurable time window (default 60 days).
- Flags applications where >= 60% of assigned seats have zero logins over 60+ days.
- Assesses capability redundancy by comparing application tags/features against enterprise standard systems using Gemini Flash.
- Calculates redundancy confidence scores (0-100) and rationale.
- Persists structured scan telemetry and application inventory to Firestore and Cloud SQL.
- Emits structured Cloud Audit Logs for forensic compliance.
- Exposes an authenticated Cloud Run job endpoint for Cloud Scheduler invocation (`POST /api/v1/jobs/scan-idp`).

## Acceptance Criteria
- AC-1.1: System connects to identity providers (Okta, Google Workspace, Azure AD) using Firebase Authentication (via OAuth 2.0 or SAML federation).
- AC-1.2: Cron-based Auditor Agent executes on a configurable schedule (default: every 48 hours) triggered by Cloud Scheduler -> Cloud Run.
- AC-1.3: Flags application when >= 60% of assigned seats show zero SAML/OIDC logins over 60+ days.
- AC-1.4: Detects capability redundancy using Gemini Flash for semantic tag matching.
- AC-1.5: Generates structured JSON payload stored in Firestore.
- AC-1.6: Logs all detection logic to Cloud Audit Logs for forensic reconstruction.

## Integration Points
- Root story: no ancestor dependencies.
- Downstream: US-3 (Consolidation Proposal Generation) reads flagged apps and telemetry from Firestore collection `idp_telemetry` and `application_inventory`.

## Data Contracts
- `AppTelemetry`: app_id, app_name, vendor, total_seats, active_seats, inactive_seats, inactive_ratio, last_login_date, tags, is_flagged_inactive
- `RedundancyAssessment`: app_name, enterprise_standard_match, redundancy_score, overlapping_capabilities, rationale
- `ScanResult`: scan_id, tenant_id, timestamp, total_apps_scanned, flagged_apps_count, apps: list[AppTelemetry], flagged: list[RedundancyAssessment]

## Out of Scope
- Direct credential modification or user offboarding in external IdPs (handled in later migration workflows).
- Real-time expense transaction analysis (handled in US-2).
