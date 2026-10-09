"""Select the next recovery occurrence that needs a proactive reminder."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any


# EventBridge checks every 5 minutes rather than at patient-specific
# times, so an occurrence is eligible while it is 25-30 minutes away.
# Every check lands in that window once or twice; the second hit is
# suppressed by last_checkin_key.
REMINDER_EARLIEST_MINUTES = 30
REMINDER_LATEST_MINUTES = 25


def _parse_clock_time(clock_time: str) -> time:
    """
    Convert an occurrence clock time such as '07:30' into a time object.

    The value must already have come from the normalized recovery plan /
    occurrence generation. This function does not invent a time.
    """
    return time.fromisoformat(clock_time)


def _occurrence_due_datetime(
    occurrence: dict[str, Any],
    now: datetime,
) -> datetime | None:
    """
    Return the occurrence's due datetime for today.

    If the occurrence has no reliable clock_time, return None.

    Important:
    Phase 14 does not invent medication/task times here.
    """
    clock_time = occurrence.get("clock_time")

    if not clock_time:
        return None

    due_time = _parse_clock_time(clock_time)

    return datetime.combine(
        now.date(),
        due_time,
        tzinfo=now.tzinfo,
    )


def _is_due_for_reminder(
    occurrence: dict[str, Any],
    now: datetime,
) -> bool:
    """
    Return True when the occurrence is 25-30 minutes away.

    Example, due_at = 07:30:

        now 06:59 -> False  (31 minutes away)
        now 07:00 -> True   (30 minutes away)
        now 07:05 -> True   (25 minutes away)
        now 07:06 -> False  (24 minutes away)

    Duplicate protection is handled separately by last_checkin_key.
    """

    due_at = _occurrence_due_datetime(occurrence, now)

    if due_at is None:
        return False

    time_until_due = due_at - now

    return (
        timedelta(minutes=REMINDER_LATEST_MINUTES)
        <= time_until_due
        <= timedelta(minutes=REMINDER_EARLIEST_MINUTES)
    )


def _reminder_priority(item: dict[str, Any]) -> tuple[int, int, str]:
    """
    Deterministically choose one reminder if several things are due together.

    Priority:
      1. walks
      2. other recovery activities/tasks
      3. medications

    Within the same category, preserve occurrence ordering where possible.
    """

    item_type = item.get("item_type", "")

    display_text = " ".join(
        str(item.get(field, ""))
        for field in (
            "name",
            "title",
            "label",
            "description",
        )
    ).lower()

    if item_type == "task" and "walk" in display_text:
        category = 0
    elif item_type == "task":
        category = 1
    elif item_type == "medication":
        category = 2
    else:
        category = 3

    occurrence_number = int(item.get("occurrence_number") or 1)

    # Stable final tie-breaker.
    occurrence_id = str(item.get("occurrence_id") or "")

    return category, occurrence_number, occurrence_id


def find_due_reminder(
    tasks: list[dict[str, Any]],
    medications: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any] | None:
    """
    Return ONE occurrence that should generate a reminder now.

    This function is intentionally pure:
      - no DynamoDB
      - no Bedrock
      - no MCP
      - no Lambda-specific code

    It receives today's already-generated occurrences.

    Those occurrences are authoritative for:
      - clock_time
      - completion state
      - occurrence_id
      - confirmation status
    """

    candidates: list[dict[str, Any]] = []

    for task in tasks:
        if task.get("status") != "pending":
            continue

        if task.get("needs_confirmation") is True:
            continue

        if not _is_due_for_reminder(task, now):
            continue

        candidates.append(
            {
                **task,
                "item_type": "task",
            }
        )

    for medication in medications:
        if medication.get("status") != "pending":
            continue

        if medication.get("needs_confirmation") is True:
            continue

        # PRN / "only if needed" medications should never generate
        # proactive reminders.
        if medication.get("as_needed") is True:
            continue

        if not _is_due_for_reminder(medication, now):
            continue

        candidates.append(
            {
                **medication,
                "item_type": "medication",
            }
        )

    if not candidates:
        return None

    candidates.sort(key=_reminder_priority)

    return candidates[0]