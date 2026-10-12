"""
Settings for proactive check-ins, in one place.

These are AfterWard's app defaults, NOT instructions from the
discharge letter. The letter says "morning" or "evening"; these
times only decide when AfterWard asks.
"""

import os
from datetime import time


def _time(name: str, default: str) -> time:
    try:
        return time.fromisoformat(os.getenv(name, default).strip())
    except ValueError:
        return time.fromisoformat(default)


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# When each medicine time of day starts (app defaults, not from the letter).
MEDICINE_SLOT_STARTS = {
    "morning": time(8, 0),
    "midday": time(12, 30),
    "evening": time(18, 0),
    "bedtime": time(21, 30),
}

# A dose not reported this long after its time of day starts is "missed".
MISSED_DOSE_AFTER_MINUTES = 60

# The reminder for a time of day's medicines starts this long before it
# begins, and runs until the missed-dose question takes over.
MEDICINE_REMINDER_BEFORE_MINUTES = 30

# A check-in with no window of its own (a follow-on, "remind me again")
# waits this long for an answer.
UNANSWERED_CHECKIN_MINUTES = 60

# "Shall I remind you again?" waits this long, and happens at most once.
RECHECK_MINUTES = 30


def quiet_hours() -> tuple[time, time]:
    """No check-ins from start until end (wraps past midnight). Default 21:00 to 07:00."""

    return _time("QUIET_HOURS_START", "21:00"), _time("QUIET_HOURS_END", "07:00")


def max_checkins_per_day() -> int:
    return _int("MAX_CHECKINS_PER_DAY", 6)


def recent_chat_seconds() -> int:
    """No check-in if she spoke to AfterWard this recently (real elapsed time)."""

    return _int("RECENT_CHAT_SECONDS", 120)
