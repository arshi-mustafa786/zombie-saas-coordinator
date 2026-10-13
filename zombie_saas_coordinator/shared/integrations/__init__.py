"""External integrations package.

Each integration client is created by the user story that needs it:
- US-4: slack.py
- US-6: trello.py
- US-7: asana.py
- US-10: zapier.py, make.py
"""

from zombie_saas_coordinator.shared.integrations.make import (
    MakeApiError,
    MakeClient,
    MakeCredentialsError,
    get_make_credentials,
    validate_make_zone,
)
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
from zombie_saas_coordinator.shared.integrations.zapier import (
    ZapierApiError,
    ZapierClient,
    ZapierCredentialsError,
    get_zapier_token,
)

__all__ = [
    "MakeApiError",
    "MakeClient",
    "MakeCredentialsError",
    "SSRFSecurityError",
    "TrelloApiError",
    "TrelloClient",
    "TrelloCredentialsError",
    "build_slack_approval_card",
    "dispatch_slack_message",
    "get_trello_credentials",
    "validate_board_id",
    "ZapierApiError",
    "ZapierClient",
    "ZapierCredentialsError",
    "get_make_credentials",
    "get_zapier_token",
    "validate_make_zone",
    "validate_slack_webhook_url",
]
