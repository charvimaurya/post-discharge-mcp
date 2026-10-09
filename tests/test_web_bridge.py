"""GET /today on the web bridge, with MCP and DynamoDB replaced by fakes."""

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app import web_bridge
from app.clock import get_clock_label


TASKS = [
    {
        "occurrence_id": "task_abc#2026-10-23#1",
        "title": "Short walk",
        "clock_time": "07:30",
        "status": "pending",
    }
]

CHECKIN = {
    "checkin_id": "2026-10-23#task_abc#2026-10-23#1",
    "occurrence_id": "task_abc#2026-10-23#1",
    "clock_time": "07:30",
    "text": "Good morning. You have about thirty minutes until your walk.",
}


@pytest.fixture
def bridge(monkeypatch):
    """Fake MCP and state reads; record what was asked for."""

    calls = {"tools": [], "patients": []}
    state = {"timezone": "Europe/London"}

    async def fake_call_mcp_tool(name, arguments):
        calls["tools"].append((name, arguments))
        return SimpleNamespace(
            structured_content={"ok": True, "data": {"date": "2026-10-23", "tasks": TASKS}}
        )

    def fake_get_recovery_state(patient_id):
        calls["patients"].append(patient_id)
        return state

    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T06:00:00Z")
    monkeypatch.setattr(web_bridge, "call_mcp_tool", fake_call_mcp_tool)
    monkeypatch.setattr(web_bridge, "get_recovery_state", fake_get_recovery_state)

    return SimpleNamespace(client=TestClient(web_bridge.app), calls=calls, state=state)


def test_clock_label_is_patient_local(monkeypatch):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T06:00:00Z")

    assert get_clock_label("Europe/London") == "Friday 23 October, 07:00"


def test_pending_checkin_is_returned(bridge):
    bridge.state["pending_checkin"] = CHECKIN

    body = bridge.client.get("/today").json()

    assert body["pending_checkin"] == CHECKIN


def test_no_pending_checkin_is_null(bridge):
    response = bridge.client.get("/today")

    assert response.status_code == 200
    assert response.json()["pending_checkin"] is None


def test_tasks_and_clock_pass_through_unchanged(bridge):
    body = bridge.client.get("/today").json()

    assert body == {
        "clock_label": "Friday 23 October, 07:00",
        "tasks": TASKS,
        "pending_checkin": None,
    }
    assert bridge.calls["tools"] == [("get_today_tasks", {})]


def test_caller_cannot_choose_patient_date_or_time(bridge):
    bridge.client.get(
        "/today",
        params={"patient_id": "someone_else", "date": "2030-01-01", "demo_now": "x"},
    )

    assert bridge.calls["patients"] == ["demo_patient_001"]
    assert bridge.calls["tools"] == [("get_today_tasks", {})]


def test_failed_tool_call_returns_clear_error(bridge, monkeypatch):
    async def failing_call(name, arguments):
        raise ConnectionError("MCP unreachable")

    monkeypatch.setattr(web_bridge, "call_mcp_tool", failing_call)

    response = bridge.client.get("/today")

    assert response.status_code == 502
    assert response.json() == {"error": web_bridge.TODAY_ERROR}


def test_tool_error_result_is_not_shown_as_an_empty_day(bridge, monkeypatch):
    async def error_result(name, arguments):
        return SimpleNamespace(structured_content={"ok": False, "error": {"code": "X"}})

    monkeypatch.setattr(web_bridge, "call_mcp_tool", error_result)

    response = bridge.client.get("/today")

    assert response.status_code == 502
    assert "tasks" not in response.json()
