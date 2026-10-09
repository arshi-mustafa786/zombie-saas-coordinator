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
from zombie_saas_coordinator.shared.integrations.trello import (
    TrelloApiError,
    TrelloClient,
    TrelloCredentialsError,
    get_trello_credentials,
    validate_board_id,
)

__all__ = [
    "SSRFSecurityError",
    "TrelloApiError",
    "TrelloClient",
    "TrelloCredentialsError",
    "build_slack_approval_card",
    "dispatch_slack_message",
    "get_trello_credentials",
    "validate_board_id",
    "validate_slack_webhook_url",
]
