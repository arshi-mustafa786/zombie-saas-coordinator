"""Agents subpackage entry point for ADK loader.

Re-exports root_agent and agent from the main zombie_saas_coordinator package
so ADK CLI can resolve the root orchestrator when scanning the agents directory.
"""

from zombie_saas_coordinator.agent import agent, root_agent  # noqa: F401
