"""
Deterministic reminder text.

Reminder wording is generated in code, not by the LLM.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any


def _display_name(item: dict[str, Any]) -> str:
    for key in (
        "display_name",
        "title",
        "name",
        "task_name",
        "medication_name",
        "label",
    ):
        value = item.get(key)
        if value:
            return str(value)

    return "recovery item"


def _greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Good morning"

    if now.hour < 18:
        return "Good afternoon"

    return "Good evening"


def _warm_line(now: datetime) -> str:
    if now.hour < 12:
        return "I hope you slept well."

    if now.hour < 18:
        return "I hope your day is going well."

    return "I hope your evening is going well."


def _number_word(number: int) -> str:
    words = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        10: "ten",
        15: "fifteen",
        20: "twenty",
        25: "twenty-five",
        30: "thirty",
        35: "thirty-five",
        40: "forty",
        45: "forty-five",
        50: "fifty",
        55: "fifty-five",
        60: "sixty",
    }

    return words.get(number, str(number))


def _time_to_words(clock_time: str) -> str:
    """
    Convert a 24-hour clock value into natural speech.

    Examples:
        07:30 -> half past seven
        09:15 -> quarter past nine
        14:45 -> quarter to three
        15:00 -> three o'clock
    """
    parsed = None

    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(clock_time, fmt)
            break
        except ValueError:
            continue

    if parsed is None:
        return clock_time

    hour = parsed.hour
    minute = parsed.minute

    def spoken_hour(value: int) -> str:
        value = value % 12

        if value == 0:
            value = 12

        names = {
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

        return names[value]

    if minute == 0:
        return f"{spoken_hour(hour)} o'clock"

    if minute == 15:
        return f"quarter past {spoken_hour(hour)}"

    if minute == 30:
        return f"half past {spoken_hour(hour)}"

    if minute == 45:
        return f"quarter to {spoken_hour(hour + 1)}"

    if minute < 30:
        return (
            f"{_number_word(minute)} minutes past "
            f"{spoken_hour(hour)}"
        )

    minutes_to_next = 60 - minute

    return (
        f"{_number_word(minutes_to_next)} minutes to "
        f"{spoken_hour(hour + 1)}"
    )


def build_reminder_text(
    first_name: str,
    item: dict[str, Any],
    now: datetime,
) -> str:
    """
    Build the exact reminder spoken by AfterWard.
    """
    clock_time = item.get("clock_time")

    if not clock_time:
        raise ValueError(
            "Cannot build a proactive reminder without clock_time."
        )

    name = _display_name(item)

    # Make Margaret's "walk" wording natural while remaining generic.
    lowered_name = name.lower()

    if "walk" in lowered_name:
        description = "your walk"
    elif item.get("item_type") == "medication":
        description = f"your {name}"
    else:
        description = f"your {name}"

    greeting = _greeting(now)
    warm_line = _warm_line(now)
    spoken_time = _time_to_words(clock_time)

    return (
        f"{greeting}, {first_name}. "
        f"{warm_line} "
        f"You have about thirty minutes until "
        f"{description}, at {spoken_time}."
    )