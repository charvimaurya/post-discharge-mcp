"""Test per-dose medication completion rebuilt from Event History."""

from unittest.mock import patch

import pytest

from app.database import recovery_state as service


DAY = "2026-10-23"

PARACETAMOL = {
    "id": "med_para",
    "name": "Paracetamol",
    "times_per_day": 4,
    "time_of_day": ["morning", "midday", "evening", "bedtime"],
    "as_needed": False,
    # Legacy base status must not leak into occurrences.
    "status": "completed",
}

CODEINE = {
    "id": "med_codeine",
    "name": "Codeine",
    "times_per_day": 4,
    "time_of_day": [],
    "as_needed": True,
}

STATE = {"medications": [PARACETAMOL, CODEINE]}


def _event(occurrence_id, completed_at=f"{DAY}T08:00:00+00:00"):
    return {
        "event_type": "medication_taken",
        "details": {"occurrence_id": occurrence_id, "completed_at": completed_at},
    }


def test_scheduled_doses_expand_and_prn_stays_single():
    with patch.object(service, "get_recovery_state", return_value=STATE), \
            patch.object(service, "get_events", return_value=[_event("med_para#2026-10-23#1")]):
        doses = service.get_medications("patient", DAY)

    para = [d for d in doses if d["medication_id"] == "med_para"]
    assert [d["time_of_day_label"] for d in para] == ["morning", "midday", "evening", "bedtime"]
    assert [d["status"] for d in para] == ["completed", "pending", "pending", "pending"]
    assert para[0]["completed_at"] == f"{DAY}T08:00:00+00:00"

    codeine = [d for d in doses if d["medication_id"] == "med_codeine"]
    assert len(codeine) == 1
    assert codeine[0]["occurrence_total"] == 1


def test_mark_dose_writes_event_only(monkeypatch):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T08:15:00Z")
    state = {"medications": [dict(PARACETAMOL)]}
    with patch.object(service, "get_recovery_state", return_value=state), \
            patch.object(service, "save_recovery_state") as save, \
            patch.object(service, "append_event") as append, \
            patch.object(service, "get_events", return_value=[_event("med_para#2026-10-23#1")]):
        append.return_value = {"created": True, "duplicate": False, "event": {}}
        result = service.mark_medication_taken("patient", "med_para#2026-10-23#1", DAY)

    save.assert_not_called()
    assert state["medications"][0] == PARACETAMOL
    kwargs = append.call_args.kwargs
    assert kwargs["event_type"] == "medication_taken"
    assert kwargs["idempotency_key"] == "patient#med_para#2026-10-23#1"
    assert kwargs["details"]["completed_at"] == "2026-10-23T08:15:00+00:00"
    assert result["already_completed"] is False
    assert result["medication"]["occurrence_id"] == "med_para#2026-10-23#1"
    assert result["medication"]["status"] == "completed"


def test_mark_dose_duplicate_is_already_completed():
    with patch.object(service, "get_recovery_state", return_value=STATE), \
            patch.object(service, "append_event", return_value={"created": False, "duplicate": True, "event": None}), \
            patch.object(service, "get_events", return_value=[]):
        result = service.mark_medication_taken("patient", "med_para#2026-10-23#2", DAY)
    assert result["already_completed"] is True


@pytest.mark.parametrize("occurrence_id,error", [
    ("med_para#2026-10-22#1", "scheduled for today"),
    ("med_para#2026-10-23#5", "scheduled for today"),
    # PRN medicines only have one occurrence per day.
    ("med_codeine#2026-10-23#2", "scheduled for today"),
    ("med_nope#2026-10-23#1", "scheduled for today"),
    ("med_para", "Invalid occurrence id"),
])
def test_mark_dose_rejects_invalid(occurrence_id, error):
    with patch.object(service, "get_recovery_state", return_value=STATE), \
            patch.object(service, "get_events", return_value=[]), \
            patch.object(service, "append_event") as append:
        with pytest.raises(ValueError, match=error):
            service.mark_medication_taken("patient", occurrence_id, DAY)
    append.assert_not_called()
