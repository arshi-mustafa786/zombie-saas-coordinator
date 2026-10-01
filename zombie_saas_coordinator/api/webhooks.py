"""HTTP endpoints for secure expense notification ingestion."""

import json
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from zombie_saas_coordinator.agents.auditor.tools import flag_subscription, validate_webhook
from zombie_saas_coordinator.shared.auth.hmac_validator import (
    InvalidSignatureError,
    WebhookSecretError,
)
from zombie_saas_coordinator.shared.models.expense import ExpenseEvent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/expense-notification", status_code=status.HTTP_202_ACCEPTED)
async def expense_notification(
    request: Request,
    signature: Annotated[str, Header(alias="X-Webhook-Signature")] = "",
) -> dict[str, object]:
    """Validate, classify, persist, and audit an expense webhook."""
    raw_payload = await request.body()
    try:
        validate_webhook(raw_payload.decode("utf-8"), signature)
    except InvalidSignatureError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except WebhookSecretError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook validation is temporarily unavailable",
        ) from error

    try:
        payload = json.loads(raw_payload)
        event = ExpenseEvent.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed expense payload",
        ) from error

    try:
        result = flag_subscription(event.model_dump(mode="json"))
    except Exception as error:
        # Cloud client timeouts and unavailable dependencies are retryable by
        # webhook providers. Detailed exceptions remain in server logs.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Expense processing is temporarily unavailable",
            headers={"Retry-After": "30"},
        ) from error

    return {"accepted": True, "event_id": event.event_id, "assessment": result}
