"""FastAPI application entry point for Cloud Run.

Exposes HTTP endpoints for:
- Cloud Scheduler triggers (cron jobs)
- Webhook ingestion (expense notifications)
- HITL approval callbacks (Slack/Teams)
- Health checks

The ADK agents are invoked from these endpoints as needed.
"""

from dotenv import load_dotenv
from fastapi import FastAPI

from zombie_saas_coordinator.api.scanner import router as scanner_router
from zombie_saas_coordinator.api.webhooks import router as webhooks_router

load_dotenv()

app = FastAPI(
    title="Zombie SaaS Coordinator",
    description="Multi-agent orchestration platform for SaaS consolidation",
    version="0.1.0",
)
app.include_router(webhooks_router)
app.include_router(scanner_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "zombie-saas-coordinator"}


# Import and register route modules
# These will be added by individual user stories:
# - US-4: from zombie_saas_coordinator.api.callbacks import router as callbacks_router
# - US-5: from zombie_saas_coordinator.api.approvals import router as approvals_router
