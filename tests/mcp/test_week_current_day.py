"""Exercise real medication writes/readers against isolated in-memory storage."""
from copy import deepcopy

import pytest

from app.auth.patient_scope import PatientContext
from app.database import recovery_state
from app.mcp.tools import week

PATIENT = "isolated_week_demo"
DAY = "2026-10-23"


@pytest.fixture
def store(monkeypatch):
    state = {"timezone": "Europe/London", "medications": [
        {"id": "a", "name": "First", "time_of_day": ["morning"], "as_needed": False},
        {"id": "b", "name": "Second", "time_of_day": ["morning"], "as_needed": False},
        {"id": "stopped", "status": "stopped", "time_of_day": ["morning"]},
        {"id": "prn", "as_needed": True, "time_of_day": []},
    ]}
    events = []
    monkeypatch.setenv("DEMO_FIXED_NOW", DAY + "T10:00:00+01:00")
    def read(patient):
        assert patient == PATIENT
        return deepcopy(state)
    def history(patient):
        assert patient == PATIENT
        return deepcopy(events)
    def append(**event):
        assert event["patient_id"] == PATIENT
        duplicate = any(row["idempotency_key"] == event["idempotency_key"] for row in events)
        if not duplicate:
            events.append(deepcopy(event))
        return {"duplicate": duplicate, "created": not duplicate}
    monkeypatch.setattr(recovery_state, "get_recovery_state", read)
    monkeypatch.setattr(recovery_state, "get_events", history)
    monkeypatch.setattr(recovery_state, "append_event", append)
    monkeypatch.setattr(week, "get_recovery_state", read)
    monkeypatch.setattr(week, "get_complete_patient_events", history)
    monkeypatch.setattr(week, "get_today_tasks_for_context", lambda context:
                        {"ok": True, "data": {"date": DAY, "tasks": []}})
    return state, events


def result():
    response = week.get_week_summary_for_context(PatientContext("test", PATIENT, "isolated"))
    assert response["ok"], response
    return response["data"]["week"]


def test_real_saves_update_today_without_inventing_previous_days(store):
    state, events = store
    original = deepcopy(state)
    assert result()["completed_days"] == 0
    recovery_state.mark_medication_taken(PATIENT, f"a#{DAY}#1", DAY)
    assert result()["days"][-1]["reason"] == "partial_completion"
    recovery_state.mark_medication_taken(PATIENT, f"b#{DAY}#1", DAY)
    saved_events = deepcopy(events)
    summary = result()
    assert summary["completed_days"] == 1
    assert summary["days"][-1]["scheduled_doses"] == 2
    assert summary["days"][-1]["taken_doses"] == 2
    assert all(day["status"] == "unknown" for day in summary["days"][:-1])
    assert result() == summary  # Repeat reads neither reset completion nor write history.
    assert events == saved_events and state == original
    recovery_state.mark_medication_taken(PATIENT, f"b#{DAY}#1", DAY)
    assert result()["completed_days"] == 1 and events == saved_events
    recovery_state.undo_completion(PATIENT, f"b#{DAY}#1", DAY)
    assert result()["completed_days"] == 0
    recovery_state.mark_medication_taken(PATIENT, f"b#{DAY}#1", DAY)
    assert result()["completed_days"] == 1


def test_incomplete_timing_never_claims_all_morning_doses_taken(store):
    state, _ = store
    state["medications"][1]["time_of_day"] = []
    recovery_state.mark_medication_taken(PATIENT, f"a#{DAY}#1", DAY)
    assert result()["days"][-1]["reason"] == "incomplete_current_schedule"
    assert result()["completed_days"] == 0


def test_no_current_morning_doses_is_neutral(store):
    state, _ = store
    for medication in state["medications"]:
        medication["status"] = "stopped"
    assert result()["days"][-1]["status"] == "no_scheduled_morning_doses"
    assert result()["completed_days"] == 0
