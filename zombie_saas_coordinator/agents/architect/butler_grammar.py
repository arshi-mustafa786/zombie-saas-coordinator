"""Deterministic parser for Trello Butler rule text.

Butler rules have no public API, but users can copy a rule's text from the
Trello UI, e.g.::

    when a card is moved into list "Done" by anyone, archive the card

Butler phrases rules in a fixed grammar, so the common triggers and actions
are matched with regexes here; only text this parser cannot handle is sent
to Gemini.
"""

import re

from zombie_saas_coordinator.shared.models.contract import (
    ActionType,
    ContractAction,
    ContractTrigger,
    TriggerEvent,
)

_QUOTED = r'"(?P<{name}>[^"]+)"'

_RULE = re.compile(r"^\s*when\s+(?P<trigger>.+?),\s*(?P<actions>.+?)\s*\.?\s*$", re.I | re.S)
# "by anyone", "by me", "by @user" qualify who fired the trigger; ignored for the contract.
_BY_ACTOR = re.compile(r"\s+by\s+(?:anyone|me|@?\S+)\s*$", re.I)
# Split actions on ", ", ", and ", " and " that are not inside quotes.
_ACTION_SEPARATOR = re.compile(r'(?:,\s*(?:and\s+)?|\s+and\s+)(?=(?:[^"]*"[^"]*")*[^"]*$)', re.I)

_TRIGGERS: list[tuple[re.Pattern[str], TriggerEvent, str | None]] = [
    (
        re.compile(
            r"^a card is (?:moved|added) (?:into|to) (?:the )?list " + _QUOTED.format(name="v"),
            re.I,
        ),
        TriggerEvent.CARD_MOVED_TO_LIST,
        "list",
    ),
    (
        re.compile(r"^a card is created in (?:the )?list " + _QUOTED.format(name="v"), re.I),
        TriggerEvent.CARD_CREATED_IN_LIST,
        "list",
    ),
    (
        re.compile(r"^the " + _QUOTED.format(name="v") + r" label is added to a card", re.I),
        TriggerEvent.LABEL_ADDED,
        "label",
    ),
    (
        re.compile(r"^the " + _QUOTED.format(name="v") + r" label is removed from a card", re.I),
        TriggerEvent.LABEL_REMOVED,
        "label",
    ),
    (
        re.compile(r"^(?:a card|the due date) is marked as complete", re.I),
        TriggerEvent.DUE_MARKED_COMPLETE,
        None,
    ),
    (re.compile(r"^a card is archived", re.I), TriggerEvent.CARD_ARCHIVED, None),
    (
        re.compile(r"^(?:a|all) checklists? (?:is|are) completed", re.I),
        TriggerEvent.CHECKLIST_COMPLETED,
        None,
    ),
]

_ACTIONS: list[tuple[re.Pattern[str], ActionType]] = [
    (re.compile(r"^archive the card$", re.I), ActionType.ARCHIVE_CARD),
    (
        re.compile(
            r"^move the card to (?:the (?P<position>top|bottom) of )?(?:the )?list "
            + _QUOTED.format(name="list")
            + r"$",
            re.I,
        ),
        ActionType.MOVE_CARD,
    ),
    (
        re.compile(r"^add the " + _QUOTED.format(name="label") + r" label to the card$", re.I),
        ActionType.ADD_LABEL,
    ),
    (
        re.compile(r"^remove the " + _QUOTED.format(name="label") + r" label from the card$", re.I),
        ActionType.REMOVE_LABEL,
    ),
    (
        re.compile(r"^mark the (?:due date|card) as complete$", re.I),
        ActionType.MARK_DUE_COMPLETE,
    ),
    (
        re.compile(r"^post comment " + _QUOTED.format(name="comment") + r"$", re.I),
        ActionType.POST_COMMENT,
    ),
    (
        re.compile(
            r"^(?:send an email notification to|notify) " + _QUOTED.format(name="target") + r".*$",
            re.I,
        ),
        ActionType.NOTIFY,
    ),
    (re.compile(r"^set due (?:date )?(?P<when>.+)$", re.I), ActionType.SET_DUE_DATE),
    (
        re.compile(r"^(?:join the card|add (?P<member>me|@\S+) to the card)$", re.I),
        ActionType.ADD_MEMBER,
    ),
]


def normalise_rule_text(text: str) -> str:
    """Straighten curly quotes and collapse whitespace, as copied from the Trello UI."""
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip()
    # A rule copied together with its surrounding quote: drop the stray opening quote.
    return re.sub(r'^"\s*(?=when\b)', "", text, flags=re.I)


def parse_butler_rule(
    text: str,
) -> tuple[ContractTrigger | None, list[ContractAction], list[str]]:
    """Parse one Butler rule into (trigger, actions, unparsed action fragments).

    The trigger is None when the rule shape or trigger is not recognised.
    """
    rule = _RULE.match(normalise_rule_text(text))
    if not rule:
        return None, [], []

    trigger = _parse_trigger(_BY_ACTOR.sub("", rule.group("trigger").strip()))
    actions: list[ContractAction] = []
    unparsed: list[str] = []
    for fragment in _ACTION_SEPARATOR.split(rule.group("actions")):
        fragment = fragment.strip()
        if not fragment:
            continue
        action = _parse_action(fragment)
        if action is None:
            unparsed.append(fragment)
        else:
            actions.append(action)
    return trigger, actions, unparsed


def _parse_trigger(text: str) -> ContractTrigger | None:
    for pattern, event, condition in _TRIGGERS:
        match = pattern.match(text)
        if match:
            conditions = {condition: match.group("v")} if condition else {}
            return ContractTrigger(event=event, conditions=conditions)
    return None


def _parse_action(text: str) -> ContractAction | None:
    for pattern, action_type in _ACTIONS:
        match = pattern.match(text)
        if match:
            params = {key: value for key, value in match.groupdict().items() if value}
            return ContractAction(type=action_type, params=params)
    return None
