"""Data models for expense webhook ingestion."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

BillingFrequency = Literal["weekly", "monthly", "quarterly", "annual", "yearly", "one_time"]


class ExpenseEvent(BaseModel):
    """Normalized expense notification received from a card provider."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
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
    event: dict[str, Any]
