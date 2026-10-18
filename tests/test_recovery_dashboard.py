"""Read-only day history, synthetic seeding and bridge integration; no live AWS."""
import asyncio
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from app.auth.patient_scope import PatientContext
from app.mcp.tools import recovery_day, week
from app.recovery_dashboard_seed import PATIENT, NOW, build_seed
from scripts.seed_recovery_dashboard import seed_tables
from tests.bridge_client import BridgeClient
from app import web_bridge


def details(day="2026-10-20", rows=None, state=None, patient=PATIENT, now=NOW):
    plan, events = build_seed()
    return recovery_day.build_day_details(state or plan, events if rows is None else rows, patient, day, datetime.fromisoformat(now))


def test_four_day_fixture_is_reproducible_separate_and_read_only():
    plan, events = build_seed()
    original = deepcopy((plan, events))
    expected = {"2026-10-20": ["taken", "taken"], "2026-10-21": ["taken", "missed"],
                "2026-10-22": ["taken", "unknown"], "2026-10-23": ["taken", "taken"]}
    for day, statuses in expected.items():
        result = details(day, events, plan)
        assert [m["status"] for m in result["medications"]] == statuses
        assert result["tasks"][0]["status"] == "completed"
        assert result["synthetic_demo_history"] is True
        assert result["medications"][0]["name"] == "Synthetic medicine A"
    assert (plan, events) == original == build_seed()
    assert week.calculate_week(events, PATIENT, "Europe/London", datetime.fromisoformat(NOW))["completed_days"] == 2


def test_dedup_undo_and_retake():
    _, rows = build_seed()
    assert details(rows=rows + deepcopy(rows)) == details(rows=rows)
    taken = next(e for e in rows if e["event_type"] == "medication_taken" and e["details"]["date"] == "2026-10-20")
    undo = deepcopy(taken); undo.update(event_type="medication_undone", idempotency_key="undo")
    assert details(rows=rows + [undo])["medications"][0]["status"] == "unknown"
    retake = deepcopy(taken); retake["idempotency_key"] = "retake"
    assert details(rows=rows + [undo, retake])["medications"][0]["status"] == "taken"
    task = next(e for e in rows if e["event_type"] == "task_completed")
    task_undo = deepcopy(task); task_undo.update(event_type="task_undone", idempotency_key="task-undo")
    assert details(rows=rows + [task_undo])["tasks"][0]["status"] == "unknown"


@pytest.mark.parametrize("mutation", ["missing_timestamp", "naive_timestamp", "version", "conflict", "schedule", "missing_schedule"])
def test_incomplete_evidence_never_confirms(mutation):
    _, rows = build_seed()
    first = next(e for e in rows if e["event_type"] == "medication_taken")
    if mutation in {"missing_timestamp", "naive_timestamp"}:
        first.pop("recorded_at")
        first["details"]["completed_at"] = None if mutation == "missing_timestamp" else "2026-10-20T06:45:00"
    elif mutation == "version":
        first["details"]["plan_version"] = "different"
    elif mutation == "conflict":
        extra = deepcopy(first); extra["details"]["completed_at"] = "2026-10-20T06:46:00+01:00"; rows.append(extra)
    elif mutation == "schedule":
        rows[1]["details"]["complete"] = False
    else:
        rows = [e for e in rows if "schedule_snapshot" not in e["event_type"]]
    result = details(rows=rows)
    assert not result["medications"] or result["medications"][0]["status"] == "unknown"


def test_prn_stopped_empty_schedule_and_not_yet_due():
    _, rows = build_seed()
    for event in rows:
        if event["event_type"] == "medication_schedule_snapshot":
            event["details"]["occurrences"][0]["as_needed"] = True
            event["details"]["occurrences"][1]["active"] = False
    assert details(rows=rows)["medications"] == []
    _, rows = build_seed()
    rows = [e for e in rows if e["event_type"] != "medication_taken"]
    assert all(m["status"] == "not_yet_due" for m in details("2026-10-23", rows=rows,
        now="2026-10-23T06:00:00+01:00")["medications"])


def test_missing_history_does_not_expand_current_plan_backwards():
    result = details("2026-10-19", [])
    assert result["medications"] == [] and result["schedule_evidence"] == "missing_or_conflicting"
    assert details(patient="other")["medications"] == []
    plan, rows = build_seed()
    rows[0]["synthetic"] = False
    assert details(rows=rows)["synthetic_demo_history"] is False
    for event in rows: event["patient_id"] = "other"
    assert details(rows=rows, patient="other")["synthetic_demo_history"] is False


@pytest.mark.parametrize("day", ["2026-10-16", "2026-10-24", "2026-02-30", "20261020"])
def test_date_window_and_invalid_days(day):
    with pytest.raises(ValueError): details(day)


def test_patient_local_boundary():
    # 23:30 UTC on the 22nd is the 23rd in London.
    assert details("2026-10-23", now="2026-10-22T23:30:00+00:00")["date"] == "2026-10-23"
    with pytest.raises(ValueError): details("2026-10-23", now="2026-10-22T22:30:00+00:00")


def test_tool_context_registration_and_no_patient_arguments(monkeypatch):
    from app.mcp import server
    from app.mcp.context import set_current_patient_context, reset_current_patient_context
    plan, rows = build_seed()
    reads = []
    monkeypatch.setattr(recovery_day, "get_recovery_state", lambda patient: reads.append(patient) or plan)
    monkeypatch.setattr(recovery_day, "get_complete_patient_events", lambda patient: reads.append(patient) or rows)
    monkeypatch.setenv("DEMO_FIXED_NOW", NOW)
    token = set_current_patient_context(PatientContext("test", PATIENT, "test"))
    try: result = asyncio.run(server.get_recovery_day_details("2026-10-20"))
    finally: reset_current_patient_context(token)
    assert result["ok"] and reads == [PATIENT, PATIENT]
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert len(tools) == 9
    assert set(tools["get_recovery_day_details"].input_schema["properties"]) == {"date"}
    assert tools["get_recovery_day_details"].annotations.read_only_hint is True


def test_bridge_forwards_only_date_and_requires_auth(monkeypatch):
    calls = []
    from app.mcp.results import success_result
    async def tool(name, args):
        calls.append((name, args))
        return SimpleNamespace(structured_content=success_result(data=details(args["date"]), message="Checked"), content=[])
    monkeypatch.setattr(web_bridge, "call_mcp_tool", tool)
    client = BridgeClient(web_bridge.app)
    response = client.get("/recovery-day?date=2026-10-20")
    assert response.status_code == 200 and response.json()["medications"][0]["status"] == "taken"
    assert response.headers["cache-control"] == "no-store"
    for query in ["date=2026-10-20&patient_id=other", "date=2026-10-20&date=2026-10-21", "date=2026-02-30", ""]:
        assert client.get("/recovery-day?" + query).status_code == 400
    assert len(calls) == 1
    from starlette.testclient import TestClient
    assert TestClient(web_bridge.app).get("/recovery-day?date=2026-10-20").status_code == 401


class MemoryTable:
    def __init__(self): self.items = {}; self.puts = 0
    def get_item(self, *, Key, ConsistentRead):
        assert ConsistentRead
        return {"Item": deepcopy(self.items.get(tuple(Key.values())))} if tuple(Key.values()) in self.items else {}
    def query(self, **kwargs): return {"Items": deepcopy(list(self.items.values()))}
    def put_item(self, *, Item, ConditionExpression):
        assert Item["patient_id"] == PATIENT and ConditionExpression
        key = (PATIENT, Item["timestamp"]) if "timestamp" in Item else (PATIENT,)
        if key in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[key] = deepcopy(Item); self.puts += 1


def test_seed_is_conditional_idempotent_and_refuses_other_records():
    state, events = MemoryTable(), MemoryTable()
    count = seed_tables(state, events)
    original = deepcopy((state.items, events.items))
    assert seed_tables(state, events) == count
    assert (state.items, events.items) == original
    assert state.puts == 1 and events.puts == count
    state.items[(PATIENT,)]["synthetic"] = False
    with pytest.raises(ValueError): seed_tables(state, events)
    state.items[(PATIENT,)]["synthetic"] = True
    next(iter(events.items.values()))["synthetic"] = False
    with pytest.raises(ValueError): seed_tables(state, events)


def test_isolated_dashboard_bridge_integrates_real_tools_and_readers_without_aws(monkeypatch):
    from contextlib import ExitStack
    from scripts.run_recovery_dashboard_demo import build_app
    from botocore.client import BaseClient
    from starlette.testclient import TestClient
    from tests.bridge_client import BRIDGE_TEST_KEY
    monkeypatch.setattr(BaseClient, "_make_api_call", lambda *a, **k: pytest.fail("No AWS calls allowed"))
    monkeypatch.setenv("DEMO_FIXED_NOW", NOW)
    plan, rows = build_seed()
    original = deepcopy((plan, rows))
    patients = []
    def read_plan(patient):
        patients.append(patient)
        assert patient == PATIENT
        return deepcopy(plan)
    def read_events(patient):
        patients.append(patient)
        assert patient == PATIENT
        return deepcopy(rows)
    with ExitStack() as stack:
        client = TestClient(build_app(stack, read_plan, read_events))
        assert client.get("/recovery-day?date=2026-10-20").status_code == 401
        headers = {"X-Bridge-Key": BRIDGE_TEST_KEY}
        weekly = client.get("/week-summary", headers=headers)
        assert weekly.status_code == 200
        assert weekly.json()["week"]["completed_days"] == 2
        for day, expected in [("2026-10-20", "taken"), ("2026-10-21", "missed"), ("2026-10-22", "unknown")]:
            response = client.get("/recovery-day?date=" + day, headers=headers)
            assert response.status_code == 200
            assert response.json()["medications"][1]["status"] == expected
        assert client.post("/reset", headers=headers).status_code == 404
        assert client.post("/tasks/complete", headers=headers).status_code == 404
    assert (plan, rows) == original
    assert patients and set(patients) == {PATIENT}


def test_current_day_uses_saved_actions_and_explicit_timestamp(monkeypatch):
    plan, rows = build_seed()
    rows = [e for e in rows if "schedule_snapshot" not in e["event_type"]]
    plan["current_medications"] = [{**plan["medications"][0], "occurrence_id": "demo_medicine_a#2026-10-23#1",
                                    "time_of_day_label": "morning"}]
    result = details("2026-10-23", rows, plan)
    assert result["schedule_evidence"] == "current_day_occurrences"
    assert result["medications"][0]["status"] == "taken"
    assert result["medications"][0]["recorded_at"]
    with pytest.raises(ValueError): details(now="2026-10-23T07:00:00")


def test_weekly_confirmation_requires_timestamps_and_excludes_prn():
    _, rows = build_seed()
    now = datetime.fromisoformat(NOW)
    first = next(e for e in rows if e["event_type"] == "medication_taken")
    first.pop("recorded_at")
    first["details"].pop("completed_at")
    assert week.calculate_week(rows, PATIENT, "Europe/London", now)["days"][3]["status"] == "unknown"
    for event in rows:
        if event["event_type"] == "morning_schedule_snapshot" and event["details"]["date"] == "2026-10-20":
            event["details"]["occurrences"][0]["as_needed"] = True
    assert week.calculate_week(rows, PATIENT, "Europe/London", now)["days"][3]["status"] == "completed"
