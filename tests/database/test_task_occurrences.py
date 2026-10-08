"""Test per-occurrence task completion rebuilt from Event History."""

from unittest.mock import patch

import pytest

from app.database import recovery_state as service


DAY = "2026-10-23"

WALK = {
    "id": "task_walk",
    "description": "Walk twice daily",
    "times_per_day": 2,
    "clock_times": ["07:30", "15:00"],
    "time_of_day": [],
    # Legacy base status must not leak into occurrences.
    "status": "completed",
}


def _event(occurrence_id, date=DAY):
    return {
        "event_type": "task_completed",
        "details": {
            "occurrence_id": occurrence_id,
            "date": date,
            "completed_at": f"{date}T08:00:00+00:00",
        },
    }


def test_occurrence_id_round_trip():
    occurrence_id = service.build_occurrence_id("task_walk", DAY, 2)
    assert occurrence_id == "task_walk#2026-10-23#2"
    assert service.parse_occurrence_id(occurrence_id) == ("task_walk", DAY, 2)


@pytest.mark.parametrize("bad", ["task_walk", "task_walk#2026-10-23#x", "task_walk#2026-10-23#0", ""])
def test_parse_occurrence_id_rejects_bad_ids(bad):
    with pytest.raises(ValueError):
        service.parse_occurrence_id(bad)


def test_only_completed_occurrence_is_marked():
    events = [
        _event("task_walk#2026-10-23#1"),
        # Another day and legacy events without occurrence_id are ignored.
        _event("task_walk#2026-10-22#2", date="2026-10-22"),
        {"event_type": "task_completed", "details": {"task_id": "task_walk"}},
    ]
    with patch.object(service, "get_recovery_state", return_value={"tasks": [WALK]}), \
            patch.object(service, "get_events", return_value=events):
        first, second = service.get_today_tasks("patient", DAY)

    assert (first["occurrence_number"], first["occurrence_total"], first["clock_time"]) == (1, 2, "07:30")
    assert first["status"] == "completed"
    assert first["completed_at"] == "2026-10-23T08:00:00+00:00"
    assert (second["occurrence_number"], second["clock_time"], second["status"]) == (2, "15:00", "pending")
    assert "completed_at" not in second
    assert first["id"] == first["task_id"] == "task_walk"


def test_mark_occurrence_writes_event_only():
    state = {"tasks": [dict(WALK)]}
    with patch.object(service, "get_recovery_state", return_value=state), \
            patch.object(service, "save_recovery_state") as save, \
            patch.object(service, "append_event") as append, \
            patch.object(service, "get_events", return_value=[_event("task_walk#2026-10-23#1")]):
        append.return_value = {"created": True, "duplicate": False, "event": {"id": "e"}}
        result = service.mark_task_completed("patient", "task_walk#2026-10-23#1", DAY)

    save.assert_not_called()
    assert state["tasks"][0] == WALK
    kwargs = append.call_args.kwargs
    assert kwargs["idempotency_key"] == "patient#task_walk#2026-10-23#1"
    assert kwargs["details"]["occurrence_id"] == "task_walk#2026-10-23#1"
    assert kwargs["details"]["date"] == DAY
    assert result["already_completed"] is False
    # The returned task is the rebuilt occurrence, now completed.
    assert result["task"]["occurrence_id"] == "task_walk#2026-10-23#1"
    assert result["task"]["status"] == "completed"


def test_mark_occurrence_duplicate_is_already_completed():
    with patch.object(service, "get_recovery_state", return_value={"tasks": [WALK]}), \
            patch.object(service, "append_event", return_value={"created": False, "duplicate": True, "event": None}), \
            patch.object(service, "get_events", return_value=[]):
        result = service.mark_task_completed("patient", "task_walk#2026-10-23#2", DAY)
    assert result["already_completed"] is True


@pytest.mark.parametrize("occurrence_id,error", [
    ("task_walk#2026-10-22#1", "scheduled for today"),
    ("task_walk#2026-10-23#3", "scheduled for today"),
    ("task_nope#2026-10-23#1", "scheduled for today"),
    ("task_walk", "Invalid occurrence id"),
])
def test_mark_occurrence_rejects_invalid(occurrence_id, error):
    with patch.object(service, "get_recovery_state", return_value={"tasks": [WALK]}), \
            patch.object(service, "get_events", return_value=[]), \
            patch.object(service, "append_event") as append:
        with pytest.raises(ValueError, match=error):
            service.mark_task_completed("patient", occurrence_id, DAY)
    append.assert_not_called()


def test_completed_at_uses_demo_clock(monkeypatch):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T08:15:00Z")
    with patch.object(service, "get_recovery_state", return_value={"tasks": [WALK]}), \
            patch.object(service, "get_events", return_value=[]), \
            patch.object(service, "append_event") as append:
        append.return_value = {"created": True, "duplicate": False, "event": {}}
        service.mark_task_completed("patient", "task_walk#2026-10-23#1", DAY)
    assert append.call_args.kwargs["details"]["completed_at"] == "2026-10-23T08:15:00+00:00"


def test_legacy_event_without_completed_at_uses_recorded_at():
    legacy = {
        "event_type": "task_completed",
        "recorded_at": "2026-10-23T09:00:00+00:00",
        "details": {"occurrence_id": "task_walk#2026-10-23#1", "date": DAY},
    }
    with patch.object(service, "get_recovery_state", return_value={"tasks": [WALK]}), \
            patch.object(service, "get_events", return_value=[legacy]):
        first, _ = service.get_today_tasks("patient", DAY)
    assert first["completed_at"] == "2026-10-23T09:00:00+00:00"
