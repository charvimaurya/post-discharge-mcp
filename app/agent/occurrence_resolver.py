"""
Decide which occurrence a completion report is about.

"I'm back from my walk" must record the walk that is due now, not
make the patient choose between walks. This is plain code with no
AWS or model calls, so the choice is predictable and testable.

Rules, in order, for one item (for example the walk task):

    a. A waiting reminder for an occurrence of this item wins.
    b. Otherwise the earliest pending occurrence that is due by
       now + 60 minutes. An occurrence without a clock time (most
       medicine doses) is due only once its time of day has started.
    c. If two or more pending occurrences are already due, ask
       which one, naming them as people speak.
    d. A completed occurrence is never chosen again. If the item
       was already done and the next one is later, say so and
       record nothing.

The resolver only runs when the patient has not named a specific
occurrence ("my 7:30 walk", "my morning paracetamol"); those, and
anything it cannot match to one item, are left to the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any

from app.reminders.text import short_task_name


DUE_WINDOW = timedelta(minutes=60)

# When each time of day starts. Matches the boundaries used for
# spoken reminder text (app/reminders/text.py).
SLOT_STARTS = {
    "morning": time(5, 0),
    "midday": time(12, 0),
    "afternoon": time(14, 0),
    "evening": time(17, 0),
    "bedtime": time(21, 0),
}

# Words that name a particular occurrence. If the patient uses one,
# the resolver steps aside and the model handles the request.
_NAMED_OCCURRENCE = re.compile(
    r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b|o'clock|"
    r"\b(morning|midday|lunchtime|afternoon|evening|bedtime|night|tonight|"
    r"first|second|third|1st|2nd|3rd|last|other)\b",
    re.IGNORECASE,
)

# "My morning walk": a part of the day, with no clock time or "second" beside it.
_NAMED_PART = re.compile(r"\b(morning|midday|lunchtime|afternoon|evening|bedtime)\b", re.IGNORECASE)
_NAMED_EXACTLY = re.compile(
    r"\b\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\b|o'clock|"
    r"\b(night|tonight|first|second|third|1st|2nd|3rd|last|other)\b",
    re.IGNORECASE,
)

# Words in a completion report that never identify an item.
_STOPWORDS = {
    "alexa", "back", "from", "done", "finished", "completed", "taken",
    "took", "have", "with", "just", "that", "this", "today", "again",
    "your", "mine", "also", "already", "i've", "i'm", "it's", "now",
}


@dataclass
class Resolution:
    """
    What to do with a completion report.

    action:
        "record"        write `occurrence`
        "ask"           ask which of `choices`
        "already_done"  nothing to write; `done` was recorded,
                        `next_up` (if any) is the next one
        "nothing"       no occurrence of this item today
        "model"         not resolvable here; let the model handle it
    """

    action: str
    occurrence: dict[str, Any] | None = None
    choices: list[dict[str, Any]] = field(default_factory=list)
    done: dict[str, Any] | None = None
    next_up: dict[str, Any] | None = None
    item_occurrences: list[dict[str, Any]] = field(default_factory=list)


def names_specific_occurrence(message: str) -> bool:
    """True when the patient says which one ("my 7:30 walk", "second walk")."""

    return bool(_NAMED_OCCURRENCE.search(message or ""))


def item_id(occurrence: dict[str, Any]) -> str:
    """The base item an occurrence belongs to (task_id / medication_id)."""

    return str(
        occurrence.get("task_id")
        or occurrence.get("medication_id")
        or str(occurrence.get("occurrence_id") or "").split("#")[0]
    )


def item_name(occurrence: dict[str, Any]) -> str:
    return str(occurrence.get("name") or occurrence.get("description") or "")


# Everyday names patients use for a medicine. Used only to understand
# "my blood thinner" and to say it back; never to choose a medicine.
_EVERYDAY_NAMES = {
    "blood thinner": (
        "apixaban", "rivaroxaban", "edoxaban", "dabigatran",
        "warfarin", "enoxaparin", "dalteparin", "heparin",
    ),
}


def everyday_name(name: str) -> str | None:
    """'Apixaban' -> 'blood thinner'; None if there is no everyday name."""

    lowered = (name or "").lower()

    for everyday, medicines in _EVERYDAY_NAMES.items():
        if any(medicine in lowered for medicine in medicines):
            return everyday

    return None


def part_of_day(occurrence: dict[str, Any]) -> str | None:
    """'morning', 'afternoon', ... from the label or, failing that, the clock time."""

    label = occurrence.get("time_of_day_label")

    if label:
        return str(label).lower()

    clock = occurrence.get("clock_time")

    if not clock:
        return None

    hour = int(str(clock).split(":")[0])

    for name, start in reversed(list(SLOT_STARTS.items())):
        if hour >= start.hour:
            return name

    return "morning"


def _is_due(occurrence: dict[str, Any], now: datetime) -> bool:
    """Timed items: due within the next hour. Untimed: once their time of day has started."""

    window = DUE_WINDOW if occurrence.get("clock_time") else timedelta(0)

    return due_at(occurrence, now) <= now + window


def _has_time(occurrence: dict[str, Any]) -> bool:
    """A clock time or a time of day; False for 'any time today'."""

    return bool(occurrence.get("clock_time")) or str(occurrence.get("time_of_day_label") or "").lower() in SLOT_STARTS


def due_at(occurrence: dict[str, Any], now: datetime) -> datetime:
    """When this occurrence is due today, in the patient's local time."""

    clock = occurrence.get("clock_time")

    if clock:
        return datetime.combine(now.date(), time.fromisoformat(str(clock)), tzinfo=now.tzinfo)

    label = str(occurrence.get("time_of_day_label") or "").lower()

    if label in SLOT_STARTS:
        return datetime.combine(now.date(), SLOT_STARTS[label], tzinfo=now.tzinfo)

    # No time at all ("any time today"): due from the start of the day.
    return datetime.combine(now.date(), time(0, 0), tzinfo=now.tzinfo)


def _words(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z']+", (text or "").lower())
        if len(word) >= 4 and word not in _STOPWORDS
    }


def _matches(message_words: set[str], name: str) -> bool:
    """'walk' matches 'walking'; 'exercises' matches 'exercise'."""

    for word in _words(f"{name} {everyday_name(name) or ''}"):
        for said in message_words:
            if word.startswith(said) or said.startswith(word):
                return True

    return False


def _short_name(occurrence: dict[str, Any]) -> str:
    """What the item is called: 'knee exercises', not the whole sentence."""

    if occurrence.get("medication_id") or occurrence.get("name"):
        return item_name(occurrence)

    return short_task_name(item_name(occurrence))


def _best_named(said: set[str], matched: set[str], occurrences: list[dict[str, Any]]) -> set[str]:
    """
    Several items mention her words ("knee exercises" is in both the exercises
    and the ice-pack sentence). Keep the one whose own name matches best.
    """

    scores: dict[str, int] = {}

    for o in occurrences:
        key = item_id(o)
        if key in matched and key not in scores:
            name_words = _words(_short_name(o))
            scores[key] = sum(
                1 for word in said if any(word.startswith(n) or n.startswith(word) for n in name_words)
            )

    best = max(scores.values(), default=0)
    winners = {key for key, score in scores.items() if score == best}

    return winners if best > 0 and len(winners) == 1 else matched


def _item_occurrences(
    message: str,
    occurrences: list[dict[str, Any]],
    pending_checkin: dict[str, Any] | None,
) -> list[dict[str, Any]] | None:
    """All of today's occurrences of the one item the patient means, or None."""

    said = _words(message)
    matched = {item_id(o) for o in occurrences if said and _matches(said, item_name(o))}

    if not matched and pending_checkin:
        # "I'm back" with a reminder waiting means the reminded item.
        reminded = str(pending_checkin.get("occurrence_id") or "")
        matched = {item_id(o) for o in occurrences if o.get("occurrence_id") == reminded}

    if len(matched) > 1:
        matched = _best_named(said, matched, occurrences)

    if len(matched) != 1:
        return None

    (only,) = matched

    return sorted(
        (o for o in occurrences if item_id(o) == only),
        key=lambda o: int(o.get("occurrence_number") or 1),
    )


def _resolve_named_part(
    message: str,
    occurrences: list[dict[str, Any]],
    pending_checkin: dict[str, Any] | None,
) -> Resolution:
    """
    "I've done my morning walk": the one occurrence of that item in that part of the day.

    Resolved in code only when it is certain: one part of the day is named,
    with no clock time or "second" beside it, and the item has exactly one
    occurrence in that part. Anything else is left to the model, as before.
    """

    parts = {part.lower() for part in _NAMED_PART.findall(message or "")}
    parts = {"midday" if part == "lunchtime" else part for part in parts}

    if len(parts) != 1 or _NAMED_EXACTLY.search(message or ""):
        return Resolution("model")

    (part,) = parts
    item = [o for o in _item_occurrences(message, occurrences, pending_checkin) or [] if not o.get("as_needed")]
    in_part = [o for o in item if part_of_day(o) == part]

    if len(in_part) != 1:
        return Resolution("model")

    (occurrence,) = in_part

    if occurrence.get("status") == "completed":
        still_open = [o for o in item if o.get("status") != "completed"]
        return Resolution(
            "already_done", done=occurrence, next_up=still_open[0] if still_open else None, item_occurrences=item,
        )

    return Resolution("record", occurrence=occurrence, item_occurrences=item)


def resolve_occurrence(
    message: str,
    occurrences: list[dict[str, Any]],
    now: datetime,
    pending_checkin: dict[str, Any] | None = None,
) -> Resolution:
    """Choose the occurrence a completion report refers to (see module docstring)."""

    if names_specific_occurrence(message):
        return _resolve_named_part(message, occurrences, pending_checkin)

    if not occurrences:
        return Resolution("nothing")

    item = _item_occurrences(message, occurrences, pending_checkin)

    if item is None:
        return Resolution("model")

    # "Only if needed" medicines are never scheduled doses.
    item = [o for o in item if not o.get("as_needed")]

    if not item:
        return Resolution("model")

    pending = [o for o in item if o.get("status") != "completed"]
    completed = [o for o in item if o.get("status") == "completed"]

    # a. The reminded occurrence, if it is still open.
    if pending_checkin:
        reminded = pending_checkin.get("occurrence_id")

        for occurrence in pending:
            if occurrence.get("occurrence_id") == reminded:
                return Resolution("record", occurrence=occurrence, item_occurrences=item)

    # b. Pending and due within the next hour, earliest first.
    due_soon = sorted(
        (o for o in pending if _is_due(o, now)),
        key=lambda o: due_at(o, now),
    )

    # c. Two or more already due: genuinely ambiguous.
    already_due = [o for o in due_soon if due_at(o, now) <= now]

    if len(already_due) >= 2:
        return Resolution("ask", choices=already_due, item_occurrences=item)

    if due_soon:
        return Resolution("record", occurrence=due_soon[0], item_occurrences=item)

    later = sorted(pending, key=lambda o: due_at(o, now))

    # d. Already recorded, and the next one is not due yet.
    if completed:
        return Resolution(
            "already_done",
            done=completed[-1],
            next_up=later[0] if later else None,
            item_occurrences=item,
        )

    # Nothing done yet and nothing due: they did it early.
    if later:
        return Resolution("record", occurrence=later[0], item_occurrences=item)

    return Resolution("nothing")


def resolve_vague_medication(
    medications: list[dict[str, Any]],
    now: datetime,
    pending_checkin: dict[str, Any] | None = None,
) -> Resolution:
    """
    "I took my tablets": which medicine?

    The reminded dose wins. Otherwise, if exactly one medicine has a
    dose due now, record its earliest due dose. If two or more
    medicines are due, ask which ("your paracetamol, your blood
    thinner, or both?"). If none is due, leave it to the model.
    """

    scheduled = [
        m for m in medications
        if not m.get("as_needed") and m.get("status") != "completed"
    ]

    if pending_checkin:
        for dose in scheduled:
            if dose.get("occurrence_id") == pending_checkin.get("occurrence_id"):
                return Resolution("record", occurrence=dose)

    first_due: dict[str, dict[str, Any]] = {}

    for dose in sorted(scheduled, key=lambda d: due_at(d, now)):
        if _is_due(dose, now):
            first_due.setdefault(item_id(dose), dose)

    # A medicine with no time at all ("three times a day") counts only when no timed
    # one is due, as in the greeting (app.agent.next_up): "You need to take your
    # cetirizine this morning", then "I took my tablets" means the cetirizine.
    timed = {key: dose for key, dose in first_due.items() if _has_time(dose)}
    if timed:
        first_due = timed

    if len(first_due) == 1:
        (dose,) = first_due.values()
        return Resolution("record", occurrence=dose)

    if len(first_due) >= 2:
        return Resolution("ask", choices=list(first_due.values()))

    return Resolution("model")


def items_mentioned(text: str, occurrences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    The first still-open occurrence of each item named in `text`.

    "I haven't taken my blood thinner" -> [the next apixaban dose].
    """

    said = _words(text)
    firsts: dict[str, dict[str, Any]] = {}

    for occurrence in sorted(occurrences, key=lambda o: int(o.get("occurrence_number") or 1)):
        if occurrence.get("as_needed") or occurrence.get("status") == "completed":
            continue

        if said and _matches(said, item_name(occurrence)):
            firsts.setdefault(item_id(occurrence), occurrence)

    return list(firsts.values())
