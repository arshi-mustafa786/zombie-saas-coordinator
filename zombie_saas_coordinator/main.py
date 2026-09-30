"""FastAPI application entry point for Cloud Run.

Exposes HTTP endpoints for:
- Cloud Scheduler triggers (cron jobs)
- Webhook ingestion (expense notifications)
- HITL approval callbacks (Slack/Teams)
- Health checks

The ADK agents are invoked from these endpoints as needed.
"""


from fastapi import FastAPI

app = FastAPI(
    title="Zombie SaaS Coordinator",
    description="Multi-agent orchestration platform for SaaS consolidation",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "zombie-saas-coordinator"}


# Import and register route modules
# These will be added by individual user stories:
# - US-1: from zombie_saas_coordinator.api.scanner import router as scanner_router
# - US-2: from zombie_saas_coordinator.api.webhooks import router as webhooks_router
# - US-4: from zombie_saas_coordinator.api.callbacks import router as callbacks_router
# - US-5: from zombie_saas_coordinator.api.approvals import router as approvals_router
