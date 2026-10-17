"""
Crisis handling (app/agent/crisis.py), tests K1 to K8.

A crisis message is answered first, with fixed words: no MCP tool, no model,
nothing saved, and no message text in the logs. The conversations run the
real agent with tools and a model that fail the test if they are touched
on a crisis turn. Demo clock 08:15.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import web_bridge
from app.agent import service
from app.agent.crisis import asks_about_doses, crisis_reply, is_crisis, normalise
from app.agent.session import clear_session, get_history
from app.agent.symptoms import sign_wording
from tests.conftest import log_lines


K1 = (
    "I'm really sorry you're feeling this way, Margaret. You don't have to go through this alone. "
    "If you might act on it now, call 999. You can talk to Samaritans any time on 116 123, free."
)
HELP = "If you might act on it now, call 999. You can talk to Samaritans any time on 116 123, free."
PARA = "para#2026-10-23#1"


@pytest.fixture
def agent(monkeypatch):
    run = SimpleNamespace(tool_calls=[], model_calls=0, session="s-crisis")
    clear_session(run.session)
    meds = [{"occurrence_id": PARA, "medication_id": "para", "name": "Paracetamol", "dose": "2 tablets",
             "instructions": "Take the morning dose after breakfast.", "time_of_day_label": "morning",
             "occurrence_number": 1, "status": "pending"}]

    async def call_tool(name, arguments):
        run.tool_calls.append(name)
        data = {"date": "2026-10-23", "tasks": [], "medications": [dict(m) for m in meds]}
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def converse(**kwargs):
        run.model_calls += 1
        message = {"role": "assistant", "content": [{"text": "Paracetamol is 2 tablets, up to four times a day."}]}
        return {"output": {"message": message}, "stopReason": "end_turn"}

    async def no_tools():
        return {"tools": []}

    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T08:15:00+01:00")
    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")

    def say(message, pending=None, first_name="Margaret"):
        return asyncio.run(service.chat(message, run.session, pending_checkin=pending, first_name=first_name))

    run.say = say
    return run


def _untouched(run) -> bool:
    return run.tool_calls == [] and run.model_calls == 0


# ---------- K1: direct words, the exact reply ----------

@pytest.mark.parametrize("message", [
    "I want to kill myself", "I want to end my life", "I've been thinking about suicide", "I just want to die",
    "Alexa, I WANT TO KILL MYSELF!!!", "i   want to  die...",
])
def test_k1_direct_words_get_the_exact_crisis_reply(agent, message):
    reply = agent.say(message)

    assert reply["response"] == K1
    assert reply["tool_trace"] == [] and reply["source"] is None and _untouched(agent)


def test_k1_without_a_name():
    assert crisis_reply("Margaret") == K1
    assert crisis_reply(None) == (
        "I'm really sorry you're feeling this way. You don't have to go through this alone. " + HELP
    )


# ---------- K2: slang ----------

@pytest.mark.parametrize("message", ["kms", "honestly kms", "KMS.", "might as well kys"])
def test_k2_slang(message):
    assert is_crisis(message)


@pytest.mark.parametrize("message", ["how many kms is the walk", "the walk is 2 kms"])
def test_k2_slang_is_a_whole_word(message):
    # "kms" as kilometres is a known false alarm we accept only when it stands alone as a word.
    assert is_crisis(message) is True
    assert not is_crisis("my alarms keep going off") and not is_crisis("skyscraper")


# ---------- K3: indirect phrases ----------

@pytest.mark.parametrize("message", [
    "everyone would be better off without me", "I don't see the point any more", "I dont see the point",
    "I do not see the point", "there's no point going on", "There is no point in carrying on.",
])
def test_k3_indirect_phrases(message):
    assert is_crisis(message)


# ---------- K4: taking all the tablets, and asking how much would cause harm ----------

@pytest.mark.parametrize("message", [
    "I'm going to take all my tablets", "I might just take all my pills", "take all of the tablets",
    "how many paracetamols would it take to hurt me", "how many tablets would kill me",
    "how much codeine would it take to harm me", "what is the lethal dose of paracetamol",
    "is that enough tablets to kill me", "I want to hurt myself", "I could overdose on my painkillers",
])
def test_k4_tablets_and_harm(message):
    assert is_crisis(message)


def test_k4_the_harm_question_is_never_answered_from_the_letter(agent):
    reply = agent.say("how many paracetamols would it take to hurt me")

    assert reply["response"] == K1
    assert "letter" not in reply["response"] and _untouched(agent)


# ---------- K5: a follow-up about doses gets the crisis reply again ----------

@pytest.mark.parametrize("follow_up", [
    "how many paracetamol can I take", "what's the maximum dose", "how much codeine is in a tablet",
    "how many tablets are in the box",
])
def test_k5_dose_questions_after_a_crisis_get_the_crisis_reply_again(agent, follow_up):
    agent.say("I want to die")

    assert agent.say(follow_up)["response"] == K1
    # And not only on the next turn.
    agent.say("the weather is nice")
    agent.tool_calls.clear(); agent.model_calls = 0
    assert agent.say(follow_up)["response"] == K1
    assert _untouched(agent)


def test_k5_a_dose_question_with_no_crisis_before_is_answered_as_usual(agent):
    reply = agent.say("how many paracetamol do I take?")

    assert reply["response"] != K1 and agent.tool_calls
    assert asks_about_doses("how many paracetamol do I take?")


# ---------- K6: the next turn asks how she is before the plan ----------

def test_k6_a_plan_question_on_the_next_turn_starts_with_how_are_you_feeling(agent):
    agent.say("I don't see the point")

    reply = agent.say("what's next?")

    assert reply["response"].startswith("Before we carry on, how are you feeling now?")
    assert reply["response"].endswith(HELP)
    assert "paracetamol" not in reply["response"] and _untouched(agent)

    # Asked once: the plan is answered again after that.
    later = agent.say("what's next?")
    assert "paracetamol" in later["response"] and "Before we carry on" not in later["response"]


def test_k6_only_on_the_next_turn(agent):
    agent.say("I don't see the point")
    agent.say("thank you")

    assert "Before we carry on" not in agent.say("what's next?")["response"]


# ---------- K7: nothing is called, saved or logged as text ----------

def test_k7_no_tools_no_model_no_history_and_no_text_in_the_logs(agent, capsys):
    message = "I want to kill myself with my paracetamol"

    reply = agent.say(message, pending={"checkin_id": "c", "occurrence_id": PARA, "type": "missed_dose"})

    assert reply["response"] == K1 and _untouched(agent)
    assert get_history(agent.session) == []

    logged = capsys.readouterr().out
    events = [line for line in log_lines(logged) if line["event"] == "crisis"]
    assert len(events) == 1 and events[0]["kind"] == "message" and events[0]["level"] == "warning"
    for word in ("kill", "myself", "paracetamol", agent.session):
        assert word not in logged


def test_k7_the_bridge_keeps_a_waiting_reminder_and_saves_nothing(monkeypatch):
    state = {"first_name": "Margaret", "pending_checkin": {"checkin_id": "c", "occurrence_id": PARA}}
    cleared = []

    async def no_tool(name, arguments):
        raise AssertionError("no MCP tool on a crisis turn")

    monkeypatch.setattr(service, "call_mcp_tool", no_tool)
    monkeypatch.setattr(web_bridge, "get_recovery_state", lambda patient_id: state)
    monkeypatch.setattr(web_bridge, "record_chat_activity", lambda patient_id, at: (_ for _ in ()).throw(AssertionError("crisis must not write metadata")))
    monkeypatch.setattr(web_bridge, "clear_pending_checkin", cleared.append)

    response = TestClient(web_bridge.app).post("/chat", json={"message": "I want to end my life", "session_id": "s-k7"})

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == K1 and body["tool_trace"] == [] and body["source"] is None
    assert cleared == []


# ---------- K8: ordinary uses of "kill" and other everyday messages ----------

@pytest.mark.parametrize("message", [
    "kill the reminder", "can you kill the reminder please", "my knee is killing me",
    "this walk will be the death of me", "I took all my tablets this morning", "I've taken my paracetamol",
    "what's the point of the ice pack?", "I'd die for a cup of tea", "the pain is killing me",
    "how many tablets do I take?", "will the exercises hurt?",
])
def test_k8_ordinary_messages_are_not_a_crisis(message):
    assert not is_crisis(message)


def test_k8_kill_the_reminder_takes_the_usual_path(agent):
    reply = agent.say("kill the reminder")

    assert reply["response"] != K1 and agent.tool_calls


def test_normalise():
    assert normalise("  DON’T   see the point!!  ") == "dont see the point"
    assert normalise("K.M.S") == "k m s"


# ---------- The letter's warning sign is always quoted with who to call ----------

def test_a_warning_sign_whose_source_has_no_action_is_quoted_with_the_action():
    sign = {"text": "Pain that your medicines do not control",
            "action": "Call the ward on 0000 000 000 (fictional number)",
            "source": {"snippet": "Pain that your medicines do not control."}}

    assert sign_wording(sign) == (
        "Call the ward on 0000 000 000 (fictional number) if you have: Pain that your medicines do not control."
    )

    whole = {"text": "chest pain", "action": "Call emergency services straight away",
             "source": {"snippet": "Call emergency services straight away if you have chest pain."}}
    assert sign_wording(whole) == "Call emergency services straight away if you have chest pain."
