"""POST /reset: the "Reset demo" button. Protected by X-Bridge-Key; demo patient only."""

import pytest
from starlette.testclient import TestClient

from app import demo_reset, web_bridge


KEY = "test-bridge-key-for-reset-tests-only"
COUNTS = {"events_deleted": 3, "tasks_reset": 5, "medications_reset": 4}


@pytest.fixture
def calls(monkeypatch):
    seen = {"resets": 0, "cleared": []}

    def fake_reset():
        seen["resets"] += 1
        return dict(COUNTS)

    monkeypatch.setenv("BRIDGE_KEY", KEY)
    monkeypatch.setenv("CLOCK_MODE", "demo")
    monkeypatch.setattr(web_bridge, "reset_demo_patient", fake_reset)
    monkeypatch.setattr(web_bridge, "clear_session", seen["cleared"].append)
    return seen


def post(body=None, key=KEY):
    headers = {"X-Bridge-Key": key} if key is not None else {}
    return TestClient(web_bridge.app).post("/reset", json=body, headers=headers)


def test_right_key_resets_the_demo_patient_and_clears_only_that_session(calls):
    response = post({"session_id": "demo-abc", "patient_id": "someone_else"})

    assert response.status_code == 200
    assert response.json() == COUNTS
    assert response.headers["cache-control"] == "no-store"
    assert calls["resets"] == 1
    assert calls["cleared"] == ["demo-abc"]


def test_reset_without_a_session_id_clears_no_session(calls):
    assert post({}).status_code == 200
    assert calls["resets"] == 1
    assert calls["cleared"] == []


@pytest.mark.parametrize("key", [None, "", "wrong-key"])
def test_missing_or_wrong_key_is_refused_and_nothing_is_reset(calls, key):
    response = post({"session_id": "demo-abc"}, key=key)

    assert response.status_code == 401
    assert calls["resets"] == 0
    assert calls["cleared"] == []


def test_refused_when_bridge_key_is_not_set(calls, monkeypatch):
    monkeypatch.delenv("BRIDGE_KEY")

    response = post({"session_id": "demo-abc"}, key="anything")

    assert response.status_code == 503
    assert calls["resets"] == 0


def test_refused_in_production(calls, monkeypatch):
    monkeypatch.setenv("CLOCK_MODE", "production")

    assert post({"session_id": "demo-abc"}).status_code == 403
    assert calls["resets"] == 0


def test_no_plan_gives_a_plain_conflict(calls, monkeypatch):
    def no_plan():
        raise demo_reset.NoPlanToReset("nothing")

    monkeypatch.setattr(web_bridge, "reset_demo_patient", no_plan)

    response = post({"session_id": "demo-abc"})

    assert response.status_code == 409
    assert response.json() == {"error": "No plan to reset. Upload a letter first."}
    assert calls["cleared"] == []


def test_a_failed_reset_reports_failure_without_details(calls, monkeypatch):
    def broken():
        raise RuntimeError("table secret-name not found")

    monkeypatch.setattr(web_bridge, "reset_demo_patient", broken)

    response = post({"session_id": "demo-abc"})

    assert response.status_code == 502
    assert "secret-name" not in response.text
    assert calls["cleared"] == []


def test_reset_is_post_only():
    from tests.bridge_client import BridgeClient
    assert BridgeClient(web_bridge.app).get("/reset").status_code == 405


def test_shared_reset_clears_the_pending_checkin_and_keeps_the_plan(monkeypatch):
    record = {
        "patient_id": demo_reset.PATIENT_ID,
        "timezone": "Europe/London",
        "first_name": "Margaret",
        "document_id": "doc_keep",
        "tasks": [{"task_id": "task_walk", "status": "completed", "completed_at": "x"}],
        "medications": [{"medication_id": "med_para", "status": "completed", "completed_at": "x"}],
        "appointments": [{"appointment_id": "appt_1"}],
        "pending_checkin": {"checkin_id": "walk#2026-10-23#1"},
        "last_checkin_key": "walk#2026-10-23#1",
        "scheduled_checkins": [{"checkin_id": "later"}],
    }
    saved = []

    class Table:
        def batch_writer(self): return self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def query(self, **kwargs): return {"Items": []}
        def delete_item(self, Key): raise AssertionError("nothing to delete")

    monkeypatch.setattr(demo_reset, "get_recovery_state", lambda patient_id: record)
    monkeypatch.setattr(demo_reset, "save_recovery_state", saved.append)
    monkeypatch.setattr(demo_reset, "event_table", Table())

    result = demo_reset.reset_demo_patient()

    assert result == {"events_deleted": 0, "tasks_reset": 1, "medications_reset": 1}
    state = saved[-1]
    assert state["pending_checkin"] is None
    assert "last_checkin_key" not in state and "scheduled_checkins" not in state
    assert state["tasks"][0]["status"] == "pending" and "completed_at" not in state["tasks"][0]
    assert state["document_id"] == "doc_keep"
    assert state["appointments"] == [{"appointment_id": "appt_1"}]


def test_shared_reset_without_a_plan_raises(monkeypatch):
    monkeypatch.setattr(demo_reset, "get_recovery_state", lambda patient_id: None)

    with pytest.raises(demo_reset.NoPlanToReset):
        demo_reset.reset_demo_patient()
