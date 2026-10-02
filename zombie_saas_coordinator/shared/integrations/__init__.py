"""External integrations package.

Each integration client is created by the user story that needs it:
- US-4: slack.py
- US-6: trello.py
- US-7: asana.py
- US-10: zapier.py, make.py
"""

from zombie_saas_coordinator.shared.integrations.slack import (
    SSRFSecurityError,
    build_slack_approval_card,
    dispatch_slack_message,
    validate_slack_webhook_url,
)

__all__ = [
    "SSRFSecurityError",
    "build_slack_approval_card",
    "dispatch_slack_message",
    "validate_slack_webhook_url",
]
