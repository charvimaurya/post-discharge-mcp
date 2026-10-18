"""Conservative adherence calculations and read-only/context boundaries."""
import asyncio
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.database import event_history
from app.mcp import server
from app.mcp.context import set_current_patient_context, reset_current_patient_context
from app.auth.patient_scope import PatientContext
from app.mcp.tools import week
from tests.mcp.week_seed import seed_week_events

PATIENT = "isolated_week_demo"
NOW = datetime.fromisoformat("2026-10-23T08:00:00+01:00")


def summary(events, now=NOW, timezone="Europe/London"):
    return week.calculate_week(events, PATIENT, timezone, now)


@pytest.fixture
def events():
    return seed_week_events(PATIENT, NOW)


def test_seed_five_complete_one_missed_today_not_due_and_rerun(events):
    original = deepcopy(events)
    result = summary(events)
    assert result["completed_days"] == 5
    assert [d["status"] for d in result["days"]] == ["completed"] * 5 + ["missed", "not_yet_due"]
    assert result["start_date"] == "2026-10-17" and result["end_date"] == "2026-10-23"
    assert result["synthetic_demo_history"] is True
    assert events == original == seed_week_events(PATIENT, NOW)
    assert summary(events + deepcopy(events)) == result


def test_seed_task_counts_are_kept_apart_from_morning_medicines(events):
    result = summary(events)
    activity = week.task_activity(events, PATIENT, result["days"])
    # Six seeded days, one with a recorded-then-undone task; today only counts what the session records.
    assert [a["completed_tasks"] for a in activity] == [2, 3, 1, 3, 2, 0, 0]
    medicine_only = [e for e in events if not e["event_type"].startswith("task_")]
    assert summary(medicine_only) == result
    assert week.task_activity(medicine_only, PATIENT, result["days"]) == [
        {"date": d["date"], "completed_tasks": 0} for d in result["days"]]


@pytest.mark.parametrize("timezone,now", [
    ("Europe/London", "2026-10-23T08:00:00+01:00"),
    ("Europe/London", "2026-10-26T00:30:00+00:00"),
    ("America/Los_Angeles", "2026-10-23T00:30:00+00:00"),
])
def test_seed_uses_one_seven_day_window_for_medicines_and_tasks(timezone, now):
    instant = datetime.fromisoformat(now)
    rows = seed_week_events(PATIENT, instant, timezone)
    result = summary(rows, instant, timezone)
    activity = week.task_activity(rows, PATIENT, result["days"])
    seeded_dates = {row["details"]["date"] for row in rows}
    assert [a["date"] for a in activity] == [d["date"] for d in result["days"]]
    assert seeded_dates == {d["date"] for d in result["days"]}
    assert all(row["patient_id"] == PATIENT and row["synthetic"] is True for row in rows)


def test_absence_never_means_missed(events):
    empty = summary([])
    assert all(d["status"] == "unknown" and d["scheduled_doses"] is None for d in empty["days"])
    snapshots = [e for e in events if e["event_type"] == "morning_schedule_snapshot"]
    assert summary(snapshots)["days"][0]["reason"] == "no_completion_evidence"
    actions = [e for e in events if e["event_type"] != "morning_schedule_snapshot"]
    assert all(d["status"] == "unknown" for d in summary(actions)["days"])


@pytest.mark.parametrize("mutation", ["partial", "incomplete", "ambiguous_period", "naive_due", "duplicate_dose", "no_version"])
def test_incomplete_evidence_is_unknown(events, mutation):
    day = events[0]["details"]["date"]
    if mutation == "partial":
        events.pop(1)
    elif mutation == "incomplete":
        events[0]["details"]["complete"] = False
    elif mutation == "ambiguous_period":
        events[0]["details"]["occurrences"][0]["period"] = "unspecified"
    elif mutation == "naive_due":
        events[0]["details"]["occurrences"][0]["due_at"] = day + "T09:00:00"
    elif mutation == "duplicate_dose":
        events[0]["details"]["occurrences"].append(deepcopy(events[0]["details"]["occurrences"][0]))
    else:
        del events[1]["details"]["plan_version"]
    result = summary(events)["days"][0]
    assert result["status"] == "unknown"
    if mutation == "partial":
        assert result["taken_doses"] == 1 and result["reason"] == "partial_completion"


def test_undo_and_retake_and_conflict(events):
    action = deepcopy(events[1])
    action.update(event_type="medication_undone", idempotency_key="undo-1")
    events.append(action)
    assert summary(events)["days"][0]["status"] == "unknown"
    retake = deepcopy(events[1]); retake["idempotency_key"] = "retake-1"
    events.append(retake)
    assert summary(events)["days"][0]["status"] == "completed"
    missed = deepcopy(events[1]); missed.update(event_type="medication_missed", idempotency_key="explicit-missed")
    events.append(missed)
    assert summary(events)["days"][0]["reason"] == "conflicting_or_unversioned_actions"


def test_stopped_and_empty_evidenced_schedule(events):
    for occurrence in events[0]["details"]["occurrences"]:
        occurrence["active"] = False
    first = summary(events)["days"][0]
    assert first["status"] == "no_scheduled_morning_doses"
    assert first["scheduled_doses"] == 0


def test_conflicting_snapshots_and_untrusted_synthetic_markers(events):
    conflict = deepcopy(events[0]); conflict["details"]["plan_version"] = "other"
    assert summary(events + [conflict])["days"][0]["status"] == "unknown"
    events[1]["synthetic"] = False
    assert summary(events)["synthetic_demo_history"] is False
    foreign = deepcopy(events[0]); foreign["patient_id"] = "other_patient"
    assert summary([foreign])["days"][0]["scheduled_doses"] is None
    with pytest.raises(ValueError):
        seed_week_events("demo_patient_001", NOW)


@pytest.mark.parametrize("timezone,now,expected", [
    ("Europe/London", "2026-10-26T00:30:00+00:00", "2026-10-20"),
    ("America/Los_Angeles", "2026-10-23T00:30:00+00:00", "2026-10-16"),
])
def test_local_day_boundaries_and_dst(timezone, now, expected):
    instant = datetime.fromisoformat(now)
    rows = seed_week_events(PATIENT, instant, timezone)
    result = summary(rows, instant, timezone)
    assert result["start_date"] == expected
    assert result["completed_days"] == 5
    assert len({d["date"] for d in result["days"]}) == 7
    with pytest.raises(ValueError):
        summary(rows, instant.replace(tzinfo=None), timezone)


def test_reader_paginates_strongly_and_filters_patient(monkeypatch):
    calls = []
    def query(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return {"Items": [{"patient_id": PATIENT}], "LastEvaluatedKey": {"timestamp": "key"}}
        return {"Items": [{"patient_id": "other"}, {"patient_id": PATIENT}]}
    monkeypatch.setattr(event_history, "event_table", SimpleNamespace(query=query))
    assert len(event_history.get_complete_patient_events(PATIENT)) == 2
    assert all(call["ConsistentRead"] is True for call in calls)
    assert calls[1]["ExclusiveStartKey"] == {"timestamp": "key"}
    with pytest.raises(ValueError):
        event_history.get_complete_patient_events("")


@pytest.mark.parametrize("patient_id", [PATIENT, "isolated_mcpjam_s4"])
def test_registered_tool_uses_only_context_and_no_writes(monkeypatch, events, patient_id):
    for event in events:
        event["patient_id"] = patient_id
    patients = []
    monkeypatch.setenv("DEMO_FIXED_NOW", NOW.isoformat())
    def read(patient):
        patients.append(patient)
        return events
    monkeypatch.setattr(week, "get_complete_patient_events", read)
    monkeypatch.setattr(week, "get_recovery_state", lambda patient: {"timezone": "Europe/London"})
    monkeypatch.setattr(week, "get_today_tasks_for_context", lambda context: {"ok": True, "data": {"date": "2026-10-23", "tasks": []}})
    original = deepcopy(events)
    token = set_current_patient_context(PatientContext("test", patient_id, "isolated"))
    try:
        result = asyncio.run(server.get_week_summary())
    finally:
        reset_current_patient_context(token)
    assert result["data"]["week"]["completed_days"] == 5
    assert patients == [patient_id] and events == original
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert len(tools) == 9
    assert tools["get_week_summary"].input_schema.get("properties", {}) == {}
    assert tools["get_week_summary"].meta["ui"]["resourceUri"] == "ui://afterward/today.html"
    assert tools["get_week_summary"].annotations.read_only_hint is True


def test_reader_failure_and_today_failure_are_generic(monkeypatch):
    context = PatientContext("test", PATIENT, "isolated")
    monkeypatch.setattr(week, "get_recovery_state", lambda patient: None)
    assert week.get_week_summary_for_context(context)["error"]["code"] == "WEEK_UNAVAILABLE"
    monkeypatch.setattr(week, "get_recovery_state", lambda patient: {"timezone": "Europe/London"})
    monkeypatch.setattr(week, "get_complete_patient_events", lambda patient: [])
    monkeypatch.setattr(week, "get_today_tasks_for_context", lambda context: {"ok": False})
    assert week.get_week_summary_for_context(context)["ok"] is False


def test_event_read_failure_does_not_expose_diagnostics(monkeypatch):
    monkeypatch.setattr(week, "get_recovery_state", lambda patient: {"timezone": "Europe/London"})
    def fail(patient):
        raise RuntimeError("private backend diagnostics")
    monkeypatch.setattr(week, "get_complete_patient_events", fail)
    result = week.get_week_summary_for_context(PatientContext("test", PATIENT, "isolated"))
    assert result["ok"] is False
    assert "private" not in str(result)
