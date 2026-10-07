"""Dispatch a fresh consolidation proposal interactive card to Slack."""

import os
import sys
import dotenv

dotenv.load_dotenv()

from scripts.create_fresh_proposal import create_fresh_proposal
from zombie_saas_coordinator.agents.auditor.tools import send_approval_card

# Default to the webhook URL provided
SLACK_WEBHOOK_URL = os.getenv(
    "SLACK_WEBHOOK_URL",
    "https://hooks.slack.com/services/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",
)

def main() -> None:
    print("=" * 70)
    print(" 1. Creating fresh consolidation proposal in Firestore...")
    proposal = create_fresh_proposal()
    print(f" [+] Proposal ID:    {proposal.proposal_id}")
    print(f" [+] Target App:     {proposal.app_name} -> {proposal.target_app}")
    print(f" [+] Annual Savings: ${proposal.savings.estimated_annual_savings:,.2f}")
    print(f" [+] Risk Score:     {proposal.risk.risk_score}/100")
    print(f" [+] Status:         {proposal.status.value.upper()}")
    print("-" * 70)

    print(" 2. Sending interactive Block Kit card to Slack...")
    print(f" [+] Webhook: {SLACK_WEBHOOK_URL[:45]}...")
    result = send_approval_card(proposal.proposal_id, SLACK_WEBHOOK_URL)

    if result.get("sent"):
        print("\n [SUCCESS] Approval card dispatched to Slack channel successfully!")
        print(f" Proposal ID for tracking: {proposal.proposal_id}")
        print(" Go to Slack and click [Approve Full Consolidation] or [Simulate Migration]!")
    else:
        print("\n [ERROR] Failed to send card to Slack:")
        print(f" Error detail: {result.get('error')}")
    print("=" * 70)

if __name__ == "__main__":
    main()
