"""Deterministic spoken reminder text."""

from __future__ import annotations

import re
from datetime import datetime, time
from typing import Any


def _greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Good morning"

    if now.hour < 18:
        return "Good afternoon"

    return "Good evening"


def _warm_line(now: datetime) -> str:
    # A statement, not a question: AfterWard does not ask about symptoms.
    if now.hour < 12:
        return "I hope you slept well."

    return "I hope you're doing well."


def build_opening_greeting(first_name: str | None, now: datetime) -> str:
    """Welcome the patient using the shared clock's local time, even on empty days."""
    name = f", {first_name}" if first_name else ""
    return f"{_greeting(now)}{name}. {_warm_line(now)}"


def is_or_are(spoken: str) -> str:
    """"Next are your knee exercises", "Next is your walk": the last word of the name decides."""
    last = spoken.split(",")[0].split()[-1].lower() if spoken.strip() else ""
    plural = last.endswith("s") and not last.endswith(("ss", "us", "is"))
    return "are" if plural else "is"


def build_return_greeting(first_name: str | None, done: int, total: int) -> str:
    """A second visit the same day: no second "I hope you slept well", and how far she has got."""
    name = f", {first_name}" if first_name else ""
    greeting = f"Welcome back{name}."
    if total and done >= total:
        return f"{greeting} You've done everything for today."
    if done:
        return f"{greeting} You've done {done} of {total} so far."
    return greeting


def _part_of_day(clock_time: str | None) -> str | None:
    """'07:30' -> 'morning'. Describes a time; never sets one."""

    if not clock_time:
        return None

    hour = int(clock_time.split(":")[0])

    if hour < 12:
        return "morning"

    if hour < 14:
        return "midday"

    if hour < 17:
        return "afternoon"

    if hour < 21:
        return "evening"

    return "bedtime"


def time_to_words(clock_time: str) -> str:
    """
    Small speech helper for demo/recovery times.

    This does not decide when something is due.
    It only converts an already-known clock time into natural speech.
    """

    hour_text, minute_text = clock_time.split(":")

    hour = int(hour_text)
    minute = int(minute_text)

    hour_12 = hour % 12 or 12

    numbers = {
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
        11: "eleven",
        12: "twelve",
    }

    if minute == 0:
        return f"{numbers[hour_12]} o'clock"

    if minute == 30:
        return f"half past {numbers[hour_12]}"

    if minute == 15:
        return f"quarter past {numbers[hour_12]}"

    if minute == 45:
        next_hour = hour_12 % 12 + 1
        return f"quarter to {numbers[next_hour]}"

    suffix = "am" if hour < 12 else "pm"

    return (
        f"{numbers[hour_12]} "
        f"{minute:02d} {suffix}"
    )


def _item_description(item: dict[str, Any]) -> str:
    """
    Produce a short patient-facing description using existing item data.
    """

    text = " ".join(
        str(item.get(field, ""))
        for field in (
            "name",
            "title",
            "label",
            "description",
        )
        if item.get(field)
    ).lower()

    if item.get("item_type") == "task" and "walk" in text:
        # Margaret's letter gives the walks clock times (07:30, 15:00)
        # but no time-of-day word, so name the part of day from the time.
        label = item.get("time_of_day_label") or _part_of_day(
            item.get("clock_time")
        )

        if label:
            return f"{label} walk"

        return "walk"

    label = item.get("time_of_day_label") or _part_of_day(item.get("clock_time"))
    prefix = f"{label} " if label else ""

    if item.get("item_type") == "medication":
        return prefix + str(item.get("name") or item.get("title") or "medication").lower()

    name = item.get("description") or item.get("title") or item.get("name") or item.get("label")

    return prefix + (short_task_name(str(name)) if name else "recovery activity")


def short_task_name(description: str) -> str:
    """
    A short spoken name for a task, from the letter's own words:
    "Knee exercises from your physiotherapy sheet" -> "knee exercises",
    "Walking: one short walk ..." -> "walk".
    """

    if "walk" in description.lower():
        return "walk"

    first = re.split(r"(?<=[.!?])\s", description.strip())[0]
    first = re.split(r":|,| from | for ", first)[0]

    return first.strip().rstrip(".").lower()


def build_reminder_text(
    first_name: str | None,
    item: dict[str, Any],
    now: datetime,
) -> str:
    """
    Build the reminder using deterministic application code.

    No LLM is involved. The greeting fits the time of day. "About
    thirty minutes" is said only when that is true; a reminder made
    at another time (forced for testing, or an item with no clock
    time) just says what is next.
    """

    opening = (
        f"{_greeting(now)}{', ' + first_name if first_name else ''}. "
        f"{_warm_line(now)} "
    )
    description = _item_description(item)
    clock_time = item.get("clock_time")

    if not clock_time:
        return f"{opening}Next is your {description}."

    spoken_time = time_to_words(clock_time)
    due = datetime.combine(now.date(), time.fromisoformat(clock_time), tzinfo=now.tzinfo)
    minutes = (due - now).total_seconds() / 60

    if 20 <= minutes <= 35:
        return (
            f"{opening}You have about thirty minutes until your "
            f"{description}, at {spoken_time}."
        )

    return f"{opening}Next is your {description}, at {spoken_time}."