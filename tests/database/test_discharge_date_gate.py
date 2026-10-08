"""Occurrences are only generated from the discharge date onwards."""

from unittest.mock import patch

import pytest

from app.database import recovery_state as service


DISCHARGE = "2026-10-16"

STATE = {
    "discharge_date": DISCHARGE,
    "tasks": [
        {"id": "task_walk", "times_per_day": 2, "clock_times": ["07:30", "15:00"], "time_of_day": []},
    ],
    "medications": [
        {"id": "med_a", "times_per_day": 2, "time_of_day": ["morning", "evening"], "as_needed": False},
    ],
}


def _read(reader, state, day):
    with patch.object(service, "get_recovery_state", return_value=state), \
            patch.object(service, "get_events", return_value=[]) as events:
        return getattr(service, reader)("patient", day), events


@pytest.mark.parametrize("reader", ["get_today_tasks", "get_medications"])
def test_before_discharge_returns_nothing(reader):
    result, events = _read(reader, STATE, "2026-10-15")
    assert result == []
    # No occurrences are built, so Event History is not read.
    events.assert_not_called()


@pytest.mark.parametrize("reader", ["get_today_tasks", "get_medications"])
@pytest.mark.parametrize("day", [DISCHARGE, "2026-10-17", "2026-11-30"])
def test_on_and_after_discharge_builds_occurrences(reader, day):
    item_id = "task_walk" if reader == "get_today_tasks" else "med_a"
    result, _ = _read(reader, STATE, day)
    assert [item["occurrence_id"] for item in result] == [
        f"{item_id}#{day}#1",
        f"{item_id}#{day}#2",
    ]
    assert all(item["status"] == "pending" for item in result)


@pytest.mark.parametrize("reader", ["get_today_tasks", "get_medications"])
@pytest.mark.parametrize("discharge", [None, "", "not-a-date"])
def test_missing_or_invalid_discharge_date_keeps_existing_behaviour(reader, discharge):
    state = dict(STATE, discharge_date=discharge)
    result, _ = _read(reader, state, "2020-01-01")
    assert len(result) == 2


def test_discharge_timestamp_is_compared_by_date():
    state = dict(STATE, discharge_date="2026-10-16T14:30:00+00:00")
    assert _read("get_today_tasks", state, "2026-10-15")[0] == []
    assert len(_read("get_today_tasks", state, "2026-10-16")[0]) == 2


# -------------------------------------------------------------
# Writes follow the same rule: an occurrence must be due today.
# -------------------------------------------------------------

WRITERS = [
    ("mark_task_completed", "task_walk", "task"),
    ("mark_medication_taken", "med_a", "medication"),
]


class _EventStore:
    """In-memory Event History honouring idempotency keys."""

    def __init__(self):
        self.events = {}

    def append(self, *, patient_id, event_type, details, idempotency_key):
        if idempotency_key in self.events:
            return {"created": False, "duplicate": True, "event": None}
        event = {"event_type": event_type, "details": details}
        self.events[idempotency_key] = event
        return {"created": True, "duplicate": False, "event": event}

    def list(self, patient_id):
        return list(self.events.values())


def _write(writer, occurrence_id, today, store):
    with patch.object(service, "get_recovery_state", return_value=STATE), \
            patch.object(service, "get_events", side_effect=store.list), \
            patch.object(service, "append_event", side_effect=store.append), \
            patch.object(service, "save_recovery_state") as save:
        result = getattr(service, writer)("patient", occurrence_id, today)
    save.assert_not_called()
    return result


@pytest.mark.parametrize("writer,item_id,_", WRITERS)
def test_forged_write_before_discharge_is_rejected(writer, item_id, _):
    store = _EventStore()
    day = "2026-10-08"
    with pytest.raises(ValueError, match="scheduled for today"):
        _write(writer, f"{item_id}#{day}#1", day, store)
    assert store.events == {}


@pytest.mark.parametrize("writer,item_id,result_key", WRITERS)
@pytest.mark.parametrize("day", [DISCHARGE, "2026-10-20"])
def test_valid_write_on_or_after_discharge_is_idempotent(writer, item_id, result_key, day):
    store = _EventStore()

    first = _write(writer, f"{item_id}#{day}#1", day, store)
    assert first["already_completed"] is False
    assert first[result_key]["status"] == "completed"

    repeat = _write(writer, f"{item_id}#{day}#1", day, store)
    assert repeat["already_completed"] is True
    assert len(store.events) == 1

    # The other occurrence that day stays independent.
    second = _write(writer, f"{item_id}#{day}#2", day, store)
    assert second["already_completed"] is False
    assert len(store.events) == 2
