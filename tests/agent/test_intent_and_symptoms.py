"""
Intent first, every turn (app/agent/intent.py), and symptoms answered only
from the letter (app/agent/symptoms.py).

The conversations run the real agent (app.agent.service.chat) with a fake
plan and a model that does what the live bug did: whatever she says, it
prompts her about the blood thinner. Demo clock 09:30.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import service
from app.agent.intent import Intent, classify_intent
from app.agent.safety import NOTHING_MORE_TO_SAY, remove_unasked_prompts
from app.agent.session import clear_session
from app.agent.symptoms import find_symptom, match_warning_sign
from tests.conftest import log_lines


WARD = "Call the ward on 0000 000 000 (fictional number)"
SIGNS = [
    {"id": "warning_calf", "text": "Pain, swelling, redness or heat in your calf.", "action": WARD,
     "urgency": "contact_care_team",
     "source": {"document_id": "doc", "page": "1", "snippet": f"{WARD} if you have: Pain, swelling, redness or heat in your calf."}},
    {"id": "warning_wound", "text": "Redness, swelling or fluid leaking from the wound.", "action": WARD,
     "urgency": "contact_care_team",
     "source": {"document_id": "doc", "page": "1", "snippet": f"{WARD} if you have: Redness, swelling or fluid leaking from the wound."}},
    {"id": "warning_fever", "text": "A temperature of 38°C or higher.", "action": WARD,
     "urgency": "contact_care_team",
     "source": {"document_id": "doc", "page": "1", "snippet": f"{WARD} if you have: A temperature of 38°C or higher."}},
    {"id": "warning_pain", "text": "Pain that your medicines do not control.", "action": WARD,
     "urgency": "contact_care_team",
     "source": {"document_id": "doc", "page": "1", "snippet": f"{WARD} if you have: Pain that your medicines do not control."}},
    {"id": "warning_chest", "text": "chest pain or sudden shortness of breath", "action": "Call emergency services straight away",
     "urgency": "emergency",
     "source": {"document_id": "doc", "page": "1",
                "snippet": "Call emergency services straight away if you have chest pain or sudden shortness of breath."}},
]

APIX = "apix#2026-10-23#1"
PARA = "para#2026-10-23#1"
MISSED = {"checkin_id": "c1", "type": "missed_dose", "occurrence_id": APIX, "item_type": "medication", "slot": "morning"}
NO_MATCH = (
    "Your letter doesn't mention this, and I can't give medical advice. "
    "If it's severe or sudden, call 999. Otherwise, please call NHS 111 or your care team."
)
NAGGING = "I hope you feel better. When you're ready, you have your blood thinner to take after breakfast."


def _medications():
    return [
        {"occurrence_id": APIX, "medication_id": "apix", "name": "Apixaban", "dose": "1 tablet",
         "instructions": "Take the morning dose after breakfast.", "time_of_day_label": "morning",
         "occurrence_number": 1, "status": "pending"},
        {"occurrence_id": "apix#2026-10-23#2", "medication_id": "apix", "name": "Apixaban", "dose": "1 tablet",
         "time_of_day_label": "evening", "occurrence_number": 2, "status": "pending"},
        {"occurrence_id": PARA, "medication_id": "para", "name": "Paracetamol", "dose": "2 tablets",
         "time_of_day_label": "midday", "occurrence_number": 1, "status": "pending"},
    ]


def _tasks():
    return [{"occurrence_id": f"walk#2026-10-23#{n}", "task_id": "walk", "clock_time": t, "occurrence_number": n,
             "description": "Walking: one short walk of 5 to 10 minutes, twice a day.",
             "status": "completed" if n == 1 else "pending"} for n, t in [(1, "07:30"), (2, "15:00")]]


TODAY = {"tasks": _tasks(), "medications": _medications()}
WHICH = {"kind": "which_medicines", "occurrence_ids": [APIX, PARA]}


# ---------- Intent ----------

@pytest.mark.parametrize("message", [
    "my head is hurting", "I feel dizzy", "my wound is bleeding", "I think I have a fever", "I feel sick",
    "I had a fall", "I'm breathless", "my leg is swollen", "I can't breathe", "the pain is not going away",
])
def test_a_symptom_always_wins_even_with_a_question_waiting(message):
    assert classify_intent(message, None, TODAY) is Intent.SYMPTOM
    assert classify_intent(message, WHICH, TODAY) is Intent.SYMPTOM
    assert classify_intent(message, MISSED, TODAY) is Intent.SYMPTOM


@pytest.mark.parametrize("message", ["yes", "no", "not yet", "both", "the paracetamol", "just one", "thank you"])
def test_an_answer_needs_a_waiting_question(message):
    assert classify_intent(message, WHICH, TODAY) is Intent.ANSWER
    assert classify_intent(message, None, TODAY) is not Intent.ANSWER


@pytest.mark.parametrize("message, intent", [
    ("I've taken my blood thinner", Intent.REPORT),
    ("I'm back from my walk", Intent.REPORT),
    ("I took my painkillers", Intent.REPORT),
    ("I have taken my paracetamol for the pain", Intent.REPORT),
    ("what do I have to do", Intent.PLAN_QUESTION),
    ("what's next?", Intent.PLAN_QUESTION),
    ("When do I take my blood thinner?", Intent.PLAN_QUESTION),
    ("I ate toast for breakfast", Intent.FOOD),
    ("the weather is nice", Intent.OTHER),
    ("Can I have a bath?", Intent.OTHER),
    ("no pain today", Intent.OTHER),
])
def test_other_intents(message, intent):
    assert classify_intent(message, None, TODAY) is intent


@pytest.mark.parametrize("message", ["the weather is nice", "When do I take my blood thinner?", "Can I have a bath?"])
def test_a_message_that_is_not_an_answer_does_not_use_the_question(message):
    assert classify_intent(message, WHICH, TODAY) is not Intent.ANSWER
    assert classify_intent(message, MISSED, TODAY) is not Intent.ANSWER


@pytest.mark.parametrize("message", [
    "I'm taking my blood thinner now", "what does my discharge letter say?", "I took my pain relief",
    "it doesn't hurt", "the swelling has gone", "my blood pressure tablets",
])
def test_these_are_not_symptoms(message):
    assert find_symptom(message) is None


# ---------- Matching the letter's warning signs ----------

@pytest.mark.parametrize("message, sign_id", [
    ("my wound is red", "warning_wound"),
    ("there is fluid leaking from my scar", "warning_wound"),
    ("I think I have a fever", "warning_fever"),
    ("my temperature is high", "warning_fever"),
    ("my calf is swollen and hot", "warning_calf"),
    ("my leg is very painful", "warning_calf"),
    ("I have chest pain", "warning_chest"),
    ("I'm short of breath", "warning_chest"),
    ("I'm in a lot of pain", "warning_pain"),
    # Not in the letter: never matched to a sign about somewhere else.
    ("my head is hurting", None),
    ("my knee hurts", None),
    ("I feel dizzy", None),
    ("my stomach is sore", None),
])
def test_warning_sign_match(message, sign_id):
    sign = match_warning_sign(find_symptom(message), SIGNS)

    assert (sign or {}).get("id") == sign_id


# ---------- The reply filter ----------

def test_unasked_prompt_sentences_are_removed():
    names = ["apixaban", "blood thinner", "walk"]

    assert remove_unasked_prompts(
        f"It is! {NAGGING}", "the weather is nice", names,
    ) == "It is! I hope you feel better."
    assert remove_unasked_prompts(
        "Have you taken your blood thinner?", "the weather is nice", names,
    ) == NOTHING_MORE_TO_SAY
    # A letter answer that names a medicine is kept, and so is anything she asked about.
    letter = "Your letter says to avoid alcohol while taking apixaban."
    assert remove_unasked_prompts(letter, "can I drink?", names) == letter
    asked = "You still have your blood thinner to take."
    assert remove_unasked_prompts(asked, "what about my blood thinner", names) == asked


# ---------- Conversations through the real agent ----------

@pytest.fixture
def agent(monkeypatch):
    run = SimpleNamespace(saved=[], model_calls=0, searches=[], tasks=_tasks(), meds=_medications(),
                          letter=[], session="s-intent")
    clear_session(run.session)

    async def call_tool(name, arguments):
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [dict(t) for t in run.tasks]}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.meds]}
        elif name == "get_recovery_plan":
            data = {"warning_signs": SIGNS}
        elif name == "search_discharge_instructions":
            run.searches.append(arguments["query"])
            data = run.letter
        elif name == "report_medication_taken":
            run.saved.append(arguments["occurrence_id"])
            for dose in run.meds:
                if dose["occurrence_id"] == arguments["occurrence_id"]:
                    dose["status"] = "completed"
            data = {"occurrence_id": arguments["occurrence_id"]}
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def converse(**kwargs):
        # The live bug: whatever she says, try to save the blood thinner and prompt her about it.
        run.model_calls += 1
        last = kwargs["messages"][-1]["content"]
        if run.model_calls % 2 == 1 and not any("toolResult" in block for block in last):
            message = {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": "a", "name": "report_medication_taken", "input": {"occurrence_id": APIX}}}]}
            return {"output": {"message": message}, "stopReason": "tool_use"}
        return {"output": {"message": {"role": "assistant", "content": [{"text": NAGGING}]}}, "stopReason": "end_turn"}

    async def no_tools():
        return {"tools": []}

    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T09:30:00+01:00")
    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")

    def say(message, pending=None):
        return asyncio.run(service.chat(message, run.session, pending_checkin=pending, first_name="Margaret"))

    run.say = say
    return run


def _mentions_medicine(reply: str) -> bool:
    return any(word in reply.lower() for word in ("blood thinner", "apixaban", "paracetamol", "tablet"))


def test_next_step_then_a_symptom_then_next_step_again(agent):
    first = agent.say("what do I have to do")
    assert "blood thinner" in first["response"]

    symptom = agent.say("my head is hurting")
    assert symptom["response"] == f"I'm sorry your head hurts, Margaret. {NO_MATCH}"
    assert not _mentions_medicine(symptom["response"])
    assert symptom["source"] is None

    # Allowed again, because she asked.
    again = agent.say("what's next?")
    assert "blood thinner" in again["response"]

    assert agent.saved == [] and agent.model_calls == 0


def test_a_symptom_wins_over_the_blood_thinner_question(agent, capsys):
    reply = agent.say("my head is hurting", pending=MISSED)

    assert reply["response"] == f"I'm sorry your head hurts, Margaret. {NO_MATCH}"
    assert agent.saved == [] and agent.model_calls == 0
    assert not any(step["tool"].startswith("report_") for step in reply["tool_trace"])
    # The letter was looked in: the plan's warning signs, its emergency number, then a search.
    assert [step["tool"] for step in reply["tool_trace"]][-3:] == [
        "get_recovery_plan", "search_discharge_instructions", "search_discharge_instructions"]

    logged = capsys.readouterr().out
    symptom_lines = [line for line in log_lines(logged) if line["event"] == "symptom"]
    assert [line["reason"] for line in symptom_lines] == ["none"]
    assert "head" not in logged and "hurting" not in logged


def test_yes_after_the_blood_thinner_question_saves_it(agent):
    reply = agent.say("yes", pending=MISSED)

    assert agent.saved == [APIX]
    assert "blood thinner" in reply["response"] and "taken" in reply["response"]
    assert agent.model_calls == 0


def test_the_weather_after_the_blood_thinner_question_saves_nothing_and_does_not_prompt(agent):
    reply = agent.say("the weather is nice", pending=MISSED)

    assert agent.saved == []
    assert not _mentions_medicine(reply["response"])
    # The model tried to save it; the write was refused in code.
    assert any(step.get("blocked") for step in reply["tool_trace"])

    # The question is gone: a later "yes" is not an answer to it.
    later = agent.say("yes")
    assert agent.saved == []
    assert not _mentions_medicine(later["response"])


def test_a_question_that_is_not_answered_is_dropped(agent):
    # Two medicines are due, so "my tablets" needs a question.
    for dose in agent.meds:
        if dose["occurrence_id"] == PARA:
            dose["time_of_day_label"] = "morning"

    asked = agent.say("I've taken my tablets")
    assert agent.saved == [] and "?" in asked["response"]

    agent.say("the weather is nice")
    # "Both" would have answered the question; it is no longer waiting.
    agent.say("both")

    assert agent.saved == []


def test_never_the_same_medicine_prompt_twice_in_a_row(agent):
    replies = [
        agent.say("what do I have to do")["response"],
        agent.say("the weather is nice")["response"],
        agent.say("it really is lovely out")["response"],
        agent.say("my head is hurting")["response"],
        agent.say("thank you")["response"],
        agent.say("I'm back from my walk")["response"],
    ]

    prompts = [_mentions_medicine(reply) for reply in replies]

    assert prompts[0] is True
    assert prompts[1:5] == [False, False, False, False]
    assert not any(a and b for a, b in zip(prompts, prompts[1:]))


def test_every_saved_report_is_followed_by_the_next_step(agent):
    """After a report she is always told what comes next, even if the reply before named the same step."""

    agent.tasks = [dict(t, status="pending") for t in _tasks()]
    agent.tasks.append({"occurrence_id": "knee#2026-10-23#1", "task_id": "knee", "occurrence_number": 1,
                        "description": "Knee exercises from your physiotherapy sheet.",
                        "time_of_day_label": "afternoon", "status": "pending"})
    inner = service.call_mcp_tool

    async def call_tool(name, arguments):
        if name == "report_task_completed":
            for task in agent.tasks:
                if task["occurrence_id"] == arguments["occurrence_id"]:
                    task["status"] = "completed"
            return SimpleNamespace(structured_content={"ok": True, "data": arguments}, is_error=False, content=[])
        return await inner(name, arguments)

    service.call_mcp_tool = call_tool
    try:
        asked = agent.say("what do I have to do")["response"]
        first = agent.say("I'm back from my walk")["response"]
        second = agent.say("I've done my knee exercises")["response"]
    finally:
        service.call_mcp_tool = inner

    assert "Next is 1 tablet of your blood thinner" in asked
    assert "Next is 1 tablet of your blood thinner" in first
    assert "done" in second and "Next is 1 tablet of your blood thinner" in second


@pytest.mark.parametrize("message, wording", [
    ("my wound is red and leaking", f"{WARD} if you have: Redness, swelling or fluid leaking from the wound."),
    ("I think I have a fever", f"{WARD} if you have: A temperature of 38°C or higher."),
    ("I have chest pain", "Call emergency services straight away if you have chest pain or sudden shortness of breath."),
])
def test_a_warning_sign_in_the_letter_is_quoted_word_for_word(agent, capsys, message, wording):
    reply = agent.say(message, pending=MISSED)

    assert reply["response"] == f"I'm sorry to hear that, Margaret. Your letter says: {wording}"
    assert reply["source"]["section"] == "Warning signs" and reply["source"]["highlight"] == wording
    assert not _mentions_medicine(reply["response"])
    # Only the letter's emergency number is looked up; the sign itself needs no search.
    assert agent.saved == [] and agent.model_calls == 0 and agent.searches == ["emergency services phone number"]

    symptom_lines = [line for line in log_lines(capsys.readouterr().out) if line["event"] == "symptom"]
    assert len(symptom_lines) == 1 and symptom_lines[0]["reason"].startswith("warning_")


def test_a_symptom_found_elsewhere_in_the_letter_is_quoted_with_the_fixed_ending(agent):
    sentence = "Some swelling of the knee is expected for several weeks."
    agent.letter = [{"text": f"AFTER YOUR OPERATION\n{sentence}\nKeep the dressing dry.", "page": 1,
                     "chunk_id": "c7", "document_id": "doc"}]

    reply = agent.say("my knee is swollen")

    assert reply["response"].startswith(f"I'm sorry to hear that, Margaret. Your letter says: {sentence}")
    assert reply["response"].endswith("Otherwise, please call NHS 111 or your care team.")
    assert reply["source"]["page"] == 1
    assert agent.saved == [] and agent.model_calls == 0
