"""After a completion, and for "what's next?", AfterWard names what is next across tasks AND medicines."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.agent import service
from app.agent.next_up import build_next_up, build_steps, letter_wording
from app.agent.session import add_message, clear_session


LONDON = ZoneInfo("Europe/London")
WALK = "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame."
MORNING_AFTER_BREAKFAST = "Take the morning dose after breakfast."


def _day():
    """Margaret's day, as get_today_tasks / get_medications return it (fresh copies)."""

    tasks = [
        {"occurrence_id": "walk#1", "task_id": "walk", "description": WALK, "clock_time": "07:30",
         "occurrence_number": 1, "status": "pending"},
        {"occurrence_id": "walk#2", "task_id": "walk", "description": WALK, "clock_time": "15:00",
         "occurrence_number": 2, "status": "pending"},
        *[
            {"occurrence_id": f"ex#{n}", "task_id": "ex", "description": "Knee exercises from your physiotherapy sheet",
             "time_of_day_label": label, "occurrence_number": n, "status": "pending"}
            for n, label in [(1, "morning"), (2, "afternoon"), (3, "evening")]
        ],
    ]
    medications = [
        *[
            {"occurrence_id": f"para#{n}", "medication_id": "para", "name": "Paracetamol", "dose": "2 tablets",
             "instructions": MORNING_AFTER_BREAKFAST, "time_of_day_label": label,
             "occurrence_number": n, "status": "pending"}
            for n, label in [(1, "morning"), (2, "midday"), (3, "evening"), (4, "bedtime")]
        ],
        *[
            {"occurrence_id": f"apix#{n}", "medication_id": "apix", "name": "Apixaban", "dose": "1 tablet",
             "instructions": MORNING_AFTER_BREAKFAST, "time_of_day_label": label,
             "occurrence_number": n, "status": "pending"}
            for n, label in [(1, "morning"), (2, "evening")]
        ],
        {"occurrence_id": "cod#1", "medication_id": "cod", "name": "Codeine", "dose": "1 tablet",
         "as_needed": True, "occurrence_number": 1, "status": "pending"},
    ]
    return tasks, medications


def at(hhmm):
    hour, minute = map(int, hhmm.split(":"))
    return datetime(2026, 10, 23, hour, minute, tzinfo=LONDON)


def done(items, *ids):
    for item in items:
        if item["occurrence_id"] in ids:
            item["status"] = "completed"


# ---------- next_up on its own ----------

def test_medicines_due_after_breakfast_come_before_the_afternoon_walk():
    tasks, meds = _day()
    done(tasks, "walk#1")

    order = [i.occurrence["occurrence_id"] for i in build_next_up(tasks, meds, at("07:50"))]

    assert order.index("para#1") < order.index("walk#2")
    assert order.index("apix#1") < order.index("walk#2")
    first_step = build_steps(build_next_up(tasks, meds, at("07:50")))[0]
    assert [item.occurrence["occurrence_id"] for item in first_step] == ["para#1", "apix#1"]
    assert first_step[0].when == "after breakfast"


def test_due_now_and_later_are_marked():
    tasks, meds = _day()
    by_id = {i.occurrence["occurrence_id"]: i for i in build_next_up(tasks, meds, at("07:50"))}

    assert by_id["para#1"].status == "due now"
    assert by_id["para#2"].status == "later"
    assert by_id["walk#2"].status == "later"


def test_taken_and_as_needed_medicines_are_never_next():
    tasks, meds = _day()
    done(meds, "para#1")

    ids = [i.occurrence["occurrence_id"] for i in build_next_up(tasks, meds, at("07:50"))]

    assert "para#1" not in ids
    assert "cod#1" not in ids


def test_letter_wording_is_used_only_where_the_letter_gives_it():
    para = _day()[1][0]

    assert letter_wording(para) == {"morning": "after breakfast"}
    assert letter_wording({"instructions": "Take the midday dose after lunch."}) == {"midday": "after lunch"}


def test_no_clock_time_is_invented_for_medicines():
    tasks, meds = _day()

    for item in build_next_up(tasks, meds, at("07:50")):
        if item.is_medication:
            assert ":" not in item.when and "o'clock" not in item.when and "half past" not in item.when


# ---------- Whole turns through chat() ----------

@pytest.fixture
def margaret(monkeypatch):
    """Fake MCP holding Margaret's day; the model must not be needed."""

    run = SimpleNamespace(calls=[])
    run.tasks, run.meds = _day()

    async def call_tool(name, arguments):
        run.calls.append((name, arguments))
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [dict(t) for t in run.tasks]}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.meds]}
        elif name.startswith("report_"):
            pool = run.tasks if name == "report_task_completed" else run.meds
            done(pool, arguments["occurrence_id"])
            data = {"occurrence_id": arguments["occurrence_id"], "already_completed": False}
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def no_model(**kwargs):
        raise AssertionError("the model should not be needed")

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", no_model)

    def say(message, clock, session="next-up", keep_history=False):
        if not keep_history:
            clear_session(session)
        monkeypatch.setenv("DEMO_FIXED_NOW", f"2026-10-23T{clock}:00+01:00")
        result = asyncio.run(service.chat(message, session, first_name="Margaret"))
        writes = [args["occurrence_id"] for name, args in run.calls if name.startswith("report_")]
        run.calls.clear()
        return result, writes

    run.say = say
    return run


def _no_list(reply):
    """One step: no digits, no counts, no offer to read a list."""

    assert not any(ch.isdigit() for ch in reply), reply
    assert "more things" not in reply and "read them" not in reply and "more thing" not in reply


def test_back_from_walk_names_only_the_after_breakfast_medicines(margaret):
    result, writes = margaret.say("Alexa, I'm back from my walk.", "08:15")
    reply = result["response"]

    assert writes == ["walk#1"]
    assert reply == (
        "Well done, Margaret, that's your morning walk done. "
        "Next is your paracetamol and blood thinner, after breakfast."
    )
    _no_list(reply)
    assert [t["tool"] for t in result["tool_trace"]][-1] == "next_up"


def test_and_after_that_moves_one_step_each_time(margaret):
    margaret.say("I'm back from my walk.", "08:15", session="steps")

    first = margaret.say("and after that?", "08:15", session="steps", keep_history=True)[0]["response"]
    second = margaret.say("what's after that?", "08:15", session="steps", keep_history=True)[0]["response"]

    assert first == "After that, your knee exercises this morning."
    assert second == "After that, your paracetamol, at midday."
    _no_list(first)


def test_a_new_completion_resets_the_pointer(margaret):
    margaret.say("I'm back from my walk.", "08:15", session="reset")
    margaret.say("and after that?", "08:15", session="reset", keep_history=True)

    margaret.say("I've done my knee exercises", "08:20", session="reset", keep_history=True)
    after = margaret.say("and after that?", "08:20", session="reset", keep_history=True)[0]["response"]

    # The step named after the exercises was the breakfast medicines; one on from there is midday.
    assert after == "After that, your paracetamol, at midday."


def test_whats_next_names_only_the_next_step(margaret):
    done(margaret.tasks, "walk#1")

    reply = margaret.say("What's next?", "08:15")[0]["response"]

    assert reply == "Next is your paracetamol and blood thinner, after breakfast."


def test_at_1240_with_the_morning_done_the_midday_medicine_is_next(margaret):
    done(margaret.tasks, "walk#1", "ex#1")
    done(margaret.meds, "para#1", "apix#1")
    margaret.meds[1]["instructions"] = "Take the midday dose after lunch."

    result, _ = margaret.say("What do I need to do now?", "12:40")

    assert result["response"] == "Next is your paracetamol, after lunch."


def test_taken_medicines_and_as_needed_ones_are_never_named(margaret):
    done(margaret.tasks, "walk#1")
    done(margaret.meds, "para#1")

    reply = margaret.say("What's next?", "08:15")[0]["response"]

    assert reply == "Next is your blood thinner, after breakfast."
    assert "codeine" not in reply.lower()


def test_whats_left_today_is_grouped_by_part_of_day(margaret):
    done(margaret.tasks, "walk#1")

    reply = margaret.say("What's left today?", "08:15")[0]["response"]

    assert reply == (
        "This morning, your paracetamol, blood thinner and knee exercises. "
        "This afternoon, your paracetamol, walk and knee exercises. "
        "This evening, your blood thinner, paracetamol and knee exercises."
    )
    assert len([s for s in reply.split(". ") if s]) <= 4
    _no_list(reply)
    assert "codeine" not in reply.lower()


def test_what_else_do_i_have_today_is_the_same_summary(margaret):
    done(margaret.tasks, "walk#1")

    assert margaret.say("What else do I have today?", "08:15")[0]["response"].startswith("This morning, your")


def test_everything_done(margaret):
    done(margaret.tasks, *[t["occurrence_id"] for t in margaret.tasks])
    done(margaret.meds, *[m["occurrence_id"] for m in margaret.meds])

    for question in ("What's next?", "What's left today?"):
        result, writes = margaret.say(question, "21:45")
        assert writes == []
        assert result["response"] == "That's everything for today, Margaret. Well done."


def test_last_item_done_says_thats_everything(margaret):
    done(margaret.tasks, *[t["occurrence_id"] for t in margaret.tasks if t["occurrence_id"] != "walk#2"])
    done(margaret.meds, *[m["occurrence_id"] for m in margaret.meds])

    result, writes = margaret.say("I'm back from my walk.", "16:00")

    assert writes == ["walk#2"]
    assert result["response"] == "Well done, Margaret, that's your afternoon walk done. That's everything for today."


def test_no_reply_has_a_screen_youre_right_or_a_dash(margaret):
    replies = [
        margaret.say("I'm back from my walk.", "07:50")[0]["response"],
        margaret.say("What's next?", "07:50")[0]["response"],
        margaret.say("I've taken my paracetamol", "07:55")[0]["response"],
    ]
    for reply in replies:
        assert "screen" not in reply.lower()
        assert "you're right" not in reply.lower()
        assert not reply.startswith(("—", "-"))
