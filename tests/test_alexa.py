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


@pytest.mark.parametrize("sample, message, reprompts", [
    ("have_taken", "I have taken my paracetamol", True),
    ("have_had", "I have had my breakfast", True),
    ("have_done", "I have done my exercises", True),
    ("have_finished", "I have finished my walk", True),
    ("just_had", "I just had lunch", True),
    ("ive_just_had", "I've just had a cup of tea", True),
    ("ate", "I ate my breakfast", True),
    ("eaten", "I've eaten my lunch", True),
    ("got_back_from", "I got back from my walk", True),
    ("already", "I already took my tablets", True),
    ("ive_already", "I've already had my medicine", True),
    ("back", "I'm back", True),
    ("ask_is_it_alright", "is it alright to have a bath", True),
    ("ask_is_it_okay_if", "is it okay if I go upstairs", True),
    ("ask_when_should_i", "when should I take my apixaban", True),
    ("ask_when_do_i", "when do I see my consultant", True),
    ("ask_have_to", "do I have to wear the stockings", True),
    ("ask_what_should_i", "what should I eat", True),
    ("ask_how_much", "how much paracetamol can I take", True),
    ("unwell_fell", "I fell over in the bathroom", False),
    ("unwell_worried", "I'm worried about my leg", False),
    ("unwell_hurts", "it hurts when I breathe", False),
    ("unwell_having", "I'm having chest pain", False),
    ("unwell_noticed", "I've noticed blood in my urine", False),
])
def test_each_new_opening_sample_rebuilds_her_sentence(alexa, sample, message, reprompts):
    request = json.load(open(f"tests/alexa/samples/{sample}.json", encoding="utf-8"))["request"]
    text, reprompt, ends = alexa.speech(alexa.send(request))

    assert alexa.turns[0][0] == message and text == f"Reply to: {message}"
    assert (reprompt is not None) == reprompts and ends is False


@pytest.mark.parametrize("intent, query, reprompts", [
    ("HaveHadIntent", "chest pain", False),
    ("HadIntent", "chest pain", False),
    ("HaveTakenIntent", "my paracetamol", True),
])
def test_a_symptom_reply_never_reprompts_whatever_intent_matched(alexa, monkeypatch, intent, query, reprompts):
    async def triaged_turn(message, session_id):
        symptom = "chest pain" in message
        return {"response": "Call 999 now." if symptom else "Well done.", "tool_trace": [], "source": None,
                "help": {"actions": ["Call 999"]} if symptom else None}

    monkeypatch.setattr(handlers, "run_turn", triaged_turn)
    _, reprompt, ends = alexa.speech(alexa.send(_intent(intent, query=query)))

    assert (reprompt is not None) == reprompts and ends is False


def test_a_crisis_reply_through_a_normal_intent_never_reprompts(alexa, monkeypatch):
    async def crisis_turn(message, session_id):
        return {"response": "Please call 999 now.", "tool_trace": [], "source": None, "help": None, "crisis": True}

    monkeypatch.setattr(handlers, "run_turn", crisis_turn)
    _, reprompt, ends = alexa.speech(alexa.send(_intent("TakenIntent", query="all my tablets at once")))

    assert reprompt is None and ends is False


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


def test_a_letter_answer_comes_with_a_card_and_plain_speech(alexa, monkeypatch):
    async def letter_turn(message, session_id):
        return {"response": "Your letter says: **Do not drive** until your consultant has reviewed you.",
                "tool_trace": [], "help": None,
                "source": {"highlight": "Do not drive until your consultant has reviewed you.", "page": 1}}

    monkeypatch.setattr(handlers, "run_turn", letter_turn)
    body = alexa.send(_intent("AskWhenCanIIntent", query="plan to go for a drive")).json()["response"]

    assert body["outputSpeech"]["text"] == "Your letter says: Do not drive until your consultant has reviewed you."
    assert body["card"] == {"type": "Simple", "title": "From your discharge letter",
                            "content": '"Do not drive until your consultant has reviewed you." (page 1)'}


def test_no_card_without_a_letter_source(alexa):
    body = alexa.send(_intent("WhatsNextIntent")).json()["response"]

    assert "card" not in body


def test_a_slow_turn_says_give_me_a_moment_and_is_logged(alexa, monkeypatch, capsys):
    import asyncio

    async def slow_turn(message, session_id):
        await asyncio.sleep(1)
        return {"response": "late", "tool_trace": [], "source": None, "help": None}

    monkeypatch.setattr(handlers, "run_turn", slow_turn)
    monkeypatch.setenv("ALEXA_AGENT_TIMEOUT_SECONDS", "0.1")

    text, _, _ = alexa.speech(alexa.send(_intent("AskCanIIntent", query="have a bath")))

    assert text == "Give me a moment, then ask me again."
    lines = log_lines(capsys.readouterr().out)
    assert any(line["event"] == "alexa_timeout" for line in lines)
    request = next(line for line in lines if line["event"] == "alexa_request")
    assert request["timed_out"] is True and request["intent"] == "AskCanIIntent"


def test_the_agent_wait_is_7_seconds_unless_set(monkeypatch):
    monkeypatch.delenv("ALEXA_AGENT_TIMEOUT_SECONDS", raising=False)
    assert handlers._timeout_seconds() == 7.0

    monkeypatch.setenv("ALEXA_AGENT_TIMEOUT_SECONDS", "not a number")
    assert handlers._timeout_seconds() == 7.0


def test_one_request_line_with_type_intent_and_time_and_never_her_words(alexa, capsys):
    alexa.send(_intent("UnwellMyIntent", query="calf is swollen"))

    out = capsys.readouterr().out
    request = next(line for line in log_lines(out) if line["event"] == "alexa_request")
    assert request["request_type"] == "IntentRequest" and request["intent"] == "UnwellMyIntent"
    assert request["timed_out"] is False and isinstance(request["ms"], int)
    assert "calf" not in out and "swollen" not in out


@pytest.mark.parametrize("intent", ["AMAZON.FallbackIntent", "SomeUnknownIntent"])
def test_fallback(alexa, intent):
    text, _, ends = alexa.speech(alexa.send(_intent(intent)))

    assert text == handlers.FALLBACK and not ends and alexa.turns == []
    assert text.endswith("If something is wrong right now, say: I need help.")


@pytest.mark.parametrize("intent, slots, message", [
    ("UnwellFellOnlyIntent", {}, "I fell"),
    ("UnwellFellOverIntent", {}, "I fell over"),
    ("UnwellFellDownIntent", {"query": "the stairs"}, "I fell down the stairs"),
    ("UnwellFallenIntent", {"query": "in the bathroom"}, "I've fallen in the bathroom"),
    ("UnwellHaveFallenIntent", {"query": "in the kitchen"}, "I have fallen in the kitchen"),
    ("UnwellHadAFallIntent", {"query": "this morning"}, "I had a fall this morning"),
    ("UnwellIveHadAFallIntent", {"query": "in the garden"}, "I've had a fall in the garden"),
])
def test_a_fall_reaches_the_agent_with_no_reprompt(alexa, intent, slots, message):
    _, reprompt, ends = alexa.speech(alexa.send(_intent(intent, **slots)))

    assert alexa.turns[0][0] == message and reprompt is None and ends is False


@pytest.mark.parametrize("intent", ["TellItIntent", "TellAfterWardIntent", "SayIntent"])
def test_a_catch_all_sends_only_her_words_and_reprompts(alexa, intent):
    _, reprompt, ends = alexa.speech(alexa.send(_intent(intent, query="I've done my walk")))

    assert alexa.turns[0][0] == "I've done my walk" and reprompt is not None and ends is False


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


def test_i_am_back_from_my_walk_is_in_the_back_from_intent():
    model = json.load(open("skill-package/interactionModels/custom/en-GB.json", encoding="utf-8"))
    samples = {intent["name"]: intent["samples"] for intent in model["interactionModel"]["languageModel"]["intents"]}

    assert {"I am back from {query}", "I've got back from {query}"} <= set(samples["BackFromIntent"])


def test_i_am_back_from_my_walk_sends_the_whole_sentence(alexa):
    alexa.send(_intent("BackFromIntent", query="my walk"))

    assert alexa.turns[0][0] == "I'm back from my walk"


@pytest.mark.parametrize("intent, sample, slots, message", [
    ("UnwellHavingIntent", "I am having {query}", {"query": "chest pain"}, "I'm having chest pain"),
    ("UnwellFeelingIntent", "I am feeling {query}", {"query": "dizzy"}, "I'm feeling dizzy"),
    ("InPainIntent", "I am in pain", {}, "I'm in pain"),
    ("NotWellIntent", "I am not well", {}, "I'm not well"),
    ("BreathlessIntent", "I am short of breath", {}, "I'm short of breath"),
])
def test_the_long_form_of_an_unwell_phrase_is_on_the_same_intent_with_no_reprompt(alexa, intent, sample, slots, message):
    model = json.load(open("skill-package/interactionModels/custom/en-GB.json", encoding="utf-8"))
    samples = {i["name"]: i["samples"] for i in model["interactionModel"]["languageModel"]["intents"]}
    assert sample in samples[intent]

    _, reprompt, ends = alexa.speech(alexa.send(_intent(intent, **slots)))

    assert alexa.turns[0][0] == message and reprompt is None and ends is False


def test_every_contraction_sample_has_its_long_form():
    model = json.load(open("skill-package/interactionModels/custom/en-GB.json", encoding="utf-8"))
    long = {"i'm": "i am", "i've": "i have", "i'll": "i will", "it's": "it is",
            "there's": "there is", "what's": "what is", "i'd": "i would"}
    samples = {s.lower() for i in model["interactionModel"]["languageModel"]["intents"] for s in i["samples"]}

    for sample in samples:
        first, _, rest = sample.partition(" ")
        if first in long:
            assert f"{long[first]} {rest}".strip() in samples, sample
