"""A report with a question in it: recorded in code, the question answered, then what is next."""

import pytest

from app.agent import service
from app.agent.service import _question_in_report, _with_answer
from tests.agent.test_dose_answers import BOTH_SAVED, margaret  # noqa: F401  (fixture)

ANSWER = "Your letter says to take paracetamol for 14 days."


@pytest.fixture
def with_model(margaret, monkeypatch):  # noqa: F811
    """The same patient, with a model that answers questions and remembers what it was asked."""

    margaret.asked_model = []
    margaret.system = []

    def converse(**kwargs):
        margaret.asked_model.append(kwargs["messages"][-1]["content"][0]["text"])
        margaret.system.append(" ".join(block["text"] for block in kwargs["system"]))
        return {"output": {"message": {"role": "assistant", "content": [{"text": ANSWER}]}},
                "stopReason": "end_turn"}

    async def no_tools():
        return {"tools": []}

    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")
    return margaret


def test_the_screenshot_message_records_answers_and_says_what_is_next(with_model):
    result, writes = with_model.say(
        "thanks Alexa I had my breakfast and also be tablets both the tablets "
        "how long do I need to take this form",
        fresh=True,
    )

    assert writes == BOTH_SAVED
    reply = result["response"]
    # Recorded, then the answer, then what is next, in that order.
    recorded = reply.index("as taken")
    answered = reply.index(ANSWER)
    next_up = reply.index("Next ")
    assert recorded < answered < next_up, reply
    # The model was told what "this" means.
    assert with_model.asked_model[0].startswith("About my paracetamol and blood thinner: how long")


def test_a_report_without_a_question_never_calls_the_model(with_model):
    result, writes = with_model.say("I have taken both medicine", fresh=True)

    assert writes == BOTH_SAVED
    assert with_model.asked_model == []
    assert ANSWER not in result["response"]


def test_what_is_next_is_not_asked_twice(with_model):
    result, _ = with_model.say("I have taken both medicine, what's next?", fresh=True)

    assert with_model.asked_model == []
    assert result["response"].count("Next ") == 1


@pytest.mark.parametrize("message, question", [
    ("I took both tablets, how long do I take them for", "how long do I take them for"),
    ("I've done my walk. Can I go upstairs now?", "Can I go upstairs now?"),
    ("Took my tablets and is it ok to have coffee", "is it ok to have coffee"),
    ("I had both tablets, when should I stop the blood thinner", "when should I stop the blood thinner"),
    ("I have taken both medicine", None),
    ("I did my walk when I got up", None),
    ("I took both tablets, what's next?", None),
])
def test_finding_the_question_in_a_report(message, question):
    assert _question_in_report(message) == question


def test_the_answer_goes_before_what_is_next():
    reply = "Thank you. I've marked your walk as done. Next are your knee exercises this morning."

    assert _with_answer(reply, "Yes, you can.") == (
        "Thank you. I've marked your walk as done. Yes, you can. Next are your knee exercises this morning."
    )
    assert _with_answer("Thank you.", "Yes.") == "Thank you. Yes."


# ---------- The demo moment: "...or both?" is waiting ----------
# These ask something besides "how long" ("what are they for?"), so the model still answers;
# a plain "how long" about what she just took is answered in code (tests below).

def test_both_and_a_question_saves_answers_then_next(with_model):
    question, _ = with_model.say("I have taken my medicine", fresh=True)
    assert question["response"] == "Your paracetamol, your blood thinner, or both?"

    result, writes = with_model.say("I've taken both. How long do I take them for, and what are they for?")
    reply = result["response"]

    assert writes == BOTH_SAVED
    # (1) The save sentence comes from code, with the doses spoken so a mistake is easy to hear.
    assert reply.startswith("Thank you, Margaret. I've marked your paracetamol, 2 tablets, and your blood thinner, 1 tablet, as taken.")
    # (2) Then the answer, (3) then what is next, once.
    assert reply.index("marked") < reply.index(ANSWER) < reply.index("Next ")
    assert reply.count("Next ") == 1
    assert with_model.asked_model == ["About my paracetamol and blood thinner: How long do I take them for, and what are they for?"]


@pytest.mark.parametrize("first", ["I have taken my medicine", "I ate pizza for breakfast"])
def test_both_the_medicines_and_a_question_saves_both(with_model, first):
    # Spoken in the demo while "...or both?" or "Have you taken them?" was waiting.
    with_model.say(first, fresh=True)

    result, writes = with_model.say(
        "I have taken both the medicines and how long do I need to take this medicines for, what are they for")
    reply = result["response"]

    assert writes == BOTH_SAVED, reply
    assert not reply.startswith("Which one")
    assert reply.index("marked") < reply.index(ANSWER) < reply.index("Next ")


def test_the_question_turn_gets_the_short_honest_rules(with_model):
    with_model.say("I have taken my medicine", fresh=True)
    with_model.say("I've taken both. How long do I take them for, and what are they for?")

    rules = with_model.system[0]
    assert "at most two short sentences" in rules and "I won't guess" in rules
    assert "Do not say what" in rules and "The app adds both." in rules


def test_the_question_turn_never_writes(with_model, monkeypatch):
    # Even if the model tries to record a dose while answering, nothing is saved.
    calls = []

    def converse(**kwargs):
        calls.append(1)
        if len(calls) == 1:
            return {"output": {"message": {"role": "assistant", "content": [{"toolUse": {
                "toolUseId": "t1", "name": "report_medication_taken",
                "input": {"occurrence_id": "para#2026-10-23#2"}}}]}}, "stopReason": "tool_use"}
        return {"output": {"message": {"role": "assistant", "content": [{"text": ANSWER}]}},
                "stopReason": "end_turn"}

    monkeypatch.setattr(service.bedrock, "converse", converse)
    with_model.say("I have taken my medicine", fresh=True)
    _, writes = with_model.say("I've taken both. How long do I take them for, and what are they for?")

    assert writes == BOTH_SAVED  # the two morning doses only; never the midday one


def test_which_question_answer_without_a_question_is_unchanged(with_model):
    with_model.say("I have taken my medicine", fresh=True)
    result, writes = with_model.say("both")

    assert writes == BOTH_SAVED
    assert with_model.asked_model == []


def test_the_question_reuses_todays_plan_instead_of_reading_it_again(with_model, monkeypatch):
    with_model.say("I have taken my medicine", fresh=True)
    reads = []
    real = service.call_mcp_tool

    async def counting(name, arguments):
        if name in ("get_today_tasks", "get_medications"):
            reads.append(name)
        return await real(name, arguments)

    monkeypatch.setattr(service, "call_mcp_tool", counting)
    with_model.say("I've taken both. How long do I take them for, and what are they for?")

    assert sorted(reads) == ["get_medications", "get_today_tasks"]  # once for the whole turn, not twice


# ---------- The plan's appointments are given to the model up front ----------

def test_appointments_fact_gives_dates_only_from_the_plan():
    from app.agent.service import _appointments_fact

    fact = _appointments_fact([
        {"title": "Consultant review", "date": "2026-11-23", "time": "09:15", "location": "Orthopaedic Clinic"},
        {"title": "GP review", "date": None},
        {"title": "Physio", "date": "2026-10-30", "needs_confirmation": True},
    ])

    assert "- Consultant review: 2026-11-23 at 09:15, Orthopaedic Clinic" in fact
    assert "- GP review: date not stated" in fact
    assert "- Physio: date needs confirmation" in fact
    assert _appointments_fact([]).endswith("- None in her plan.")


def test_an_answer_with_a_date_is_not_redone_when_the_plan_was_read_up_front(with_model, monkeypatch):
    # The answer names a date. Before, this forced two more model calls to read the plan.
    dated = "Your consultant will decide at your review on 23 November."
    calls = []

    def converse(**kwargs):
        calls.append(" ".join(block["text"] for block in kwargs["system"]))
        return {"output": {"message": {"role": "assistant", "content": [{"text": dated}]}},
                "stopReason": "end_turn"}

    monkeypatch.setattr(service.bedrock, "converse", converse)
    with_model.say("I have taken my medicine", fresh=True)
    result, _ = with_model.say("I've taken both. How long do I take them for, and what are they for?")

    assert len(calls) == 1, "one model call, not three"
    assert "APPOINTMENTS FROM HER PLAN" in calls[0]
    assert dated in result["response"]
