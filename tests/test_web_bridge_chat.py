"""POST /chat on the web bridge: real agent loop, scripted model, fake MCP and state."""

from types import SimpleNamespace

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import turn, web_bridge
from app.agent import service
from app.agent.safety import remove_wake_word


WALK_ID = "task_abc#2026-10-23#1"
CHECKIN_KEY = f"2026-10-23#{WALK_ID}"

TODAY_TASKS = {
    "ok": True,
    "data": {
        "date": "2026-10-23",
        "tasks": [
            {"occurrence_id": WALK_ID, "title": "Short walk", "clock_time": "07:30", "status": "pending"}
        ],
    },
}


def _tool_use(name, arguments=None):
    return {
        "role": "assistant",
        "content": [{"toolUse": {"toolUseId": f"id-{name}", "name": name, "input": arguments or {}}}],
    }


def _text(text):
    return {"role": "assistant", "content": [{"text": text}]}


@pytest.fixture
def bridge(monkeypatch):
    """Scripted model turns, recorded MCP calls and an in-memory RecoveryState."""

    run = SimpleNamespace(
        model_turns=[],
        seen_messages=[],
        tool_calls=[],
        state={
            "timezone": "Europe/London",
            "pending_checkin": {"checkin_id": CHECKIN_KEY, "occurrence_id": WALK_ID},
            "last_checkin_key": CHECKIN_KEY,
        },
        patients=[],
        chats=[],
        scheduled=[],
    )

    def converse(**kwargs):
        run.seen_messages.append(kwargs["messages"][0]["content"][0]["text"])
        message = run.model_turns.pop(0)
        stop = "tool_use" if any("toolUse" in b for b in message["content"]) else "end_turn"
        return {"output": {"message": message}, "stopReason": stop}

    async def call_tool(name, arguments):
        run.tool_calls.append((name, arguments))
        payload = TODAY_TASKS if name == "get_today_tasks" else {"ok": True, "data": {}}
        return SimpleNamespace(structured_content=payload, is_error=False, content=[])

    async def no_tools():
        return {"tools": []}

    def get_state(patient_id):
        run.patients.append(patient_id)
        return run.state

    def clear(patient_id):
        run.state.pop("pending_checkin", None)

    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")
    monkeypatch.setattr(turn, "get_recovery_state", get_state)
    monkeypatch.setattr(turn, "clear_pending_checkin", clear)
    monkeypatch.setattr(turn, "record_chat_activity", lambda patient_id, at: run.chats.append(at))
    monkeypatch.setattr(turn, "add_scheduled_checkin", lambda patient_id, entry: run.scheduled.append(entry))

    run.client = TestClient(web_bridge.app)
    return run


def _write_calls(run):
    return [name for name, _ in run.tool_calls if name.startswith("report_")]


def test_wake_word_removed_mid_sentence():
    assert remove_wake_word("Thanks, Alexa. I'm just getting ready.") == "Thanks, I'm just getting ready."


def test_acknowledgement_clears_reminder_without_completing(bridge):
    response = bridge.client.post(
        "/chat", json={"message": "Thanks, Alexa. I'm just getting ready.", "session_id": "s-ack"}
    )

    assert response.status_code == 200
    # Answered in code: no model call, nothing written, the reminder is not repeated.
    assert bridge.seen_messages == []
    assert response.json()["response"].startswith("Lovely.")
    assert _write_calls(bridge) == []
    assert "pending_checkin" not in bridge.state
    assert bridge.state["last_checkin_key"] == CHECKIN_KEY
    assert TODAY_TASKS["data"]["tasks"][0]["status"] == "pending"


def test_completion_report_uses_write_tool_then_clears(bridge):
    bridge.model_turns = [
        _tool_use("get_today_tasks"),
        _tool_use("report_task_completed", {"occurrence_id": WALK_ID}),
        _text("Well done on your walk. I've marked it as done."),
    ]

    response = bridge.client.post(
        "/chat", json={"message": "Alexa, I'm back from my 7:30 am walk.", "session_id": "s-walk"}
    )

    body = response.json()
    assert response.status_code == 200
    assert bridge.seen_messages[0] == "I'm back from my 7:30 am walk."
    assert ("report_task_completed", {"occurrence_id": WALK_ID}) in bridge.tool_calls
    # Today's facts are read first; "7:30" names the walk, so the model chooses and writes it.
    assert [step["tool"] for step in body["tool_trace"]] == [
        "get_today_tasks", "get_medications", "get_recovery_plan", "get_today_tasks", "report_task_completed",
    ]
    assert body["session_id"] == "s-walk"
    assert set(body) == {"response", "tool_trace", "source", "help", "session_id", "request_id"}
    # "help" is the Get help card for a symptom reply; a completion report has none.
    assert body["help"] is None
    assert "pending_checkin" not in bridge.state
    assert bridge.state["last_checkin_key"] == CHECKIN_KEY


def test_agent_failure_returns_error_and_keeps_reminder(bridge, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("Bedrock unavailable")

    monkeypatch.setattr(service.bedrock, "converse", broken)

    response = bridge.client.post("/chat", json={"message": "What's next, Alexa?", "session_id": "s-fail"})

    assert response.status_code == 502
    assert response.json() == {"error": web_bridge.CHAT_ERROR}
    assert bridge.state["pending_checkin"]["checkin_id"] == CHECKIN_KEY


def test_crisis_is_answered_when_her_record_cannot_be_read(bridge, monkeypatch):
    def unreadable(patient_id):
        raise RuntimeError("DynamoDB unavailable")

    monkeypatch.setattr(turn, "get_recovery_state", unreadable)

    response = bridge.client.post("/chat", json={"message": "Alexa, I want to kill myself", "session_id": "s-crisis-down"})

    assert response.status_code == 200
    reply = response.json()["response"]
    # The fixed reply without her name: no record, model, MCP tool or chat activity was needed.
    assert reply.startswith("I'm really sorry you're feeling this way. ")
    assert "999" in reply and "116 123" in reply
    assert bridge.seen_messages == [] and bridge.tool_calls == [] and bridge.chats == []

    # Anything else still fails as before.
    response = bridge.client.post("/chat", json={"message": "What's next?", "session_id": "s-other-down"})
    assert response.status_code == 502
    assert response.json() == {"error": web_bridge.CHAT_ERROR}


def test_unfinished_turn_keeps_reminder(bridge):
    # The model never stops calling tools, so chat() hits its round limit.
    bridge.model_turns = [_tool_use("get_today_tasks") for _ in range(service.MAX_TOOL_ROUNDS + 1)]

    response = bridge.client.post("/chat", json={"message": "What's next?", "session_id": "s-loop"})

    assert response.status_code == 200
    assert response.json()["response"].startswith("Sorry, I couldn't finish that.")
    assert "pending_checkin" in bridge.state


def test_no_reminder_means_nothing_to_clear(bridge, monkeypatch):
    bridge.state.pop("pending_checkin")
    monkeypatch.setattr(
        turn, "clear_pending_checkin", lambda patient_id: pytest.fail("nothing to clear")
    )
    bridge.model_turns = [_text("Hello.")]

    response = bridge.client.post("/chat", json={"message": "Hello", "session_id": "s-none"})

    assert response.status_code == 200


def test_empty_message_is_rejected(bridge):
    response = bridge.client.post("/chat", json={"message": "   "})

    assert response.status_code == 400
    assert bridge.seen_messages == []
    assert "pending_checkin" in bridge.state


def test_caller_cannot_choose_patient(bridge):
    bridge.model_turns = [_text("Hello.")]

    response = bridge.client.post(
        "/chat", json={"message": "Hello", "patient_id": "someone_else", "session_id": "s-pid"}
    )

    assert response.status_code == 400
    assert bridge.patients == []


def test_missing_session_id_gets_a_new_one(bridge):
    bridge.model_turns = [_text("Hello.")]

    body = bridge.client.post("/chat", json={"message": "Hello"}).json()

    assert body["session_id"]
