"""
The one place the app asks what time it is.

CLOCK_MODE chooses the clock:

    real        (default) the current time, in the patient's time zone.
    production  the same real time; test-only hooks (such as forcing a
                reminder) are switched off.
    demo        a fixed time for recording the demo video:
                DEMO_FIXED_NOW, or Friday 23 October 2026, 07:00 if unset.

Business logic ("today", "due", "done at") uses get_current_datetime(),
get_patient_datetime() or get_current_date(). Audit timestamps that
record when something really happened (recorded_at, last_updated)
use system_now_utc(). No other module reads the system clock.
"""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Europe/London"

# The demo video's moment: one week after Margaret's discharge.
DEFAULT_DEMO_NOW = "2026-10-23T07:00:00+01:00"

CLOCK_MODES = ("real", "production", "demo")


def clock_mode() -> str:
    """'real' (default), 'production' or 'demo'. Unknown values mean 'real'."""

    mode = os.getenv("CLOCK_MODE", "").strip().lower()

    return mode if mode in CLOCK_MODES else "real"


def is_demo_clock() -> bool:
    return clock_mode() == "demo"


def allows_test_hooks() -> bool:
    """Test-only features (force a reminder now) are off in production."""

    return clock_mode() != "production"


def demo_now_text() -> str | None:
    """The fixed demo time as text in demo mode; None on the real clock."""

    if not is_demo_clock():
        return None

    return os.getenv("DEMO_FIXED_NOW", "").strip() or DEFAULT_DEMO_NOW


def system_now_utc() -> datetime:
    """The real time now, in UTC. For audit timestamps, and for the real clock."""

    return datetime.now(timezone.utc)


def parse_demo_now(value: str) -> datetime:
    """
    Parse a fixed test time such as "2026-10-23T07:00:00+01:00".

    An offset is required: without one the time is ambiguous and a
    demo could silently run an hour out. Raises ValueError.
    """

    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        raise ValueError(
            "demo_now must include a UTC offset, e.g. "
            "2026-10-23T07:00:00+01:00"
        )

    return parsed


def get_current_datetime() -> datetime:
    """'Now' for the app: the demo time in demo mode, otherwise the real time (UTC)."""

    fixed = demo_now_text()

    if fixed:
        parsed = datetime.fromisoformat(fixed.replace("Z", "+00:00"))

        # DEMO_FIXED_NOW without an offset has always meant UTC.
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    return system_now_utc()


def get_patient_datetime(
    tz_name: str = DEFAULT_TIMEZONE,
    now: datetime | None = None,
) -> datetime:
    """
    The shared clock (or a supplied test time) in the patient's time zone.

    Plan clock times such as "07:30" are local, so every "due" check
    compares against local time, never UTC.
    """

    return (now or get_current_datetime()).astimezone(ZoneInfo(tz_name or DEFAULT_TIMEZONE))


def get_current_date(tz_name: str = DEFAULT_TIMEZONE) -> str:
    """Today's date (YYYY-MM-DD) in the patient's time zone."""

    return get_patient_datetime(tz_name).date().isoformat()


def get_clock_label(
    tz_name: str = DEFAULT_TIMEZONE,
    now: datetime | None = None,
) -> str:
    """Patient-local time for display, e.g. "Friday 23 October, 07:00"."""

    local = get_patient_datetime(tz_name, now)

    return f"{local:%A} {local.day} {local:%B}, {local:%H:%M}"
