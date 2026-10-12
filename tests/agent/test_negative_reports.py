"""'No, I haven't taken it' never becomes a write; positive medicine reports pick the right dose."""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import service
from app.agent.safety import asked_about_completion, is_negative_report, tidy_reply
from app.agent.session import add_message, clear_session


PARA = [
    {"occurrence_id": f"med_para#2026-10-23#{n}", "medication_id": "med_para", "name": "Paracetamol",
     "dose": "2 tablets", "time_of_day_label": label, "occurrence_number": n, "status": "pending"}
    for n, label in [(1, "morning"), (2, "midday"), (3, "evening"), (4, "bedtime")]
]
APIX = [
    {"occurrence_id": f"med_apix#2026-10-23#{n}", "medication_id": "med_apix", "name": "Apixaban",
     "dose": "1 tablet", "time_of_day_label": label, "occurrence_number": n, "status": "pending"}
    for n, label in [(1, "morning"), (2, "evening")]
]
CODEINE = [{"occurrence_id": "med_cod#2026-10-23#1", "medication_id": "med_cod", "name": "Codeine",
            "as_needed": True, "occurrence_number": 1, "status": "pending"}]


# ---------- The checks on their own ----------

@pytest.mark.parametrize("message", [
    "no I have not taken it",
    "No, I haven't taken it",
    "I haven’t taken my blood thinner yet",
    "I haven't taken my blood thinner yet",
    "Not yet",
    "not yet, I will later",
    "I didn't take it",
    "I forgot my paracetamol",
    "Nope",
    "I'll skip it today",
])
def test_negative_answers_are_recognised(message):
    assert is_negative_report(message)


@pytest.mark.parametrize("message", [
    "I've taken my paracetamol",
    "I took my tablets",
    "I'm back from my walk.",
    "Thanks, I'm just getting ready.",
    "What's left? I'm about to have breakfast.",
    "I'm missing my driving. What does my letter say about it?",
    "And the blood thinner. How long do I take it for?",
    "I took it, no problem",
])
def test_positive_and_ordinary_lines_are_not_negative(message):
    assert not is_negative_report(message)


def test_afterwards_question_gives_the_context():
    assert asked_about_completion("Have you taken your paracetamol yet, Margaret?") == "report_medication_taken"
    assert asked_about_completion("Are you back from your walk?") == "report_task_completed"
    assert asked_about_completion("Your walk is at half past seven.") is None


def test_tidy_reply_removes_fragments_and_promises():
    assert tidy_reply("—let me record those for you. Which did you take?") == "Which did you take?"
    assert tidy_reply("— Well done, Margaret.") == "Well done, Margaret."
    assert tidy_reply("Well done, Margaret.") == "Well done, Margaret."


# ---------- Whole turns through chat(), demo clock 07:50 ----------

@pytest.fixture
def chat(monkeypatch):
    """Fake MCP holding today's plan; the model is scripted, and unused unless a test says so."""

    # Copies, so a dose ticked in one test stays pending in the next.
    run = SimpleNamespace(medications=[dict(m) for m in PARA + APIX + CODEINE], calls=[], model_turns=None)

    async def call_tool(name, arguments):
        run.calls.append((name, arguments))
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": []}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.medications]}
        elif name == "report_medication_taken":
            target = next(m for m in run.medications if m["occurrence_id"] == arguments["occurrence_id"])
            target["status"] = "completed"
            data = {"occurrence_id": target["occurrence_id"], "already_completed": False}
        else:
            data = {}
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def converse(**kwargs):
        if run.model_turns is None:
            raise AssertionError("the model should not be needed for this turn")
        message = run.model_turns.pop(0)
        stop = "tool_use" if any("toolUse" in b for b in message["content"]) else "end_turn"
        return {"output": {"message": message}, "stopReason": stop}

    async def no_tools():
        return {"tools": []}

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T07:50:00+01:00")

    def say(message, asked=None, session="negative"):
        clear_session(session)
        if asked:
            add_message(session, "user", "Hello")
            add_message(session, "assistant", asked)
        result = asyncio.run(service.chat(message, session, first_name="Margaret"))
        writes = [args["occurrence_id"] for name, args in run.calls if name.startswith("report_")]
        run.calls.clear()
        return result, writes

    run.say = say
    return run


ASKED = "Have you taken your morning paracetamol yet, Margaret?"


def test_no_i_have_not_taken_it(chat):
    result, writes = chat.say("no I have not taken it", asked=ASKED)

    assert writes == []
    assert "record" not in result["response"].lower()
    assert result["response"] == (
        "That's okay, Margaret. Your paracetamol is still in today's plan. Tell me when you've taken it."
    )
    note = result["tool_trace"][-1]
    assert note["blocked"] is True and note["ok"] is False and note["tool"] == "report_medication_taken"


def test_not_taken_blood_thinner_yet(chat):
    result, writes = chat.say("I haven't taken my blood thinner yet")

    assert writes == []
    assert result["response"] == (
        "That's okay, Margaret. Your blood thinner is still in today's plan. Tell me when you've taken it."
    )


def test_not_yet_after_a_question(chat):
    result, writes = chat.say("Not yet, Alexa", asked=ASKED)

    assert writes == []
    assert "still in today's plan" in result["response"]


def test_paracetamol_at_0750_records_the_morning_dose_only(chat):
    result, writes = chat.say("I've taken my paracetamol")

    assert writes == ["med_para#2026-10-23#1"]
    assert result["response"].startswith(
        "Thank you, Margaret, I've marked your morning paracetamol, 2 tablets, as taken. "
        "Next is your blood thinner, this morning."
    )


def test_my_tablets_with_two_medicines_due_asks_one_question(chat):
    result, writes = chat.say("I took my tablets")

    assert writes == []
    assert result["response"] == "Your paracetamol, your blood thinner, or both?"


def test_my_tablets_with_one_medicine_due_records_it(chat):
    chat.medications = [dict(m) for m in PARA] + [dict(APIX[0], status="completed"), dict(APIX[1])] + CODEINE

    result, writes = chat.say("I took my tablets")

    assert writes == ["med_para#2026-10-23#1"]


def test_negative_question_goes_to_the_model_but_cannot_write(chat):
    chat.model_turns = [
        {"role": "assistant", "content": [
            {"text": "—let me record those for you."},
            {"toolUse": {"toolUseId": "w1", "name": "report_medication_taken",
                         "input": {"occurrence_id": "med_apix#2026-10-23#1"}}},
        ]},
        {"role": "assistant", "content": [{"text": "That's fine. Your blood thinner is due this morning."}]},
    ]

    result, writes = chat.say("I haven't taken my apixaban, should I take it now?")

    assert writes == []
    # After a refused write the code replies, not the model.
    assert result["response"] == (
        "That's okay, Margaret. Your blood thinner is still in today's plan. Tell me when you've taken it."
    )
    assert any(step.get("blocked") for step in result["tool_trace"])


def test_text_before_a_tool_call_is_never_spoken(chat):
    chat.model_turns = [
        {"role": "assistant", "content": [
            {"text": "—let me check."},
            {"toolUse": {"toolUseId": "r1", "name": "get_medications", "input": {}}},
        ]},
        {"role": "assistant", "content": [{"text": "— Your next paracetamol is at midday."}]},
    ]

    result, _ = chat.say("When is my next paracetamol?")

    assert result["response"] == "Your next paracetamol is at midday."


def test_no_reply_starts_with_a_dash_or_says_let_me_record(chat):
    lines = [
        ("no I have not taken it", ASKED),
        ("I haven't taken my blood thinner yet", None),
        ("Not yet, Alexa", ASKED),
        ("I took my tablets", None),
        ("I've taken my paracetamol", None),
    ]
    for message, asked in lines:
        reply = chat.say(message, asked=asked)[0]["response"]
        assert not reply.startswith(("—", "–", "-"))
        assert "let me record" not in reply.lower()
