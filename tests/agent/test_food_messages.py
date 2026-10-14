"""Food and drink: never judged except by the letter's diet_advice; meal-linked medicines asked about."""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import service
from app.agent.food import diet_reply, is_food_message
from app.agent.session import clear_session


# Synthetic diet advice, test only. Margaret's real letter has no DIET section.
DIET = [
    {"kind": "avoid", "text": "Do not drink alcohol while you are taking codeine.",
     "source": {"page": 1, "snippet": "Do not drink alcohol while you are taking codeine."}},
    {"kind": "advice", "text": "Eat plenty of fibre, such as fruit, vegetables and porridge, and drink plenty of water.",
     "source": {"page": 1, "snippet": "Eat plenty of fibre, such as fruit, vegetables and porridge, and drink plenty of water."}},
]

AFTER_BREAKFAST = "Take the morning dose after breakfast."


def _meds():
    return [
        *[{"occurrence_id": f"para#{n}", "medication_id": "para", "name": "Paracetamol", "dose": "2 tablets",
           "instructions": AFTER_BREAKFAST, "time_of_day_label": s, "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "midday"), (3, "evening"), (4, "bedtime")]],
        *[{"occurrence_id": f"apix#{n}", "medication_id": "apix", "name": "Apixaban", "dose": "1 tablet",
           "instructions": AFTER_BREAKFAST, "time_of_day_label": s, "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "evening")]],
        {"occurrence_id": "cod#1", "medication_id": "cod", "name": "Codeine", "as_needed": True, "status": "pending"},
    ]


@pytest.fixture
def margaret(monkeypatch):
    run = SimpleNamespace(diet=[], meds=_meds(), calls=[])

    async def call_tool(name, arguments):
        run.calls.append((name, arguments))
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": []}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.meds]}
        elif name == "get_recovery_plan":
            data = {"patient_id": "demo_patient_001", **({"diet_advice": run.diet} if run.diet else {})}
        elif name == "report_medication_taken":
            for m in run.meds:
                if m["occurrence_id"] == arguments["occurrence_id"]:
                    m["status"] = "completed"
            data = {"occurrence_id": arguments["occurrence_id"], "already_completed": False}
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def no_model(**kwargs):
        raise AssertionError("food replies must not come from the model")

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", no_model)
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T08:40:00+01:00")

    def say(message, session="food", fresh=True):
        if fresh:
            clear_session(session)
        result = asyncio.run(service.chat(message, session, first_name="Margaret"))
        writes = [args["occurrence_id"] for name, args in run.calls if name.startswith("report_")]
        run.calls.clear()
        return result, writes

    run.say = say
    return run


def test_pizza_for_breakfast_without_diet_advice(margaret):
    result, writes = margaret.say("I ate pizza for breakfast")
    reply = result["response"]

    assert writes == []
    assert reply == (
        "Thanks for telling me, Margaret. Your letter doesn't give any advice about food. "
        "Now that you've had breakfast, it's time for your paracetamol, 2 tablets, and your blood thinner, "
        "1 tablet. Have you taken them?"
    )
    assert "that's fine" not in reply.lower()
    assert "get_recovery_plan" in [t["tool"] for t in result["tool_trace"]]


def test_pizza_with_diet_advice_quotes_one_line_and_never_says_avoid_pizza(margaret):
    margaret.diet = DIET

    reply = margaret.say("I ate pizza for breakfast")[0]["response"]

    assert reply.startswith(
        "Thanks for telling me, Margaret. Your letter doesn't mention pizza. It does say: "
        "Eat plenty of fibre, such as fruit, vegetables and porridge, and drink plenty of water."
    )
    assert "avoid pizza" not in reply.lower() and "shouldn't" not in reply.lower()


def test_breakfast_with_morning_medicines_taken_asks_nothing(margaret):
    for m in margaret.meds:
        if m["occurrence_id"] in ("para#1", "apix#1"):
            m["status"] = "completed"

    reply = margaret.say("I had breakfast")[0]["response"]

    assert reply == "Thanks for telling me, Margaret."


def test_breakfast_without_food_goes_straight_to_the_medicines(margaret):
    reply = margaret.say("I had breakfast")[0]["response"]

    assert reply == (
        "Now that you've had breakfast, it's time for your paracetamol, 2 tablets, and your blood thinner, "
        "1 tablet. Have you taken them?"
    )


def test_wine_gets_a_gentle_warning_quoting_the_alcohol_line(margaret):
    margaret.diet = DIET

    reply = margaret.say("I had a glass of wine")[0]["response"]

    assert reply == "Thanks for telling me, Margaret. Your letter says: Do not drink alcohol while you are taking codeine."


def test_had_porridge_and_banana_gets_praise(margaret):
    margaret.diet = DIET

    reply = margaret.say("I had porridge and a banana")[0]["response"]

    assert reply.startswith("That sounds good, Margaret. Your letter says: Eat plenty of fibre")


def test_porridge_and_banana_without_a_verb_is_not_assumed_eaten(margaret):
    margaret.diet = DIET

    reply = margaret.say("porridge and a banana")[0]["response"]

    assert reply == "Your letter says: Eat plenty of fibre, such as fruit, vegetables and porridge, and drink plenty of water."
    assert "sounds good" not in reply


def test_yes_records_the_meal_medicines(margaret):
    margaret.say("I ate pizza for breakfast", session="meal")

    result, writes = margaret.say("Yes", session="meal", fresh=False)

    assert writes == ["para#1", "apix#1"]
    assert result["response"] == (
        "Thank you, Margaret. I've marked your paracetamol, 2 tablets, and your blood thinner, 1 tablet, as taken. "
        "Next is 2 tablets of your paracetamol, at midday."
    )


def test_no_records_nothing(margaret):
    margaret.say("I ate pizza for breakfast", session="meal-no")

    result, writes = margaret.say("Not yet", session="meal-no", fresh=False)

    assert writes == []
    assert "still in today's plan" in result["response"]


@pytest.mark.parametrize("message", [
    "I ate pizza for breakfast", "I had a glass of wine", "porridge and a banana", "I had breakfast",
    "I've just had a cup of tea",
])
def test_food_messages_are_recognised(message):
    assert is_food_message(message, ["Paracetamol", "Apixaban"])


@pytest.mark.parametrize("message", [
    "I've taken my paracetamol", "I'm back from my walk", "I was sick after breakfast",
    "I had a fall", "What did my paperwork say about driving?", "I had my apixaban",
])
def test_other_messages_are_not_food(message):
    assert not is_food_message(message, ["Paracetamol", "Apixaban"])


@pytest.mark.parametrize("message", ["I ate pizza", "I had chips and a burger", "some chocolate cake", "a pint of beer"])
def test_no_reply_contains_a_food_rule_that_is_not_in_the_letter(message):
    reply = diet_reply(message, DIET, "Margaret")
    quoted = [a["text"] for a in DIET if a["text"] in reply]
    rest = reply
    for line in quoted:
        rest = rest.replace(line, "")

    assert quoted, "every food reply repeats a line from the letter"
    for word in ("avoid", "shouldn't", "should not", "bad for", "healthy", "unhealthy", "calorie", "fine"):
        assert word not in rest.lower()


# ---------- Questions, plans and "not yet" are never treated as "she ate" ----------

from app.agent.food import ATE, NOT_YET, PLAN, QUESTION, classify_food_message

NOT_EATEN = [
    "what can I eat for breakfast",
    "can I have pizza?",
    "can I have a glass of wine?",
    "I'm about to have breakfast",
    "I haven't had breakfast yet",
]


@pytest.mark.parametrize("message,kind", [
    ("I ate pizza for breakfast", ATE), ("I had breakfast", ATE), ("I've had my lunch", ATE),
    ("just finished breakfast", ATE),
    ("what can I eat for breakfast", QUESTION), ("can I have pizza?", QUESTION), ("is it ok to have wine", QUESTION),
    ("should I eat before my tablets", QUESTION), ("am I allowed coffee", QUESTION), ("porridge and a banana", QUESTION),
    ("I'm going to have lunch", PLAN), ("about to eat", PLAN), ("having breakfast now", PLAN),
    ("I haven't had breakfast", NOT_YET), ("not eaten yet", NOT_YET), ("no breakfast yet", NOT_YET),
])
def test_classification(message, kind):
    assert classify_food_message(message) == kind


@pytest.mark.parametrize("message", NOT_EATEN)
@pytest.mark.parametrize("with_diet", [False, True])
def test_questions_plans_and_not_yet_never_ask_have_you_taken_them(margaret, message, with_diet):
    margaret.diet = DIET if with_diet else []

    result, writes = margaret.say(message)

    assert writes == []
    assert "Now that you've had" not in result["response"]
    assert "Have you taken" not in result["response"]


def test_i_had_breakfast_still_asks(margaret):
    assert "Have you taken them?" in margaret.say("I had breakfast")[0]["response"]


def test_general_question_lists_the_letter_lines(margaret):
    margaret.diet = DIET

    assert margaret.say("what can I eat for breakfast")[0]["response"] == (
        "Your letter says: Do not drink alcohol while you are taking codeine. "
        "Eat plenty of fibre, such as fruit, vegetables and porridge, and drink plenty of water."
    )


def test_general_question_without_diet_advice(margaret):
    assert margaret.say("what can I eat for breakfast")[0]["response"] == (
        "Your letter doesn't give any advice about food. If you're unsure, please ask your care team."
    )


def test_specific_question_quotes_an_avoid_line_and_never_says_yes_or_no(margaret):
    margaret.diet = DIET

    reply = margaret.say("can I have a glass of wine?")[0]["response"]

    assert reply == "Your letter says: Do not drink alcohol while you are taking codeine."


def test_specific_question_not_in_the_letter(margaret):
    margaret.diet = DIET

    reply = margaret.say("can I have pizza?")[0]["response"]

    assert reply.startswith("Your letter doesn't mention pizza. It does say: Eat plenty of fibre")
    assert not reply.lower().startswith(("yes", "no"))


def test_plan_reminds_without_asking(margaret):
    assert margaret.say("I'm about to have breakfast")[0]["response"] == (
        "Remember, your paracetamol, 2 tablets, and your blood thinner, 1 tablet, are taken after breakfast."
    )


def test_not_yet_reminds_without_asking(margaret):
    assert margaret.say("I haven't had breakfast yet")[0]["response"].startswith("Remember, your paracetamol")


def test_a_question_leaves_nothing_for_a_yes_to_record(margaret):
    from app.agent.session import pop_offer

    margaret.say("what can I eat for breakfast", session="q-yes")

    assert pop_offer("q-yes") is None


def test_whats_left_with_breakfast_still_gets_whats_next(margaret):
    reply = margaret.say("What's left? I'm about to have breakfast.")[0]["response"]

    assert reply == "Next is 2 tablets of your paracetamol and 1 tablet of your blood thinner, after breakfast."
