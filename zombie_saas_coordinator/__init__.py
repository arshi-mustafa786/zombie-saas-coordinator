"""Zombie SaaS Coordinator — Root Package.

Exports the root_agent for Google ADK CLI discovery.
Usage:
    adk web zombie_saas_coordinator
    adk run zombie_saas_coordinator
    adk deploy cloud_run zombie_saas_coordinator
"""

from dotenv import load_dotenv

load_dotenv()

from zombie_saas_coordinator.agent import agent, root_agent  # noqa: E402, F401
