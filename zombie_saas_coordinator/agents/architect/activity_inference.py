"""Infer Butler-style automations from Trello board activity.

Trello has no API for reading Butler rules, but their effects appear in the
board's action history: e.g. every time a card is moved into "Done", the
same card is archived a few seconds later. A (trigger -> effect) pair that
repeats consistently is reported as an inferred contract with a confidence
score; it is never presented as an exact rule.
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

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
    ParserType,
    RuleSource,
    TriggerEvent,
)

# (event or action type, sorted condition/param items) — hashable keys for counting.
_Key = tuple[str, tuple[tuple[str, str], ...]]


def infer_contracts(actions: list[dict[str, Any]], board_id: str) -> list[BehavioralContract]:
    """Return contracts for trigger->effect pairs that repeat consistently on the board."""
    events_by_card: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # Trello returns newest first; walk oldest first so the stable sort below keeps
    # a trigger ahead of an effect that shares its timestamp.
    for action in reversed(actions):
        event = _to_event(action)
        if event:
            events_by_card[event["card_id"]].append(event)

    trigger_counts: Counter[_Key] = Counter()
    pair_counts: Counter[tuple[_Key, _Key]] = Counter()
    pair_app_counts: Counter[tuple[_Key, _Key]] = Counter()

    for events in events_by_card.values():
        events.sort(key=lambda event: event["at"])
        for index, cause in enumerate(events):
            if cause["trigger"] is None:
                continue
            trigger_counts[cause["trigger"]] += 1
            seen: set[_Key] = set()
            for effect in events[index + 1 :]:
                if (effect["at"] - cause["at"]).total_seconds() > INFERENCE_WINDOW_SECONDS:
                    break
                key = effect["effect"]
                if key is None or key in seen or _is_same_change(cause["trigger"], key):
                    continue
                seen.add(key)
                pair_counts[(cause["trigger"], key)] += 1
                if effect["by_app"]:
                    pair_app_counts[(cause["trigger"], key)] += 1

    contracts: list[BehavioralContract] = []
    for (trigger_key, effect_key), observed in sorted(pair_counts.items()):
        occurrences = trigger_counts[trigger_key]
        ratio = observed / occurrences
        if observed < INFERENCE_MIN_OCCURRENCES or ratio < INFERENCE_MIN_RATIO:
            continue
        app_fraction = pair_app_counts[(trigger_key, effect_key)] / observed
        # Effects attributed to an app (Butler) are stronger evidence than user activity.
        confidence = round(min(ratio, 1.0) * (1.0 if app_fraction >= 0.5 else 0.8), 2)
        trigger = ContractTrigger(
            event=TriggerEvent(trigger_key[0]), conditions=dict(trigger_key[1])
        )
        contracts.append(
            BehavioralContract(
                source=RuleSource.INFERRED_FROM_ACTIVITY,
                parser=ParserType.ACTIVITY,
                trigger=trigger,
                actions=[
                    ContractAction(type=ActionType(effect_key[0]), params=dict(effect_key[1]))
                ],
                scope={"board_id": board_id, **trigger.conditions},
                confidence=confidence,
                evidence_count=observed,
                metadata={
                    "trigger_occurrences": occurrences,
                    "observed_ratio": round(ratio, 2),
                    "app_created_fraction": round(app_fraction, 2),
                    "window_seconds": INFERENCE_WINDOW_SECONDS,
                },
            )
        )
    return contracts


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
        # Actions performed by an app or Power-Up (Butler) carry an appCreator.
        "by_app": bool(action.get("appCreator")),
    }


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
