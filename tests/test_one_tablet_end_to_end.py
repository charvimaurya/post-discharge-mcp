"""
"I've taken one tablet" through the bridge's POST /chat, end to end.

The model is replaced by one that does what the live bug did: it tries
to save BOTH medicines and then says "I've noted ...". Nothing may be
saved, and the reply must ask which medicine. Demo clock 08:15.
"""

from types import SimpleNamespace

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import web_bridge
from app.agent import service


AFTER_BREAKFAST = "Take the morning dose after breakfast."
WALK = "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame."
ASKS_WHICH = "Which one did you take: your paracetamol or your blood thinner?"


def _day():
    tasks = [
        {"occurrence_id": f"walk#2026-10-23#{n}", "task_id": "walk", "description": WALK, "clock_time": t,
         "occurrence_number": n, "status": "pending"} for n, t in [(1, "07:30"), (2, "15:00")]
    ]
    meds = [
        *[{"occurrence_id": f"para#2026-10-23#{n}", "medication_id": "para", "name": "Paracetamol",
           "dose": "2 tablets", "instructions": AFTER_BREAKFAST, "time_of_day_label": s,
           "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "midday"), (3, "evening"), (4, "bedtime")]],
        *[{"occurrence_id": f"apix#2026-10-23#{n}", "medication_id": "apix", "name": "Apixaban",
           "dose": "1 tablet", "instructions": AFTER_BREAKFAST, "time_of_day_label": s,
           "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "evening")]],
    ]
    return tasks, meds


@pytest.fixture
def bridge(monkeypatch):
    run = SimpleNamespace(saved=[], model_calls=0, state={"timezone": "Europe/London", "first_name": "Margaret"})
    run.tasks, run.meds = _day()

    async def call_tool(name, arguments):
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [dict(t) for t in run.tasks]}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.meds]}
        elif name == "get_recovery_plan":
            data = {"patient_id": "demo_patient_001"}
        elif name == "report_medication_taken":
            run.saved.append(arguments["occurrence_id"])
            data = {"occurrence_id": arguments["occurrence_id"]}
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def converse(**kwargs):
        # Like the live bug: save both, then claim it.
        run.model_calls += 1
        last = kwargs["messages"][-1]["content"]
        if any("toolResult" in block for block in last):
            message = {"role": "assistant", "content": [
                {"text": "Thank you, I've noted your paracetamol and blood thinner."}]}
            return {"output": {"message": message}, "stopReason": "end_turn"}
        message = {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "p", "name": "report_medication_taken",
                         "input": {"occurrence_id": "para#2026-10-23#1"}}},
            {"toolUse": {"toolUseId": "a", "name": "report_medication_taken",
                         "input": {"occurrence_id": "apix#2026-10-23#1"}}},
        ]}
        return {"output": {"message": message}, "stopReason": "tool_use"}

    async def no_tools():
        return {"tools": []}

    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T08:15:00+01:00")
    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")
    monkeypatch.setattr(web_bridge, "get_recovery_state", lambda patient_id: run.state)
    monkeypatch.setattr(web_bridge, "clear_pending_checkin", lambda patient_id: run.state.pop("pending_checkin", None))
    monkeypatch.setattr(web_bridge, "record_chat_activity", lambda patient_id, at: None)
    monkeypatch.setattr(web_bridge, "add_scheduled_checkin", lambda patient_id, entry: None)

    client = TestClient(web_bridge.app)

    def chat(message, session):
        response = client.post("/chat", json={"message": message, "session_id": session})
        assert response.status_code == 200
        return response.json()

    run.chat = chat
    return run


def _assert_nothing_saved_and_asks_which(run, body):
    assert run.saved == []
    assert body["response"] == ASKS_WHICH
    assert "noted" not in body["response"].lower() and "marked" not in body["response"].lower()


def test_a_first_message(bridge):
    body = bridge.chat("I've taken one tablet", "seq-a")

    _assert_nothing_saved_and_asks_which(bridge, body)
    # Answered in code: the model is never asked to guess.
    assert bridge.model_calls == 0


def test_the_executor_refuses_the_models_writes(bridge):
    # A named time sends this to the model, which (like the live bug) tries to save both.
    body = bridge.chat("I took one paracetamol at 8am", "seq-model")

    assert bridge.saved == []
    blocked = [s for s in body["tool_trace"] if s.get("blocked")]
    assert [s["arguments"]["occurrence_id"] for s in blocked] == ["para#2026-10-23#1", "apix#2026-10-23#1"]
    # The model's "I've noted ..." is never spoken after a refused write.
    assert body["response"].startswith("Your letter says 2 tablets of paracetamol")
    assert "noted" not in body["response"].lower()


def test_b_after_i_ate_breakfast(bridge):
    first = bridge.chat("I ate breakfast", "seq-b")
    assert first["response"].endswith("Have you taken them?")

    body = bridge.chat("I've taken one tablet", "seq-b")

    _assert_nothing_saved_and_asks_which(bridge, body)


def test_c_after_the_0700_reminder(bridge):
    bridge.state["pending_checkin"] = {
        "checkin_id": "2026-10-23#walk#2026-10-23#1", "type": "reminder",
        "occurrence_id": "walk#2026-10-23#1", "item_type": "task", "clock_time": "07:30",
        "text": "Good morning, Margaret. I hope you slept well. You have about thirty minutes until your morning walk, at half past seven.",
    }

    body = bridge.chat("I've taken one tablet", "seq-c")

    _assert_nothing_saved_and_asks_which(bridge, body)


def test_then_naming_the_blood_thinner_saves_only_it(bridge):
    bridge.chat("I've taken one tablet", "seq-name")

    body = bridge.chat("the blood thinner", "seq-name")

    assert bridge.saved == ["apix#2026-10-23#1"]
    assert body["response"].startswith("Thank you, Margaret. I've marked your blood thinner, 1 tablet, as taken.")


def test_then_naming_the_paracetamol_saves_nothing(bridge):
    bridge.chat("I've taken one tablet", "seq-para")

    body = bridge.chat("the paracetamol", "seq-para")

    assert bridge.saved == []
    assert body["response"].startswith("Your letter says 2 tablets of paracetamol")


def test_after_a_refusal_the_question_stays_open(bridge):
    bridge.chat("I've taken one tablet", "seq-open")
    bridge.chat("the paracetamol", "seq-open")

    body = bridge.chat("the blood thinner", "seq-open")

    assert bridge.saved == ["apix#2026-10-23#1"]
    assert bridge.model_calls == 0
    assert body["response"].startswith("Thank you, Margaret. I've marked your blood thinner, 1 tablet, as taken.")
