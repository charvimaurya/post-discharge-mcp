"""
Demo history for past days of the demo patient, so the weekly dashboard is not empty.

Pure: given the medicine and task occurrences the plan gives for a past day (the same
ones the app builds for that date), return the events a well-kept day would have saved:
the day's schedule snapshots, every scheduled dose taken and most tasks done.
scripts/seed_demo_history.py writes them; nothing here touches AWS.

Every idempotency key starts with KEY_PREFIX, so the seeded events can be found and
removed again. Today and later days are refused: today's history is only what is
really recorded.
"""

from datetime import date as Date, datetime, time, timedelta
from zoneinfo import ZoneInfo

PATIENT_ID = "demo_patient_001"
PLAN_VERSION = "demo-history-v1"
KEY_PREFIX = "demo-history#"

# When each part of the day is due, and when the dose or task is recorded done.
PERIOD_TIMES = {"morning": time(8), "midday": time(12), "afternoon": time(15),
                "evening": time(18), "night": time(21), "bedtime": time(22)}
DEFAULT_TIME = time(12)
DONE_AFTER = timedelta(minutes=10)
# The day's last task is left undone: a believable day, not a perfect one.
TASKS_LEFT_UNDONE = 1


def _due(day: str, clock: str | None, period: str | None, zone: ZoneInfo) -> datetime:
    if clock:
        hour, minute = (int(part) for part in clock.split(":"))
        at = time(hour, minute)
    else:
        at = PERIOD_TIMES.get((period or "").lower(), DEFAULT_TIME)
    return datetime.combine(Date.fromisoformat(day), at, zone)


def _done(due: datetime) -> str:
    return (due + DONE_AFTER).isoformat()


def build_demo_day(day: str, today: str, medications: list[dict], tasks: list[dict],
                   timezone: str = "Europe/London") -> list[tuple[str, dict, str]]:
    """[(event_type, details, idempotency_key)] for one past day."""

    if Date.fromisoformat(day) >= Date.fromisoformat(today):
        raise ValueError("Demo history is only for days before today")

    zone = ZoneInfo(timezone)
    events: list[tuple[str, dict, str]] = []
    common = {"date": day, "plan_version": PLAN_VERSION}

    def add(kind: str, details: dict, suffix: str) -> None:
        events.append((kind, {**common, **details}, f"{KEY_PREFIX}{PATIENT_ID}#{day}#{kind}#{suffix}"))

    doses = []
    for med in medications:
        key = med.get("occurrence_id")
        # As-needed medicines have no schedule, so they are never "due" or "taken" here.
        if med.get("as_needed") or not isinstance(key, str) or key.rsplit("#", 2)[-2:-1] != [day]:
            continue
        period = med.get("time_of_day_label")
        due = _due(day, None, period, zone)
        doses.append({"occurrence_id": key, "name": med.get("name"), "dose": med.get("dose"),
                      "period": period, "active": True, "as_needed": False, "due_at": due.isoformat()})

    snapshot = {"complete": True, "timezone": timezone}
    add("medication_schedule_snapshot", {**snapshot, "occurrences": doses}, "all-medicines")
    add("morning_schedule_snapshot", {**snapshot, "occurrences": [d for d in doses if d["period"] == "morning"]}, "morning")
    for dose in doses:
        add("medication_taken", {"occurrence_id": dose["occurrence_id"],
                                 "completed_at": _done(datetime.fromisoformat(dose["due_at"]))}, dose["occurrence_id"])

    planned = []
    for task in tasks:
        key = task.get("occurrence_id")
        if not isinstance(key, str) or key.rsplit("#", 2)[-2:-1] != [day]:
            continue
        due = _due(day, task.get("clock_time"), task.get("time_of_day_label"), zone)
        planned.append({"occurrence_id": key, "name": task.get("description") or task.get("title"),
                        "active": True, "due_at": due.isoformat()})
    add("task_schedule_snapshot", {**snapshot, "occurrences": planned}, "tasks")
    for task in planned[:max(len(planned) - TASKS_LEFT_UNDONE, 0)]:
        add("task_completed", {"occurrence_id": task["occurrence_id"], "description": task["name"],
                               "completed_at": _done(datetime.fromisoformat(task["due_at"]))}, task["occurrence_id"])
    return events
