"""POST /alexa: request checks, launch, TaskDone and MedicineTaken. Fake turn and record; no AWS, no Amazon."""

import json
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app import web_bridge
from app.alexa import handlers
from tests.conftest import log_lines

SKILL = "amzn1.ask.skill.test-0000"


def _envelope(request, skill=SKILL, session="amzn1.echo-api.session.s-1"):
    return {
        "version": "1.0",
        "session": {"new": False, "sessionId": session, "application": {"applicationId": skill},
                    "user": {"userId": "amzn1.ask.account.test"}},
        "context": {"System": {"application": {"applicationId": skill}, "user": {"userId": "amzn1.ask.account.test"},
                               "device": {"deviceId": "d", "supportedInterfaces": {}}, "apiEndpoint": "https://api.amazonalexa.com"}},
        "request": {"requestId": "amzn1.echo-api.request.r-1", "timestamp": "2026-10-23T06:00:00Z",
                    "locale": "en-GB", **request},
    }


def _intent(name, **slots):
    return {"type": "IntentRequest", "intent": {"name": name, "confirmationStatus": "NONE", "slots": {
        key: {"name": key, "value": value, "confirmationStatus": "NONE"} for key, value in slots.items()}}}


@pytest.fixture
def alexa(monkeypatch):
    run = SimpleNamespace(turns=[], state={"first_name": "Margaret"})

    async def fake_turn(message, session_id):
        run.turns.append((message, session_id))
        return {"response": f"Reply to: {message}", "tool_trace": [], "source": None, "help": None}

    monkeypatch.setenv("ALEXA_SKILL_ID", SKILL)
    monkeypatch.setenv("ALEXA_VERIFY_SIGNATURE", "false")
    monkeypatch.setenv("ALEXA_VERIFY_TIMESTAMP", "false")
    monkeypatch.setattr(handlers, "run_turn", fake_turn)
    monkeypatch.setattr(handlers, "get_recovery_state", lambda patient_id: run.state)

    client = TestClient(web_bridge.app)

    def send(request, **kwargs):
        return client.post("/alexa", content=json.dumps(_envelope(request, **kwargs)))

    def speech(response):
        body = response.json()["response"]
        return body["outputSpeech"]["text"], body.get("reprompt"), body.get("shouldEndSession")

    run.send, run.speech = send, speech
    return run


def test_launch_speaks_the_waiting_reminder_without_running_a_turn(alexa):
    alexa.state["pending_checkin"] = {"text": "Good morning, Margaret. It's time for your morning walk."}

    text, reprompt, ends = alexa.speech(alexa.send({"type": "LaunchRequest"}))

    assert text == "Good morning, Margaret. It's time for your morning walk."
    assert alexa.turns == [] and reprompt and not ends


def test_launch_without_a_reminder_greets_and_says_what_is_next(alexa):
    text, _, _ = alexa.speech(alexa.send({"type": "LaunchRequest"}))

    assert text == "Hello, Margaret. Reply to: What is next?"
    assert alexa.turns == [("What is next?", "amzn1.echo-api.session.s-1")]


def test_task_done_rebuilds_the_sentence_and_keeps_the_session_open(alexa):
    text, reprompt, ends = alexa.speech(alexa.send(_intent("TaskDoneIntent", query="my walk")))

    assert alexa.turns == [("I've done my walk", "amzn1.echo-api.session.s-1")]
    assert text == "Reply to: I've done my walk"
    assert reprompt["outputSpeech"]["text"] == handlers.REPROMPT and not ends


@pytest.mark.parametrize("slots, message", [
    ({"query": "both how long do I take them for"}, "I've taken both how long do I take them for"),
    ({"medicine": "both"}, "both"),
])
def test_medicine_taken(alexa, slots, message):
    alexa.send(_intent("MedicineTakenIntent", **slots))

    assert alexa.turns[0][0] == message


def test_other_intents_say_coming_soon(alexa):
    text, _, _ = alexa.speech(alexa.send(_intent("AskLetterIntent", query="have a bath")))

    assert text == handlers.COMING_SOON and alexa.turns == []


def test_another_skill_is_refused_and_logged(alexa, capsys):
    response = alexa.send(_intent("TaskDoneIntent", query="my walk"), skill="amzn1.ask.skill.someone-else")

    assert response.status_code == 403 and alexa.turns == []
    rejected = [line for line in log_lines(capsys.readouterr().out) if line["event"] == "alexa_rejected"]
    assert rejected and rejected[0]["reason"] == "skill_id"


def test_no_skill_id_set_refuses_everything(alexa, monkeypatch):
    monkeypatch.delenv("ALEXA_SKILL_ID")

    assert alexa.send({"type": "LaunchRequest"}).status_code == 403


def test_an_unsigned_request_is_refused_when_checks_are_on(alexa, monkeypatch, capsys):
    monkeypatch.setenv("ALEXA_VERIFY_SIGNATURE", "true")

    response = alexa.send({"type": "LaunchRequest"})

    assert response.status_code == 400 and alexa.turns == []
    rejected = [line for line in log_lines(capsys.readouterr().out) if line["event"] == "alexa_rejected"]
    assert rejected[0]["reason"] == "signature"


def test_an_old_request_is_refused_by_the_timestamp_check(alexa, monkeypatch):
    monkeypatch.setenv("ALEXA_VERIFY_TIMESTAMP", "true")

    assert alexa.send({"type": "LaunchRequest"}).status_code == 400
