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


def test_back_from_rebuilds_her_sentence_and_keeps_the_session_open(alexa):
    text, reprompt, ends = alexa.speech(alexa.send(_intent("BackFromIntent", query="my walk")))

    assert alexa.turns == [("I'm back from my walk", "amzn1.echo-api.session.s-1")]
    assert text == "Reply to: I'm back from my walk"
    assert reprompt["outputSpeech"]["text"] == handlers.REPROMPT and not ends


@pytest.mark.parametrize("intent, slots, message", [
    ("HadIntent", {"query": "my breakfast and i've taken my medicine"}, "I've had my breakfast and i've taken my medicine"),
    ("TakenIntent", {"query": "both how long do I take them for"}, "I've taken both how long do I take them for"),
    ("YesIntent", {"query": "both tablets taken and how long those for"}, "yes both tablets taken and how long those for"),
    ("MedicineAnswerIntent", {"medicine": "both"}, "both"),
    ("AskWhenCanIIntent", {"query": "plan to go for a drive"}, "when can I plan to go for a drive"),
    ("AskCanIIntent", {"query": "have a glass of wine"}, "can I have a glass of wine"),
    ("UnwellMyIntent", {"query": "calf is swollen"}, "my calf is swollen"),
    ("BreathlessIntent", {}, "I'm short of breath"),
    ("NeedHelpIntent", {}, "I need help"),
    ("WhatsNextIntent", {}, "What's next?"),
    ("PlanTodayIntent", {}, "What's left today?"),
])
def test_each_opening_reaches_the_agent_as_she_said_it(alexa, intent, slots, message):
    alexa.send(_intent(intent, **slots))

    assert alexa.turns[0][0] == message


def test_every_opening_intent_in_the_model_has_its_opening_words():
    model = json.load(open("skill-package/interactionModels/custom/en-GB.json", encoding="utf-8"))
    for intent in model["interactionModel"]["languageModel"]["intents"]:
        if any("{query}" in sample for sample in intent["samples"]) and intent["name"] in handlers.OPENINGS:
            opening = handlers.OPENINGS[intent["name"]].lower()
            assert any(sample.lower().startswith(opening) for sample in intent["samples"]), intent["name"]
    names = {intent["name"] for intent in model["interactionModel"]["languageModel"]["intents"]}
    # Every handled intent is in the model, and every custom intent in the model is handled.
    handled = set(handlers.OPENINGS) | set(handlers.FIXED) | {"MedicineAnswerIntent"}
    assert handled <= names
    assert {name for name in names if not name.startswith("AMAZON.")} <= handled

    samples = [s.lower() for intent in model["interactionModel"]["languageModel"]["intents"] for s in intent["samples"]]
    assert len(samples) == len(set(samples)), "a sample is in two intents"


def test_the_sentence_is_echoed_only_when_asked(alexa, monkeypatch):
    plain = alexa.send(_intent("BackFromIntent", query="my walk")).json()
    assert "sent_to_run_turn" not in (plain.get("sessionAttributes") or {})

    monkeypatch.setenv("ALEXA_ECHO_SENTENCE", "true")
    echoed = alexa.send(_intent("BackFromIntent", query="my walk")).json()
    assert echoed["sessionAttributes"]["sent_to_run_turn"] == "I'm back from my walk"


@pytest.mark.parametrize("intent, slots", [("UnwellMyIntent", {"query": "calf is swollen"}), ("NeedHelpIntent", {})])
def test_unwell_reply_is_spoken_as_it_is_with_no_reprompt(alexa, intent, slots):
    text, reprompt, ends = alexa.speech(alexa.send(_intent(intent, **slots)))

    assert text == f"Reply to: {alexa.turns[0][0]}"
    assert reprompt is None and ends is False


def test_help_ends_with_how_to_get_help_now(alexa):
    text, reprompt, ends = alexa.speech(alexa.send(_intent("AMAZON.HelpIntent")))

    assert text.endswith("If something is wrong right now, say: I need help.")
    assert reprompt and not ends and alexa.turns == []


@pytest.mark.parametrize("intent", ["AMAZON.StopIntent", "AMAZON.CancelIntent"])
def test_stop_and_cancel_say_goodbye_and_end(alexa, intent):
    text, reprompt, ends = alexa.speech(alexa.send(_intent(intent)))

    assert text == "Take care, Margaret." and ends is True and reprompt is None


@pytest.mark.parametrize("intent", ["AMAZON.FallbackIntent", "SomeUnknownIntent"])
def test_fallback(alexa, intent):
    text, _, ends = alexa.speech(alexa.send(_intent(intent)))

    assert text == handlers.FALLBACK and not ends and alexa.turns == []


def test_another_skill_is_refused_and_logged(alexa, capsys):
    response = alexa.send(_intent("BackFromIntent", query="my walk"), skill="amzn1.ask.skill.someone-else")

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
