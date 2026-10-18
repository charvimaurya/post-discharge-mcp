"""Activity is distinct saved task occurrences, never a guessed schedule."""
from app.mcp.tools.week import task_activity

DAY = "2026-10-23"
DAYS = [{"date": DAY}]


def event(kind="task_completed", key="first", occurrence=f"walk#{DAY}#1", patient="patient"):
    return {"event_type": kind, "patient_id": patient, "idempotency_key": key,
            "details": {"date": DAY, "occurrence_id": occurrence, "completed_at": DAY + "T08:00:00Z"}}


def test_retries_are_one_record_and_undo_then_retake_updates_count():
    rows = [event(), event()]
    assert task_activity(rows, "patient", DAYS)[0]["completed_tasks"] == 1
    rows.append(event("task_undone", "undo"))
    assert task_activity(rows, "patient", DAYS)[0]["completed_tasks"] == 0
    rows.append(event(key="retake"))
    assert task_activity(rows, "patient", DAYS)[0]["completed_tasks"] == 1


def test_only_patient_scoped_task_occurrences_on_the_right_date_are_counted():
    rows = [event(), event(patient="other"), event("medication_taken", "medicine"),
            event(key="wrong-date", occurrence="walk#2026-10-22#1")]
    assert task_activity(rows, "patient", DAYS) == [{"date": DAY, "completed_tasks": 1}]
    assert task_activity([], "patient", DAYS) == [{"date": DAY, "completed_tasks": 0}]
