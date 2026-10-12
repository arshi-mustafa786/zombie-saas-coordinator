"""API routes package.

Each route module is created by the user story that introduces it:
- US-1: scanner.py    (Cloud Scheduler trigger)
- US-2: webhooks.py   (Expense webhook ingestion)
- US-4: callbacks.py  (Slack/Teams interaction callbacks)
- US-5: approvals.py  (HITL authorization endpoint)
"""

from zombie_saas_coordinator.api import (
    approvals,
    callbacks,
    proposals,
    quarantine,
    scanner,
    webhooks,
)

__all__ = ["approvals", "callbacks", "proposals", "quarantine", "scanner", "webhooks"]
