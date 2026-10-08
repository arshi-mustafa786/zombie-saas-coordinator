"""Infer Butler-style automations from Trello board activity.

Trello has no API for reading Butler rules, but their effects appear in the
board's action history: e.g. every time a card is moved into "Done", the
same card is archived a few seconds later *by Butler*.

Timing alone does not prove causation (a person may label a card "Urgent"
and then move it by hand), so only effects attributed to an app via the
action's ``appCreator`` count as evidence for a contract. Repeated sequences
performed by people are returned separately as ``ObservedPattern`` (weak
evidence) and are never published as contracts.
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, NamedTuple

from zombie_saas_coordinator.shared.constants import (
    INFERENCE_MIN_OCCURRENCES,
    INFERENCE_MIN_RATIO,
    INFERENCE_WINDOW_SECONDS,
)
from zombie_saas_coordinator.shared.models.contract import (
    ActionType,
    BehavioralContract,
    ContractAction,
    ContractTrigger,
    ObservedPattern,
    ParserType,
    RuleSource,
    TriggerEvent,
)

# (event or action type, sorted condition/param items) — hashable keys for counting.
_Key = tuple[str, tuple[tuple[str, str], ...]]


class InferenceResult(NamedTuple):
    contracts: list[BehavioralContract]  # automation-attributed: publishable contracts
    observed_patterns: list[ObservedPattern]  # person-attributed: weak evidence only


def infer_contracts(actions: list[dict[str, Any]], board_id: str) -> InferenceResult:
    """Split repeated trigger->effect pairs into app-performed contracts and user patterns."""
    events_by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # Trello returns newest first; walk oldest first so the stable sort below keeps
    # a trigger ahead of an effect that shares its timestamp.
    for action in reversed(actions):
        event = _to_event(action)
        if event:
            events_by_card[event["card_id"]].append(event)

    trigger_counts: Counter[_Key] = Counter()
    app_pairs: Counter[tuple[_Key, _Key]] = Counter()
    user_pairs: Counter[tuple[_Key, _Key]] = Counter()
    actors: dict[tuple[_Key, _Key], Counter[str]] = defaultdict(Counter)

    for events in events_by_card.values():
        events.sort(key=lambda event: event["at"])
        for index, cause in enumerate(events):
            if cause["trigger"] is None:
                continue
            trigger_counts[cause["trigger"]] += 1
            # Effects in the window after this trigger; an app-performed one wins.
            followed: dict[_Key, str | None] = {}
            for effect in events[index + 1 :]:
                if (effect["at"] - cause["at"]).total_seconds() > INFERENCE_WINDOW_SECONDS:
                    break
                key = effect["effect"]
                if key is None or _is_same_change(cause["trigger"], key):
                    continue
                if followed.get(key) is None:
                    followed[key] = effect["actor"]
            for key, actor in followed.items():
                pair = (cause["trigger"], key)
                if actor:
                    app_pairs[pair] += 1
                    actors[pair][actor] += 1
                else:
                    user_pairs[pair] += 1

    contracts: list[BehavioralContract] = []
    patterns: list[ObservedPattern] = []
    for pair in sorted(set(app_pairs) | set(user_pairs)):
        trigger_key, effect_key = pair
        occurrences = trigger_counts[trigger_key]
        trigger = ContractTrigger(
            event=TriggerEvent(trigger_key[0]), conditions=dict(trigger_key[1])
        )
        action = ContractAction(type=ActionType(effect_key[0]), params=dict(effect_key[1]))
        app_ratio = app_pairs[pair] / occurrences

        if app_pairs[pair] >= INFERENCE_MIN_OCCURRENCES and app_ratio >= INFERENCE_MIN_RATIO:
            contracts.append(
                BehavioralContract(
                    source=RuleSource.INFERRED_FROM_ACTIVITY,
                    parser=ParserType.ACTIVITY,
                    trigger=trigger,
                    actions=[action],
                    scope={"board_id": board_id, **trigger.conditions},
                    confidence=round(min(app_ratio, 1.0), 2),
                    evidence_count=app_pairs[pair],
                    metadata={
                        "automation_actor": actors[pair].most_common(1)[0][0],
                        "trigger_occurrences": occurrences,
                        "app_attributed_effects": app_pairs[pair],
                        "user_attributed_effects": user_pairs[pair],
                        "window_seconds": INFERENCE_WINDOW_SECONDS,
                    },
                )
            )
            continue

        observed = app_pairs[pair] + user_pairs[pair]
        ratio = observed / occurrences
        if observed >= INFERENCE_MIN_OCCURRENCES and ratio >= INFERENCE_MIN_RATIO:
            patterns.append(
                ObservedPattern(
                    trigger=trigger,
                    action=action,
                    occurrences=observed,
                    trigger_occurrences=occurrences,
                    ratio=round(min(ratio, 1.0), 2),
                    app_attributed=app_pairs[pair],
                )
            )
    return InferenceResult(contracts, patterns)


def _to_event(action: dict[str, Any]) -> dict[str, Any] | None:
    """Map one Trello action to the trigger it represents and the effect it performs."""
    data = action.get("data") or {}
    card_id = (data.get("card") or {}).get("id")
    date = action.get("date")
    if not card_id or not date:
        return None

    kind = action.get("type")
    old = data.get("old") or {}
    card = data.get("card") or {}
    trigger: _Key | None = None
    effect: _Key | None = None

    if kind == "createCard":
        list_name = (data.get("list") or {}).get("name")
        if list_name:
            trigger = (TriggerEvent.CARD_CREATED_IN_LIST.value, (("list", list_name),))
    elif kind == "updateCard" and data.get("listAfter"):
        list_name = data["listAfter"].get("name", "")
        trigger = (TriggerEvent.CARD_MOVED_TO_LIST.value, (("list", list_name),))
        effect = (ActionType.MOVE_CARD.value, (("list", list_name),))
    elif kind == "updateCard" and old.get("closed") is False and card.get("closed") is True:
        trigger = (TriggerEvent.CARD_ARCHIVED.value, ())
        effect = (ActionType.ARCHIVE_CARD.value, ())
    elif kind == "updateCard" and old.get("dueComplete") is False and card.get("dueComplete"):
        trigger = (TriggerEvent.DUE_MARKED_COMPLETE.value, ())
        effect = (ActionType.MARK_DUE_COMPLETE.value, ())
    elif kind in ("addLabelToCard", "removeLabelFromCard"):
        label = _label_name(data.get("label") or {})
        added = kind == "addLabelToCard"
        trigger = (
            (TriggerEvent.LABEL_ADDED if added else TriggerEvent.LABEL_REMOVED).value,
            (("label", label),),
        )
        effect = (
            (ActionType.ADD_LABEL if added else ActionType.REMOVE_LABEL).value,
            (("label", label),),
        )

    if trigger is None and effect is None:
        return None
    return {
        "card_id": card_id,
        "at": datetime.fromisoformat(date),
        "trigger": trigger,
        "effect": effect,
        "actor": _automation_actor(action),
    }


def _automation_actor(action: dict[str, Any]) -> str | None:
    """Who performed the action if it was an app, else None (a person).

    ``appCreator`` is null for actions made with a user's own token and set for
    actions made by an app; Butler's carries a name. Verify against a live board.
    """
    app = action.get("appCreator") or {}
    if not app.get("id") and not app.get("name"):
        return None
    if "butler" in str(app.get("name", "")).casefold():
        return "butler"
    return f"app:{app.get('id') or app.get('name')}"


def _label_name(label: dict[str, Any]) -> str:
    """Labels can be colour-only with an empty name."""
    return (
        label.get("name")
        or (f"color:{label['color']}" if label.get("color") else "")
        or label.get("id", "")
    )


def _is_same_change(trigger: _Key, effect: _Key) -> bool:
    """A move into list X is not 'caused' by a move into list X (same for labels)."""
    paired = {
        TriggerEvent.CARD_MOVED_TO_LIST.value: ActionType.MOVE_CARD.value,
        TriggerEvent.LABEL_ADDED.value: ActionType.ADD_LABEL.value,
        TriggerEvent.LABEL_REMOVED.value: ActionType.REMOVE_LABEL.value,
        TriggerEvent.CARD_ARCHIVED.value: ActionType.ARCHIVE_CARD.value,
        TriggerEvent.DUE_MARKED_COMPLETE.value: ActionType.MARK_DUE_COMPLETE.value,
    }
    return paired.get(trigger[0]) == effect[0] and trigger[1] == effect[1]
