"""Behavioral contract models (US-6), read by US-7 schema diffing.

A ``ContractExtraction`` is the audit-trail document for one Trello board:
the board's structure (``BoardSnapshot``) plus the automation rules
(``BehavioralContract``) found on it.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from zombie_saas_coordinator.shared.constants import MAX_RULE_TEXT_LENGTH


class RuleSource(StrEnum):
    """Where a contract came from."""

    BUTLER_RULE_TEXT = "butler_rule_text"  # rule text supplied by a user
    INFERRED_FROM_ACTIVITY = "inferred_from_activity"  # pattern in board history


class ParserType(StrEnum):
    """How a contract was turned into structured form."""

    GRAMMAR = "grammar"
    GEMINI = "gemini"
    ACTIVITY = "activity"
    UNPARSED = "unparsed"


class TriggerEvent(StrEnum):
    """Canonical trigger vocabulary shared with US-7/US-8."""

    CARD_MOVED_TO_LIST = "card_moved_to_list"
    CARD_CREATED_IN_LIST = "card_created_in_list"
    LABEL_ADDED = "label_added"
    LABEL_REMOVED = "label_removed"
    DUE_MARKED_COMPLETE = "due_marked_complete"
    CARD_ARCHIVED = "card_archived"
    CHECKLIST_COMPLETED = "checklist_completed"


class ActionType(StrEnum):
    """Canonical action vocabulary shared with US-7/US-8."""

    ARCHIVE_CARD = "archive_card"
    MOVE_CARD = "move_card"
    ADD_LABEL = "add_label"
    REMOVE_LABEL = "remove_label"
    MARK_DUE_COMPLETE = "mark_due_complete"
    POST_COMMENT = "post_comment"
    NOTIFY = "notify"
    SET_DUE_DATE = "set_due_date"
    ADD_MEMBER = "add_member"


class ContractTrigger(BaseModel):
    """When the rule fires, e.g. ``card_moved_to_list`` with ``{"list": "Done"}``."""

    model_config = ConfigDict(frozen=True)

    event: TriggerEvent
    conditions: dict[str, str] = Field(default_factory=dict)


class ContractAction(BaseModel):
    """What the rule does, e.g. ``move_card`` with ``{"list": "Archive"}``."""

    model_config = ConfigDict(frozen=True)

    type: ActionType
    params: dict[str, str] = Field(default_factory=dict)


class BehavioralContract(BaseModel):
    """One automation rule in canonical ``{trigger, actions, scope}`` form.

    An unparsed rule keeps its raw text with no trigger/actions, so nothing
    is silently dropped and US-8 can flag it for manual review.
    """

    model_config = ConfigDict(frozen=True)

    contract_id: str = Field(default_factory=lambda: f"bc_{uuid4().hex[:12]}", min_length=1)
    source: RuleSource
    parser: ParserType
    trigger: ContractTrigger | None = None
    actions: list[ContractAction] = Field(default_factory=list)
    scope: dict[str, str] = Field(default_factory=dict)
    raw_text: str = Field(default="", max_length=MAX_RULE_TEXT_LENGTH)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0, description="Observed occurrences (inferred)")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _parsed_rules_are_complete(self) -> "BehavioralContract":
        if self.parser == ParserType.UNPARSED:
            if self.trigger is not None or self.actions:
                raise ValueError("an unparsed contract cannot carry a trigger or actions")
            if not self.raw_text:
                raise ValueError("an unparsed contract must keep its raw rule text")
        elif self.trigger is None or not self.actions:
            raise ValueError("a parsed contract needs a trigger and at least one action")
        return self


class ObservedPattern(BaseModel):
    """A repeated trigger->effect sequence performed by people, not by an automation.

    Weak evidence only: it may be a team habit rather than a rule, so it is never
    published as a ``BehavioralContract`` and downstream stories must not enforce it.
    """

    model_config = ConfigDict(frozen=True)

    trigger: ContractTrigger
    action: ContractAction
    occurrences: int = Field(ge=0, description="Times the effect followed the trigger")
    trigger_occurrences: int = Field(ge=0)
    ratio: float = Field(ge=0.0, le=1.0)
    app_attributed: int = Field(
        default=0, ge=0, description="Of the occurrences, how many an app performed"
    )
    note: str = "Effects were performed by users, not an automation; not a contract."


class ListInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    closed: bool = False


class LabelInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    color: str | None = None


class CustomFieldInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    type: str
    options: list[str] = Field(default_factory=list, description="Values of a dropdown field")


class PowerUpInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""


class BoardSnapshot(BaseModel):
    """Board structure and usage counts. Card titles/descriptions are never stored."""

    model_config = ConfigDict(frozen=True)

    board_id: str = Field(min_length=1)
    name: str = ""
    url: str = ""
    closed: bool = False
    lists: list[ListInfo] = Field(default_factory=list)
    labels: list[LabelInfo] = Field(default_factory=list)
    custom_fields: list[CustomFieldInfo] = Field(default_factory=list)
    power_ups: list[PowerUpInfo] = Field(default_factory=list)
    cards_total: int = Field(default=0, ge=0)
    cards_archived: int = Field(default=0, ge=0)
    cards_with_due: int = Field(default=0, ge=0)
    cards_due_complete: int = Field(default=0, ge=0)
    cards_with_checklists: int = Field(default=0, ge=0)
    checklists_count: int = Field(default=0, ge=0)
    checklist_items_count: int = Field(default=0, ge=0)
    label_usage: dict[str, int] = Field(
        default_factory=dict, description="Label id -> number of cards using it"
    )


class ContractExtraction(BaseModel):
    """Audit-trail document stored in ``behavioral_contracts`` for one board."""

    model_config = ConfigDict(frozen=True)

    extraction_id: str = Field(default_factory=lambda: f"bcx_{uuid4().hex[:12]}", min_length=1)
    proposal_id: str = Field(min_length=1)
    board: BoardSnapshot
    contracts: list[BehavioralContract] = Field(default_factory=list)
    observed_patterns: list[ObservedPattern] = Field(
        default_factory=list, description="User habits seen in activity; not contracts"
    )
    api_calls: list[dict[str, Any]] = Field(
        default_factory=list, description="Trello requests made (no credentials)"
    )
    warnings: list[str] = Field(default_factory=list)
    extracted_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    extracted_by: str = Field(default="system:architect_agent", min_length=1)
