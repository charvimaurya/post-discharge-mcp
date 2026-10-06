"""Shared clock so DEMO_FIXED_NOW can control what "today" means everywhere."""

import os
from datetime import datetime, timezone


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


def get_current_date() -> str:
    """Return today's date as YYYY-MM-DD using the shared clock."""

    return get_current_datetime().date().isoformat()
