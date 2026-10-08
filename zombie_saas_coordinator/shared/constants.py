"""Shared constants for all agents, APIs and models.

Values here are contracts between user stories (e.g. US-1 writes the
``scans`` collection that US-3 reads), so change them in one place only.
"""

from typing import Any

# ──────────────────────────────────────────────
# Firestore collections
# ──────────────────────────────────────────────

SCANS_COLLECTION = "scans"  # US-1 writes, US-3 reads
SAAS_WHITELIST_COLLECTION = "saas_whitelist"  # US-2 reads
EXPENSE_EVENTS_COLLECTION = "expense_events"  # US-2 writes, US-3 reads
PROPOSALS_COLLECTION = "consolidation_proposals"  # US-3 writes, US-4 reads/updates
BEHAVIORAL_CONTRACTS_COLLECTION = "behavioral_contracts"  # US-6 writes, US-7 reads

# ──────────────────────────────────────────────
# Cloud Logging audit log names
# ──────────────────────────────────────────────

IDP_TELEMETRY_AUDIT_LOG = "idp-telemetry-audit"
EXPENSE_WEBHOOK_AUDIT_LOG = "expense-webhook-audit"
PROPOSAL_AUDIT_LOG = "consolidation-proposal-audit"
CONTRACT_EXTRACTION_AUDIT_LOG = "behavioral-contract-audit"

# ──────────────────────────────────────────────
# US-1: IdP telemetry & redundancy
# ──────────────────────────────────────────────

DEFAULT_SCAN_WINDOW_DAYS = 60
# AC-1.3: flag an app when >= 60% of seats have no logins over 60+ days.
INACTIVITY_MIN_DAYS = 60
INACTIVITY_SEAT_RATIO = 0.60
# Minimum capability overlap (percent) to report an app as redundant.
REDUNDANCY_MIN_SCORE = 50

ENTERPRISE_STANDARDS: dict[str, dict[str, Any]] = {
    "Project Management": {
        "standard_app": "Jira Software (Enterprise Standard)",
        "capabilities": {
            "kanban",
            "scrum",
            "issue-tracking",
            "task-tracking",
            "collaboration",
            "enterprise-agile",
        },
    },
    "Team Communication": {
        "standard_app": "Microsoft Teams (Enterprise Standard)",
        "capabilities": {"chat", "video-calls", "screen-sharing", "channels", "team-messaging"},
    },
    "Cloud Storage": {
        "standard_app": "Google Drive (Enterprise Standard)",
        "capabilities": {"file-storage", "document-sharing", "cloud-sync", "permissions"},
    },
    "Document Collaboration": {
        "standard_app": "Confluence (Enterprise Standard)",
        "capabilities": {"wiki", "documentation", "knowledge-base", "specs"},
    },
}

# ──────────────────────────────────────────────
# US-2: Expense webhooks
# ──────────────────────────────────────────────

# Monthly-equivalent spend (USD) above which a subscription goes straight to Finance.
HIGH_VALUE_MONTHLY_THRESHOLD = 500
# Default for the EXPENSE_RENEWAL_WINDOW_DAYS environment variable.
DEFAULT_RENEWAL_WINDOW_DAYS = 30

# ──────────────────────────────────────────────
# US-3: Consolidation proposals
# ──────────────────────────────────────────────

PROPOSAL_TTL_DAYS = 7  # FR2.3: approval expires after 7 days
MAX_SUMMARY_LENGTH = 1000
MAX_RATIONALE_LENGTH = 2000
MAX_PROMPT_FIELD_LENGTH = 200
# Money is stored as float (Firestore has no decimal type); compare to the cent.
MONEY_TOLERANCE = 0.01

# Risk scoring
BASE_RISK_SCORE = 10
HIGH_ACTIVE_RATIO = 0.50
HIGH_ACTIVE_RISK = 40
MODERATE_ACTIVE_RATIO = 0.20
MODERATE_ACTIVE_RISK = 20
RISK_PER_DEPENDENCY = 15
MAX_DEPENDENCY_RISK = 30
HIGH_COMPLIANCE_RISK = 20
MEDIUM_COMPLIANCE_RISK = 10
DATA_AGE_OLD_DAYS = 365
DATA_AGE_OLD_RISK = 10
DATA_AGE_AGING_DAYS = 180
DATA_AGE_AGING_RISK = 5

# Recommendation thresholds
MANUAL_REVIEW_RISK_THRESHOLD = 65
MIN_ANNUAL_SAVINGS = 500

# Workflow fields US-4 callbacks update after a proposal is signed.
UNSIGNED_PROPOSAL_FIELDS = frozenset(
    {"signature", "status", "updated_at", "action_by", "action_email", "action"}
)
# Flat fields US-4 reads, mapped to the nested proposal values they are derived from.
US4_PROPOSAL_ALIASES: dict[str, tuple[str, ...]] = {
    "annual_savings": ("savings", "estimated_annual_savings"),
    "risk_score": ("risk", "risk_score"),
    "target_platform": ("target_app",),
    "detected_dependencies": ("dependencies",),
}

# ──────────────────────────────────────────────
# US-6: Behavioral contract extraction (Trello)
# ──────────────────────────────────────────────

# US-5 gate that must be approved before any Trello data is read.
INVESTIGATION_GATE = "PERMISSION_TO_INVESTIGATE"

TRELLO_API_BASE_URL = "https://api.trello.com/1"
# Secret Manager secret names used on Cloud Run (names, not secrets).
TRELLO_API_KEY_SECRET_ID = "trello-api-key"  # noqa: S105
TRELLO_API_TOKEN_SECRET_ID = "trello-api-token"  # noqa: S105
TRELLO_TIMEOUT_SECONDS = 10.0
# Retry 429 (rate limit) and transient gateway errors only; 500 fails fast.
TRELLO_RETRY_STATUSES = frozenset({429, 502, 503, 504})
TRELLO_MAX_RETRIES = 3
TRELLO_MAX_RETRY_WAIT_SECONDS = 10.0
TRELLO_ACTIONS_PAGE_SIZE = 1000  # Trello's maximum for /boards/{id}/actions
TRELLO_MAX_ACTION_PAGES = 5

# Inferring automations from board activity (Butler rules have no public API).
INFERENCE_WINDOW_SECONDS = 60  # effect must follow its trigger on the same card
# Only effects performed by an app (appCreator set) count towards a contract.
INFERENCE_MIN_OCCURRENCES = 3
INFERENCE_MIN_RATIO = 0.8  # share of trigger occurrences followed by the automated effect

MAX_RULE_TEXT_LENGTH = 500
MAX_BUTLER_RULES_PER_CALL = 50
