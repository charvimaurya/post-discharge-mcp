"""Deterministic synthetic history for memory-backed tests only. No AWS imports."""
from datetime import datetime, time, timedelta
import hashlib
from zoneinfo import ZoneInfo


PATIENTS = {"isolated_mcpjam_s4", "isolated_week_demo"}

# Recovery tasks recorded complete on the six days before today, oldest first. Today gets none:
# its count comes from what is really recorded in the session, so it matches the Today card.
TASK_COUNTS = (2, 3, 1, 3, 2, 0)
TASKS = (("task_walk", 1), ("task_exercises", 1), ("task_walk", 2))
# On this many days ago a second task is recorded and then undone, so it does not count.
UNDONE_OFFSET = 4
# Days ago on which both morning medicines are taken: Tuesday and Wednesday when today is
# Friday 23 October. Every other earlier day is recorded missed; today is not yet due.
TAKEN_OFFSETS = (3, 2)


def seed_week_events(patient_id, now, timezone="Europe/London", taken_offsets=TAKEN_OFFSETS):
    if patient_id not in PATIENTS or now.utcoffset() is None:
        raise ValueError("Only isolated synthetic patients and aware clocks are allowed")
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    rows = []

    def add(kind, details, suffix):
        key = f"synthetic-week#{patient_id}#{details['date']}#{suffix}#{kind}"
        rows.append({"patient_id": patient_id, "timestamp": "event#" + hashlib.sha256(key.encode()).hexdigest(),
                     "recorded_at": now.isoformat(), "event_type": kind, "details": details,
                     "idempotency_key": key, "synthetic": True})

    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        date = day.isoformat()
        common = {"date": date, "plan_version": "synthetic-week-v1"}
        occurrences = [{"occurrence_id": f"{med}#{date}#1", "period": "morning", "active": True,
                        "due_at": datetime.combine(day, time(9), zone).isoformat()} for med in ("dose_a", "dose_b")]
        add("morning_schedule_snapshot", {**common, "complete": True, "timezone": timezone,
                                          "occurrences": occurrences}, "schedule")
        if offset:
            for occurrence in occurrences:
                kind = "medication_taken" if offset in taken_offsets else "medication_missed"
                add(kind, {**common, "occurrence_id": occurrence["occurrence_id"],
                           "completed_at": occurrence["due_at"]} if kind == "medication_taken" else
                    {**common, "occurrence_id": occurrence["occurrence_id"]}, occurrence["occurrence_id"])
            # Task completions come after the day's medicine rows and use their own event types,
            # so the morning-medicine history is unchanged.
            tasks = list(TASKS[:TASK_COUNTS[6 - offset]])
            if offset == UNDONE_OFFSET:
                tasks.append(TASKS[1])
            for task, number in tasks:
                occurrence_id = f"{task}#{date}#{number}"
                completed_at = datetime.combine(day, time(10 + number), zone).isoformat()
                add("task_completed", {**common, "occurrence_id": occurrence_id, "completed_at": completed_at}, occurrence_id)
            if offset == UNDONE_OFFSET:
                undone = f"{TASKS[1][0]}#{date}#{TASKS[1][1]}"
                add("task_undone", {**common, "occurrence_id": undone}, undone)
    return rows
