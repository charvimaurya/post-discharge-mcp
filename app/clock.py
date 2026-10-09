"""Shared clock so DEMO_FIXED_NOW can control what "today" means everywhere."""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def get_current_datetime() -> datetime:
    """
    Return the current UTC time, or DEMO_FIXED_NOW when it is set.

    DEMO_FIXED_NOW is an ISO 8601 timestamp such as
    "2026-10-04T09:00:00Z".
    """

    fixed_now = os.getenv("DEMO_FIXED_NOW", "").strip()

    if fixed_now:
        parsed = datetime.fromisoformat(
            fixed_now.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed

    return datetime.now(timezone.utc)


def parse_demo_now(value: str) -> datetime:
    """
    Parse a manual test timestamp such as "2026-10-23T07:00:00+01:00".

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


def get_patient_datetime(
    tz_name: str = "Europe/London",
    now: datetime | None = None,
) -> datetime:
    """
    Return the shared clock (or a supplied test time) in the
    patient's local timezone.

    Plan clock times such as "07:30" are local, so reminder
    checks must compare them against local time, not UTC.
    """

    return (now or get_current_datetime()).astimezone(ZoneInfo(tz_name))


def get_clock_label(
    tz_name: str = "Europe/London",
    now: datetime | None = None,
) -> str:
    """Patient-local time for display, e.g. "Friday 23 October, 07:00"."""

    local = get_patient_datetime(tz_name, now)

    return f"{local:%A} {local.day} {local:%B}, {local:%H:%M}"


def get_current_date() -> str:
    """Return today's date as YYYY-MM-DD using the shared clock."""

    return get_current_datetime().date().isoformat()
