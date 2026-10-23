"""
Demo history for past days of the demo patient, so the weekly dashboard is not empty.

Pure: given the medicine and task occurrences the plan gives for a past day (the same
ones the app builds for that date), return the events a well-kept day would have saved:
the day's schedule snapshots, every scheduled dose taken and every task done.
scripts/seed_demo_history.py writes them manually. ensure_demo_history restores
the fixed recording fixture when the demo history tools find it missing.

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
# Every task is recorded done, so the dashboard shows these days as complete.
TASKS_LEFT_UNDONE = 0

def ensure_demo_history(patient_id: str, state: dict, events: list[dict], now: datetime) -> list[dict]:
    """Repair the recording fixture after an upload clears the previous history.

    Restricted to Margaret on the demo clock with a ready plan. Real patient
    history, today's progress and days with non-fixture actions are untouched.
    Writes use the same idempotency keys as the manual seed script, so retries
    (including interrupted seeds) cannot duplicate completions.
    """
    from app.clock import is_demo_clock

    if (patient_id != PATIENT_ID or not is_demo_clock()
            or state.get("ingestion_status") != "ready"):
        return events
    try:
        discharge = Date.fromisoformat(state.get("discharge_date") or "")
    except (ValueError, TypeError):
        return events

    from app.database import event_history, recovery_state

    changed = False
    # Same seven-day window as the history tools; recovery starts after discharge.
    first = max(discharge + timedelta(days=1), now.date() - timedelta(days=6))
    for offset in range(max((now.date() - first).days, 0)):
        day = (first + timedelta(days=offset)).isoformat()
        rows = [event for event in events if event.get("patient_id") == patient_id
                and (event.get("details") or {}).get("date") == day]
        if any(not str(event.get("idempotency_key", "")).startswith(KEY_PREFIX) for event in rows):
            continue
        marker = f"{KEY_PREFIX}{patient_id}#{day}#ready#{state.get('document_id', '')}"
        if any(event.get("idempotency_key") == marker for event in rows):
            continue
        planned = build_demo_day(day, now.date().isoformat(),
                                 recovery_state.get_medications(patient_id, day),
                                 recovery_state.get_today_tasks(patient_id, day),
                                 state.get("timezone") or "Europe/London")
        for kind, details, key in planned:
            event_history.append_event(patient_id, kind, details, key)
        # Saved last: an interrupted seed is retried rather than treated as done.
        event_history.append_event(patient_id, "demo_history_seeded",
                                   {"date": day, "document_id": state.get("document_id")}, marker)
        changed = True
    return event_history.get_complete_patient_events(patient_id) if changed else events


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
                        "period": task.get("clock_time") or task.get("time_of_day_label"),
                        "active": True, "due_at": due.isoformat()})
    add("task_schedule_snapshot", {**snapshot, "occurrences": planned}, "tasks")
    for task in planned[:max(len(planned) - TASKS_LEFT_UNDONE, 0)]:
        add("task_completed", {"occurrence_id": task["occurrence_id"], "description": task["name"],
                               "completed_at": _done(datetime.fromisoformat(task["due_at"]))}, task["occurrence_id"])
    return events
