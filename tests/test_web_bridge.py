"""GET /today on the web bridge, with MCP and DynamoDB replaced by fakes."""

from types import SimpleNamespace

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import web_bridge
from app.clock import get_clock_label


TASKS = [
    {
        "occurrence_id": "task_abc#2026-10-23#1",
        "title": "Short walk",
        "description": "Short walk",
        "clock_time": "07:30",
        "status": "pending",
    }
]

MEDICATIONS = [
    {
        "occurrence_id": "med_para#2026-10-23#1",
        "name": "Paracetamol",
        "dose": "2 tablets",
        "time_of_day_label": "morning",
        "status": "pending",
    }
]

TOOL_DATA = {
    "get_today_tasks": {"date": "2026-10-23", "tasks": TASKS},
    "get_medications": {"date": "2026-10-23", "medications": MEDICATIONS},
}

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
    state = {"timezone": "Europe/London", "discharge_date": "2026-10-16"}

    async def fake_call_mcp_tool(name, arguments):
        calls["tools"].append((name, arguments))
        return SimpleNamespace(
            structured_content={"ok": True, "data": TOOL_DATA[name]}
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


TOOLS_CALLED = [("get_today_tasks", {}), ("get_medications", {})]


def test_tasks_medications_and_clock_pass_through_unchanged(bridge):
    body = bridge.client.get("/today").json()

    # Each item gains its place in the day; nothing else changes.
    assert body == {
        "clock_label": "Friday 23 October, 07:00",
        # This test patient's record has no first name.
        "first_name": None,
        # 07:00: the 07:30 walk is inside its reminder window, so the greeting names it (same as the reminder).
        "opening_greeting": "Good morning. I hope you slept well. Next is your morning walk at half past seven. You can start getting ready.",
        "date": "2026-10-23",
        "discharge_date": "2026-10-16",
        "tasks": [dict(TASKS[0], timing="due now")],
        "medications": [dict(MEDICATIONS[0], timing="due now")],
        "pending_checkin": None,
    }
    assert bridge.calls["tools"] == TOOLS_CALLED


def test_today_includes_a_medications_list(bridge):
    body = bridge.client.get("/today").json()

    assert isinstance(body["medications"], list)
    assert body["medications"][0]["occurrence_id"] == "med_para#2026-10-23#1"


def test_caller_cannot_choose_patient_date_or_time(bridge):
    bridge.client.get(
        "/today",
        params={"patient_id": "someone_else", "date": "2030-01-01", "demo_now": "x"},
    )

    assert bridge.calls["patients"] == ["demo_patient_001"]
    assert bridge.calls["tools"] == TOOLS_CALLED


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


def test_failed_medications_call_returns_clear_error(bridge, monkeypatch):
    async def medications_fail(name, arguments):
        if name == "get_medications":
            raise ConnectionError("MCP unreachable")
        return SimpleNamespace(structured_content={"ok": True, "data": TOOL_DATA[name]})

    monkeypatch.setattr(web_bridge, "call_mcp_tool", medications_fail)

    response = bridge.client.get("/today")

    assert response.status_code == 502
    assert response.json() == {"error": web_bridge.TODAY_ERROR}


def test_medications_error_result_is_not_shown_as_no_medicines(bridge, monkeypatch):
    async def medications_error(name, arguments):
        if name == "get_medications":
            return SimpleNamespace(structured_content={"ok": False, "error": {"code": "X"}})
        return SimpleNamespace(structured_content={"ok": True, "data": TOOL_DATA[name]})

    monkeypatch.setattr(web_bridge, "call_mcp_tool", medications_error)

    response = bridge.client.get("/today")

    assert response.status_code == 502
    assert "medications" not in response.json()


# ---------- First greeting of the day, then "Welcome back" ----------

def test_first_visit_today_says_good_morning(bridge):
    body = bridge.client.get("/today").json()

    assert body["opening_greeting"].startswith("Good morning. I hope you slept well.")


def test_a_second_visit_today_says_welcome_back_without_slept_well(bridge):
    bridge.state["greeted_on"] = "2026-10-23"

    greeting = bridge.client.get("/today").json()["opening_greeting"]

    assert greeting.startswith("Welcome back.")
    assert "slept well" not in greeting and "Good morning" not in greeting
    # Still names what is next.
    assert "morning walk" in greeting


def test_a_greeting_from_yesterday_is_a_new_good_morning(bridge):
    bridge.state["greeted_on"] = "2026-10-22"

    assert bridge.client.get("/today").json()["opening_greeting"].startswith("Good morning.")


def test_greeted_records_the_patient_local_date(bridge, monkeypatch):
    recorded = []
    monkeypatch.setattr(web_bridge, "record_greeting", lambda patient, day: recorded.append((patient, day)))

    response = bridge.client.post("/greeted", params={"patient_id": "someone_else", "day": "2030-01-01"})

    assert response.status_code == 200
    # 06:00 UTC is 07:00 in London on 23 October; the caller cannot choose patient or day.
    assert recorded == [("demo_patient_001", "2026-10-23")]
