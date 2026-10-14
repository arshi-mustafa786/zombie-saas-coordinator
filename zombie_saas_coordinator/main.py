"""FastAPI application entry point for Cloud Run.

Exposes HTTP endpoints for:
- Cloud Scheduler triggers (cron jobs)
- Webhook ingestion (expense notifications)
- HITL approval callbacks (Slack/Teams)
- Health checks

The ADK agents are invoked from these endpoints as needed.
"""

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI

from zombie_saas_coordinator.api.approvals import router as approvals_router
from zombie_saas_coordinator.api.callbacks import router as callbacks_router
from zombie_saas_coordinator.api.proposals import router as proposals_router
from zombie_saas_coordinator.api.quarantine import router as quarantine_router
from zombie_saas_coordinator.api.reconciliation import router as reconciliation_router
from zombie_saas_coordinator.api.scanner import router as scanner_router
from zombie_saas_coordinator.api.webhooks import router as webhooks_router

load_dotenv()

app = FastAPI(
    title="Zombie SaaS Coordinator",
    description="Multi-agent orchestration platform for SaaS consolidation",
    version="0.1.0",
)
app.include_router(webhooks_router)
app.include_router(callbacks_router)
app.include_router(proposals_router)
app.include_router(scanner_router)
app.include_router(approvals_router)
app.include_router(quarantine_router)
app.include_router(reconciliation_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "zombie-saas-coordinator"}


@app.get("/readiness")
async def readiness_check() -> dict[str, Any]:
    """Readiness probe endpoint for Cloud Run container validation."""
    checks: dict[str, str] = {"service": "ready"}
    try:
        from zombie_saas_coordinator.shared.db.firestore_client import get_firestore_client

        db = get_firestore_client()
        if db:
            checks["firestore"] = "connected"
    except Exception as exc:
        checks["firestore"] = f"degraded: {exc}"
    return {"status": "ready", "checks": checks}

