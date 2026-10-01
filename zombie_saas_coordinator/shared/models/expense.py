"""Data models for expense webhook ingestion."""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

BillingFrequency = Literal["weekly", "monthly", "quarterly", "annual", "yearly", "one_time"]


class ExpenseEvent(BaseModel):
    """Normalized expense notification received from a card provider."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    event_id: str = ""
    external_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("external_id", "transaction_id", "provider_event_id", "id"),
    )
    merchant: str = Field(
        min_length=1,
        validation_alias=AliasChoices("merchant", "merchant_name"),
    )
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    frequency: BillingFrequency = Field(
        validation_alias=AliasChoices("frequency", "billing_frequency")
    )
    renewal_date: date | None = Field(
        default=None,
        validation_alias=AliasChoices("renewal_date", "contract_renewal_date"),
    )
    provider: str | None = None
    card_last_four: str | None = Field(default=None, pattern=r"^\d{4}$")
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("merchant")
    @classmethod
    def normalize_merchant(cls, value: str) -> str:
        """Reject whitespace-only merchant names and normalize surrounding space."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("merchant must not be blank")
        return normalized

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        """Store ISO currency codes consistently."""
        return value.upper()

    @model_validator(mode="after")
    def assign_deterministic_event_id(self) -> "ExpenseEvent":
        """Generate an idempotency key that remains stable across webhook retries."""
        if self.event_id:
            return self

        provider = (self.provider or "unknown").casefold()
        identity = (
            {"external_id": self.external_id, "provider": provider}
            if self.external_id
            else {
                "amount": str(self.amount.normalize()),
                "card_last_four": self.card_last_four,
                "currency": self.currency,
                "frequency": self.frequency,
                "merchant": self.merchant.casefold(),
                "provider": provider,
                "renewal_date": self.renewal_date.isoformat() if self.renewal_date else None,
            }
        )
        canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
        self.event_id = "expense_" + hashlib.sha256(canonical.encode()).hexdigest()
        return self


class SubscriptionAssessment(BaseModel):
    """Result of comparing an expense event with subscription policy."""

    status: str
    flagged: bool
    reason: str
    reasons: list[str]
    priority: Literal["normal", "high", "immediate"]
    route_to: str | None = None
    approved: bool
    recurring: bool
    monthly_equivalent: Decimal
    renewal_opportunity: bool
    confidence: Literal["low", "high"]
    duplicate: bool = False
    event: dict[str, Any]
