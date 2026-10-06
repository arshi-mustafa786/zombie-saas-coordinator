"""Slack Block Kit integration for US-4 Interactive Approval Cards."""

import ipaddress
import urllib.parse
from typing import Any

import httpx

from zombie_saas_coordinator.shared.models.proposal import ConsolidationProposal


class SSRFSecurityError(ValueError):
    """Raised when an incoming or requested URL attempts Server-Side Request Forgery."""

    pass


ALLOWED_WEBHOOK_HOSTS = {
    "hooks.slack.com",
    "slack.com",
}


def validate_slack_webhook_url(url: str) -> bool:
    """Validates that a Slack webhook URL is safe against SSRF attacks.

    Requirements:
    - Must use HTTPS scheme.
    - Must resolve strictly to allowed Slack domains.
    - Must not target private/loopback/cloud-metadata IP ranges.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise SSRFSecurityError(f"Insecure protocol '{parsed.scheme}'; only HTTPS is allowed.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SSRFSecurityError("Invalid URL: missing hostname.")

    # Check for IP literal attempts
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise SSRFSecurityError(
                f"Target IP address '{hostname}' is a forbidden private/local range."
            )
    except ValueError:
        pass  # Not an IP literal; proceed to domain check

    # Domain whitelist check
    if not any(
        hostname == allowed or hostname.endswith("." + allowed) for allowed in ALLOWED_WEBHOOK_HOSTS
    ):
        raise SSRFSecurityError(
            f"Domain '{hostname}' is not in the allowed Slack webhook whitelist."
        )

    return True


def build_slack_approval_card(proposal: ConsolidationProposal) -> dict[str, Any]:
    """Builds a rich Slack Block Kit message payload for a consolidation proposal."""
    dependencies_text = (
        "\n".join(f"• {dep}" for dep in proposal.detected_dependencies) or "• None detected"
    )
    if len(dependencies_text) > 2000:
        dependencies_text = dependencies_text[:1997] + "..."

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": (
                    f"🚨 Zombie SaaS Detected: {proposal.app_name} → {proposal.target_platform}"
                ),
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Target Platform:*\n{proposal.target_platform}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Est. Annual Savings:*\n${proposal.annual_savings:,.2f}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Risk Score:*\n`{proposal.risk_score} / 100`",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Proposal ID:*\n`{proposal.proposal_id}`",
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Recommendation:*\n{proposal.recommendation}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Detected Dependencies & Automations:*\n{dependencies_text}",
            },
        },
        {
            "type": "divider",
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Simulate Migration",
                        "emoji": True,
                    },
                    "action_id": "simulate_migration",
                    "value": proposal.proposal_id,
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Approve Full Consolidation",
                        "emoji": True,
                    },
                    "style": "primary",
                    "action_id": "approve_consolidation",
                    "value": proposal.proposal_id,
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Ignore / Whitelist",
                        "emoji": True,
                    },
                    "style": "danger",
                    "action_id": "ignore_whitelist",
                    "value": proposal.proposal_id,
                },
            ],
        },
    ]

    return {
        "text": (
            f"Consolidation Proposal for {proposal.app_name} "
            f"(${proposal.annual_savings:,.2f} savings)"
        ),
        "blocks": blocks,
    }


def dispatch_slack_message(
    channel_or_webhook: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Dispatches a formatted Block Kit message to a Slack channel or webhook.

    Validates webhook URL against SSRF and executes the HTTP POST request.
    """
    validate_slack_webhook_url(channel_or_webhook)

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(channel_or_webhook, json=payload)
            response.raise_for_status()
            return {
                "sent": True,
                "status_code": response.status_code,
                "message_id": f"slack_msg_{response.status_code}",
                "response_text": response.text,
            }
    except httpx.HTTPError as exc:
        return {
            "sent": False,
            "status_code": getattr(exc.response, "status_code", 500)
            if hasattr(exc, "response")
            else 500,
            "error": str(exc),
        }
