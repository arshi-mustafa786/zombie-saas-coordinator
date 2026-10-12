from dotenv import load_dotenv

load_dotenv()

from zombie_saas_coordinator.agent import root_agent

__all__ = ["root_agent"]
