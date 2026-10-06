"""Check canonical extraction mapping, application-owned values, and missing evidence."""

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime

from app.ingestion.normalizer import make_id, normalize_recovery_plan, normalize_source
from app.models.recovery_model import Restriction, WarningSign


def test_canonical_fields_survive_normalization():
    source = {"document_id": "model-invented", "snippet": "Original [?text?]", "page": 2, "read_from_image": True}
    extracted = {
        "discharge_date": " 2026-09-18 ",
        "medications": [{"name": " Example ", "strength": "500 mg", "form": "tablet", "dose": "1 tablet", "site": "oral", "times_per_day": 2, "time_of_day": ["morning"], "as_needed": True, "as_needed_reason": "stated reason", "max_per_day": 3, "instructions": "with food", "duration_text": "7 days", "source": source, "status": "completed"}],
        "tasks": [{"description": " Walk ", "kind": "walk", "times_per_day": 2, "time_of_day": ["evening"], "clock_times": ["18:30"], "details": "as tolerated", "duration_text": "7 days", "source": source}],
        "appointments": [{"title": " Review ", "date": "2026-10-01", "time": "10:00", "location": "Clinic", "conflicting_dates": ["2026-10-02"], "source": source}],
        "restrictions": [{"text": " Avoid lifting ", "topic": "activity", "source": source}],
        "monitoring": [{"what": " Temperature ", "frequency_text": "twice daily", "threshold_text": "above 38.5 C", "source": source}],
        "warning_signs": [{"text": " Warning ", "action": " Call [?111?] ", "urgency": "emergency", "source": source}],
    }
    original = deepcopy(extracted)
    state = normalize_recovery_plan(extracted, "patient", "request-document")
    saved = asdict(state)
    for category in ("medications", "tasks", "appointments", "restrictions", "monitoring", "warning_signs"):
        item = saved[category][0]
        for key, value in extracted[category][0].items():
            if key not in {"source", "status"}:
                assert item[key] == (value.strip() if isinstance(value, str) else value)
        assert item["id"]
        assert item["source"] == {**source, "document_id": "request-document"}
        assert item["needs_confirmation"] is False
    assert isinstance(state.restrictions[0], Restriction)
    assert isinstance(state.warning_signs[0], WarningSign)
    assert state.medications[0].status == state.tasks[0].status == state.appointments[0].status == "pending"
    assert state.patient_id == "patient" and state.document_id == "request-document"
    assert state.discharge_date == "2026-09-18"
    assert state.ingestion_status == "processing" and state.pending_checkin is None
    assert state.timezone == "Europe/London"
    assert datetime.fromisoformat(state.last_updated).utcoffset().total_seconds() == 0
    assert extracted == original
    state.tasks[0].clock_times.append("19:00")
    assert extracted == original


def test_missing_source_and_required_text_are_not_invented():
    for source in (None, {}, {"snippet": None}, {"snippet": "  ", "page": 1}):
        assert normalize_source(source, "document") is None
    assert normalize_source({"snippet": " evidence "}, "document").snippet == "evidence"
    state = normalize_recovery_plan({
        "medications": [{"name": "Example"}, {"name": " "}],
        "tasks": [{"description": ""}], "appointments": [{"title": None}],
        "restrictions": [{"text": " "}], "monitoring": [{"what": ""}],
        "warning_signs": [{"text": "warning"}, {"action": "action"}],
    }, "patient", "document")
    med = state.medications[0]
    assert med.source is None and med.strength is None and med.times_per_day is None
    assert med.time_of_day == [] and med.as_needed is False
    assert not any((state.tasks, state.appointments, state.restrictions, state.monitoring, state.warning_signs))


def test_ids_are_stable_and_keep_components_distinct():
    assert make_id("med", " Example ", "500 mg", None) == make_id("med", "example", "500 mg", None)
    assert make_id("med", "example", "500 mg") != make_id("med", "example", "250 mg")
    assert make_id("task", "a-b", "c") != make_id("task", "a", "b-c")
