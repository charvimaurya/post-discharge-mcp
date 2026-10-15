"""
What is next today, across tasks AND medicines.

One list of today's pending items, built from the get_today_tasks
and get_medications results, so a reply after "I'm back from my
walk" can mention the medicines that are now due, not just walks.

Rules:
- "Only if needed" medicines are never listed.
- Tasks are placed by their clock time. Medicines (and tasks with
  no clock time) are placed by their time of day; no clock time is
  invented for them. The fixed times below are for sorting only.
- An item is "due now" once its clock time or time of day has
  started, "later" before that. Items with no time at all are
  "any time" and only come up when nothing timed is left.
- Wording comes from the letter where it gives some ("after
  breakfast"); otherwise the time of day is said plainly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from app.agent.occurrence_resolver import SLOT_STARTS, everyday_name, item_id, item_name, part_of_day
from app.reminders.text import build_opening_greeting, build_return_greeting, is_or_are, short_task_name, time_to_words


# Sorting positions only (AfterWard's defaults, never spoken as times).
_SORT_TIMES = {
    "morning": time(7, 30),
    "midday": time(13, 0),
    "afternoon": time(15, 0),
    "evening": time(18, 0),
    "bedtime": time(21, 30),
}

_SLOT_WORDS = {
    "morning": "this morning",
    "midday": "at midday",
    "afternoon": "this afternoon",
    "evening": "this evening",
    "bedtime": "at bedtime",
}

_MEAL_SLOT = {"breakfast": "morning", "lunch": "midday", "dinner": "evening", "tea": "evening", "supper": "evening"}

# "Take the morning dose after breakfast" -> morning: "after breakfast".
_DOSE_MEAL = re.compile(
    r"\b(morning|midday|lunchtime|evening|night|bedtime)\s+dose\s+"
    r"((?:after|with|before)\s+(?:breakfast|lunch|dinner|tea|supper|food|a meal|your evening meal))",
    re.IGNORECASE,
)
_MEAL = re.compile(r"\b((?:after|with|before)\s+(breakfast|lunch|dinner|tea|supper))\b", re.IGNORECASE)


@dataclass
class NextItem:
    occurrence: dict[str, Any]
    is_medication: bool
    slot: str | None          # "morning", ... or None for "any time"
    status: str               # "due now", "later" or "any time"
    when: str                 # "after breakfast", "at three o'clock", "this evening", ""
    spoken: str               # "your paracetamol, 2 tablets", "your afternoon walk"
    sort_key: tuple


def letter_wording(medication: dict[str, Any]) -> dict[str, str]:
    """
    Slot -> the letter's own words for when to take it, where it says.
    Only phrases actually written in the instructions or source line.
    """

    text = " ".join(
        str(part) for part in (
            medication.get("instructions"),
            (medication.get("source") or {}).get("snippet"),
        ) if part
    )

    wording: dict[str, str] = {}

    for slot_word, phrase in _DOSE_MEAL.findall(text):
        slot = {"lunchtime": "midday", "night": "bedtime"}.get(slot_word.lower(), slot_word.lower())
        wording.setdefault(slot, phrase.lower())

    # A meal with no dose named ("Take after lunch") belongs to that meal's slot.
    for phrase, meal in _MEAL.findall(text):
        wording.setdefault(_MEAL_SLOT[meal.lower()], phrase.lower())

    if re.search(r"\bat bedtime\b", text, re.IGNORECASE):
        wording.setdefault("bedtime", "at bedtime")

    return wording


def _thing(occurrence: dict[str, Any]) -> str:
    """A short spoken name for a task: 'walk', 'knee exercises', 'ice pack on the knee'."""

    return short_task_name(item_name(occurrence))


def _spoken(occurrence: dict[str, Any], is_medication: bool, slot: str | None) -> str:
    if is_medication:
        name = everyday_name(item_name(occurrence)) or item_name(occurrence).lower()
        dose = occurrence.get("dose")
        return f"your {name}, {dose}" if dose else f"your {name}"

    thing = _thing(occurrence)

    if thing == "walk" and slot:
        return f"your {slot} walk"

    # "Keep the dressing clean and dry" is an instruction, not a thing to own.
    if _IMPERATIVE.match(thing):
        return thing

    return f"your {thing}"


_IMPERATIVE = re.compile(r"^(keep|rest|use|avoid|wear|do|take|apply|raise|elevate|check|change|drink|eat)\b")


def build_next_up(
    tasks: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    now: datetime,
) -> list[NextItem]:
    """Today's pending items, due-now first, then by time; medicines first at the same time."""

    items: list[NextItem] = []

    for is_medication, occurrences in ((False, tasks), (True, medications)):
        wording_cache: dict[str, dict[str, str]] = {}

        for o in occurrences:
            if o.get("status") == "completed" or (is_medication and o.get("as_needed")):
                continue

            clock = o.get("clock_time")
            slot = part_of_day(o)

            if clock:
                starts = time.fromisoformat(str(clock))
                sort_at = starts
                when = f"at {time_to_words(str(clock))}"
            elif slot in SLOT_STARTS:
                starts = SLOT_STARTS[slot]
                sort_at = _SORT_TIMES[slot]
                when = _SLOT_WORDS[slot]
            else:
                starts = sort_at = None
                when = ""

            if is_medication and slot:
                key = item_id(o)
                if key not in wording_cache:
                    wording_cache[key] = letter_wording(o)
                when = wording_cache[key].get(slot, when)

            if starts is None:
                status = "any time"
            elif starts <= now.time():
                status = "due now"
            else:
                status = "later"

            rank = {"due now": 0, "later": 1, "any time": 2}[status]
            minutes = sort_at.hour * 60 + sort_at.minute if sort_at else 24 * 60

            items.append(NextItem(
                occurrence=o,
                is_medication=is_medication,
                slot=slot if starts is not None else None,
                status=status,
                when=when,
                spoken=_spoken(o, is_medication, slot),
                sort_key=(rank, minutes, 0 if is_medication else 1, int(o.get("occurrence_number") or 1)),
            ))

    return sorted(items, key=lambda item: item.sort_key)


def build_steps(items: list[NextItem]) -> list[list[NextItem]]:
    """
    The day as steps, in order. Medicines due in the same time of day are
    ONE step ("your paracetamol and blood thinner, after breakfast");
    every task is its own step.
    """

    steps: list[list[NextItem]] = []

    for item in items:
        last = steps[-1][0] if steps else None
        if (
            last is not None
            and item.is_medication
            and last.is_medication
            and item.slot is not None
            and item.slot == last.slot
            and item.status == last.status
        ):
            steps[-1].append(item)
        else:
            steps.append([item])

    return steps


def step_ids(step: list[NextItem]) -> list[str]:
    return [item.occurrence.get("occurrence_id") for item in step]


def describe_for_model(items: list[NextItem]) -> str:
    """The next_up list as plain lines for the model's facts block."""

    if not items:
        return "  - nothing left today"

    return "\n".join(
        f"  - {item.status} | {item.spoken}{' ' + item.when if item.when else ''}"
        for item in items
    )


def timing(occurrence: dict[str, Any], now: datetime) -> str:
    """
    Where an item sits in the day, for /today:

        "earlier today"  its time has passed (a timed item over an hour
                         ago, or a time of day that has ended)
        "due now"        its time is now or within the next half hour,
                         or its time of day is under way
        "later"          still to come
        "any time"       no time at all

    Done items keep their timing; the screen shows them as done.
    """

    clock = occurrence.get("clock_time")
    local = now.time()

    if clock:
        due = datetime.combine(now.date(), time.fromisoformat(str(clock)), tzinfo=now.tzinfo)
        minutes = (due - now).total_seconds() / 60
        if minutes < -60:
            return "earlier today"
        return "due now" if minutes <= 30 else "later"

    slot = part_of_day(occurrence)

    if slot not in SLOT_STARTS:
        return "any time"

    order = list(SLOT_STARTS)
    starts = SLOT_STARTS[slot]
    following = order.index(slot) + 1
    ends = SLOT_STARTS[order[following]] if following < len(order) else None

    if local < starts:
        return "later"
    if ends is not None and local >= ends:
        return "earlier today"
    return "due now"


def build_opening_message(
    first_name: str | None,
    tasks: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    now: datetime,
    returning: bool = False,
) -> str:
    """Greet and name today's next eligible item, without reviving earlier items.
    returning: she was already greeted today, so "Welcome back" and her progress, not "Good morning"."""
    if returning:
        everything = [*tasks, *medications]
        done = sum(1 for item in everything if item.get("status") == "completed")
        greeting = build_return_greeting(first_name, done, len(everything))
    else:
        greeting = build_opening_greeting(first_name, now)
    def eligible(items):
        return [item for item in items
                if not item.get("needs_confirmation")
                and timing(item, now) != "earlier today"]

    items = build_next_up(eligible(tasks), eligible(medications), now)
    if not items:
        return greeting

    # A timed item inside its reminder window (30 minutes before, until its time)
    # is named first, so the greeting and the reminder never disagree.
    def minutes_until(candidate) -> float | None:
        clock = candidate.occurrence.get("clock_time")
        if not clock or candidate.is_medication:
            return None
        due = datetime.combine(now.date(), time.fromisoformat(str(clock)), tzinfo=now.tzinfo)
        return (due - now).total_seconds() / 60

    item = next((i for i in items if (m := minutes_until(i)) is not None and 0 <= m <= 30), items[0])
    schedule = f" {item.when}" if item.when else ""
    if item.is_medication:
        dose = item.occurrence.get("dose")
        medicine = item.spoken.removesuffix(f", {dose}") if dose else item.spoken
        instruction = f"{dose} of {medicine}" if dose else medicine
        message = f"{greeting} You need to take {instruction}{schedule}."
    else:
        message = f"{greeting} Next {is_or_are(item.spoken)} {item.spoken}{schedule}."
    clock = item.occurrence.get("clock_time")
    if clock and not item.is_medication:
        due = datetime.combine(now.date(), time.fromisoformat(str(clock)), tzinfo=now.tzinfo)
        minutes = (due - now).total_seconds() / 60
        if 0 < minutes <= 30:
            message += " You can start getting ready."
    return message
