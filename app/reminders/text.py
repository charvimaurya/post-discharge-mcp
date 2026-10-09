"""Deterministic spoken reminder text."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Good morning"

    if now.hour < 18:
        return "Good afternoon"

    return "Good evening"


def _time_to_words(clock_time: str) -> str:
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
        label = item.get("time_of_day_label")

        if label:
            return f"{label} walk"

        return "walk"

    if item.get("item_type") == "medication":
        return str(
            item.get("name")
            or item.get("title")
            or "medication"
        )

    return str(
        item.get("title")
        or item.get("name")
        or item.get("label")
        or "recovery activity"
    )


def build_reminder_text(
    first_name: str,
    item: dict[str, Any],
    now: datetime,
) -> str:
    """
    Build the reminder using deterministic application code.

    No LLM is involved.
    """

    clock_time = item.get("clock_time")

    if not clock_time:
        raise ValueError(
            "Cannot build timed reminder without clock_time."
        )

    description = _item_description(item)
    spoken_time = _time_to_words(clock_time)

    return (
        f"{_greeting(now)}, {first_name}. "
        f"I hope you're doing well. "
        f"You have about thirty minutes until your "
        f"{description}, at {spoken_time}."
    )