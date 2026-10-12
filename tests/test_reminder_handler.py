"""Reminder checker Lambda, with storage replaced by in-memory fakes."""

import pytest

from app.clock import get_patient_datetime
from app.database import event_history, recovery_state
from lambdas.reminder_checker import handler as module


PATIENT_ID = "demo_patient_001"

WALK = {
    "occurrence_id": "walk#2026-10-23#1",
    "title": "Short walk",
    "clock_time": "07:30",
    "occurrence_number": 1,
    "status": "pending",
    "needs_confirmation": False,
}

WALK_KEY = "2026-10-23#walk#2026-10-23#1"


@pytest.fixture
def saved(monkeypatch):
    """Fake the database reads and the check-in store."""

    store: dict[str, dict] = {}

    def fake_save(patient_id, pending_checkin, checkin_key, **rules):
        if store.get(patient_id, {}).get("last_checkin_key") == checkin_key:
            return False
        store[patient_id] = {
            "pending_checkin": pending_checkin,
            "last_checkin_key": checkin_key,
        }
        return True

    def must_not_run(*args, **kwargs):
        raise AssertionError("A reminder must not record completion or events.")

    monkeypatch.setattr(
        module,
        "get_recovery_state",
        lambda patient_id: {"first_name": "Margaret", "timezone": "Europe/London"},
    )
    monkeypatch.setattr(module, "get_today_tasks", lambda patient_id, date: [dict(WALK)])
    monkeypatch.setattr(module, "get_medications", lambda patient_id, date: [])
    monkeypatch.setattr(module, "save_pending_checkin", fake_save)
    monkeypatch.setattr(recovery_state, "mark_task_completed", must_not_run)
    monkeypatch.setattr(recovery_state, "mark_medication_taken", must_not_run)
    monkeypatch.setattr(event_history, "append_event", must_not_run)

    return store


def test_patient_datetime_converts_utc_to_bst(monkeypatch):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T06:00:00Z")

    local = get_patient_datetime("Europe/London")

    assert (local.hour, local.minute) == (7, 0)
    assert local.date().isoformat() == "2026-10-23"


def test_reminder_created_with_occurrence_key(monkeypatch, saved):
    # 06:00 UTC is 07:00 BST, thirty minutes before a 07:30 walk.
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T06:00:00Z")

    result = module.handler({"patient_id": PATIENT_ID}, None)

    assert result["created"] is True
    checkin = result["pending_checkin"]
    assert checkin["checkin_id"] == WALK_KEY
    assert checkin["occurrence_id"] == WALK["occurrence_id"]
    assert checkin["item_type"] == "task"
    assert checkin["date"] == "2026-10-23"
    assert checkin["clock_time"] == "07:30"
    assert "Margaret" in checkin["text"]


def test_correct_occurrence_is_stored(monkeypatch, saved):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T06:00:00Z")

    module.handler({"patient_id": PATIENT_ID}, None)

    assert saved[PATIENT_ID]["last_checkin_key"] == WALK_KEY
    assert saved[PATIENT_ID]["pending_checkin"]["occurrence_id"] == WALK["occurrence_id"]


def test_duplicate_is_suppressed(monkeypatch, saved):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T06:00:00Z")
    module.handler({"patient_id": PATIENT_ID}, None)

    # The next 5-minute check still finds the walk 25 minutes away.
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T06:05:00Z")
    result = module.handler({"patient_id": PATIENT_ID}, None)

    assert result == {
        "created": False,
        "reason": "already_reminded",
        "checkin_id": WALK_KEY,
    }


def test_nothing_due(monkeypatch, saved):
    # 07:00 UTC is 08:00 BST: the walk is past, not upcoming.
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T07:00:00Z")

    result = module.handler({"patient_id": PATIENT_ID}, None)

    assert result == {"created": False, "reason": "nothing_due"}
    assert saved == {}


def test_no_demo_now_uses_shared_clock(monkeypatch, saved):
    # Shared clock says 08:00 BST: nothing is upcoming.
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T07:00:00Z")

    result = module.handler({"patient_id": PATIENT_ID}, None)

    assert result == {"created": False, "reason": "nothing_due"}


def test_empty_demo_now_uses_shared_clock(monkeypatch, saved):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T06:00:00Z")

    result = module.handler({"patient_id": PATIENT_ID, "demo_now": ""}, None)

    assert result["created"] is True


def test_valid_demo_now_is_used(monkeypatch, saved):
    # The shared clock alone would find nothing due.
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T07:00:00Z")

    result = module.handler(
        {"patient_id": PATIENT_ID, "demo_now": "2026-10-23T07:00:00+01:00"},
        None,
    )

    assert result["created"] is True
    assert result["pending_checkin"]["created_at"] == "2026-10-23T07:00:00+01:00"


def test_utc_demo_now_is_converted_to_patient_time(monkeypatch, saved):
    result = module.handler(
        {"patient_id": PATIENT_ID, "demo_now": "2026-10-23T06:00:00Z"},
        None,
    )

    assert result["created"] is True
    assert result["pending_checkin"]["created_at"] == "2026-10-23T07:00:00+01:00"


@pytest.mark.parametrize(
    "demo_now",
    ["not a time", "2026-13-40T07:00:00+01:00", "2026-10-23T07:00:00"],
)
def test_invalid_demo_now_is_rejected_before_any_read(monkeypatch, saved, demo_now):
    def must_not_read(patient_id):
        raise AssertionError("Invalid demo_now must not reach the database.")

    monkeypatch.setattr(module, "get_recovery_state", must_not_read)

    result = module.handler({"patient_id": PATIENT_ID, "demo_now": demo_now}, None)

    assert result["created"] is False
    assert result["reason"] == "invalid_demo_now"
    assert result["error"]
    assert saved == {}


def test_patient_not_found(monkeypatch, saved):
    monkeypatch.setattr(module, "get_recovery_state", lambda patient_id: None)

    result = module.handler({"patient_id": PATIENT_ID}, None)

    assert result == {"created": False, "reason": "patient_not_found"}
