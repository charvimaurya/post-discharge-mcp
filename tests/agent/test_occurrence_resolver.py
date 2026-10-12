"""Which occurrence a completion report is about, with the demo clock. No AWS, no model."""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.agent import service
from app.agent.completion_replies import ask_reply, already_done_reply
from app.agent.occurrence_resolver import names_specific_occurrence, resolve_occurrence
from app.agent.safety import remove_hollow_openers


LONDON = ZoneInfo("Europe/London")
WALK = "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame."
WALK_1 = "task_walk#2026-10-23#1"
WALK_2 = "task_walk#2026-10-23#2"


def at(hhmm):
    hour, minute = map(int, hhmm.split(":"))
    return datetime(2026, 10, 23, hour, minute, tzinfo=LONDON)


def walks(first="pending", second="pending"):
    """Margaret's two walks: clock times from the letter, no time-of-day word."""

    return [
        {"occurrence_id": WALK_1, "task_id": "task_walk", "description": WALK, "clock_time": "07:30",
         "time_of_day_label": None, "occurrence_number": 1, "occurrence_total": 2, "status": first},
        {"occurrence_id": WALK_2, "task_id": "task_walk", "description": WALK, "clock_time": "15:00",
         "time_of_day_label": None, "occurrence_number": 2, "occurrence_total": 2, "status": second},
    ]


def exercises():
    return [
        {"occurrence_id": f"task_ex#2026-10-23#{n}", "task_id": "task_ex",
         "description": "Knee exercises from your physiotherapy sheet", "clock_time": None,
         "time_of_day_label": label, "occurrence_number": n, "status": "pending"}
        for n, label in [(1, "morning"), (2, "afternoon"), (3, "evening")]
    ]


REMINDER = {"checkin_id": f"2026-10-23#{WALK_1}", "occurrence_id": WALK_1, "clock_time": "07:30"}


# ---------- The resolver on its own ----------

def test_reminder_wins():
    r = resolve_occurrence("I'm back from my walk", walks() + exercises(), at("07:00"), REMINDER)
    assert (r.action, r.occurrence["occurrence_id"]) == ("record", WALK_1)


def test_without_reminder_the_due_walk_is_chosen():
    r = resolve_occurrence("I'm back from my walk", walks() + exercises(), at("07:00"))
    assert (r.action, r.occurrence["occurrence_id"]) == ("record", WALK_1)


def test_two_overdue_walks_are_ambiguous():
    r = resolve_occurrence("I'm back from my walk", walks(), at("16:00"))
    assert r.action == "ask"
    assert [o["occurrence_id"] for o in r.choices] == [WALK_1, WALK_2]


def test_first_walk_done_records_the_second():
    r = resolve_occurrence("I'm back from my walk", walks(first="completed"), at("16:00"))
    assert (r.action, r.occurrence["occurrence_id"]) == ("record", WALK_2)


def test_done_walk_is_never_chosen_again():
    r = resolve_occurrence("I've done my walk", walks(first="completed"), at("07:50"))
    assert r.action == "already_done"
    assert r.done["occurrence_id"] == WALK_1
    assert r.next_up["occurrence_id"] == WALK_2


def test_named_occurrence_is_left_to_the_model():
    assert names_specific_occurrence("I'm back from my 7:30 am walk")
    assert names_specific_occurrence("I've done my second walk")
    assert not names_specific_occurrence("Alexa, I'm back from my walk")
    assert resolve_occurrence("I'm back from my 7:30 am walk", walks(), at("16:00")).action == "model"
    assert resolve_occurrence("I've done my second walk", walks(), at("16:00")).action == "model"


def test_a_named_part_of_the_day_is_resolved_in_code():
    # Certain: one walk in the morning, one in the afternoon.
    r = resolve_occurrence("I've done my morning walk", walks(), at("07:00"))
    assert (r.action, r.occurrence["occurrence_id"]) == ("record", WALK_1)

    r = resolve_occurrence("I'm back from my afternoon walk", walks(), at("16:00"))
    assert (r.action, r.occurrence["occurrence_id"]) == ("record", WALK_2)

    # Said in the afternoon, it is still the morning one she means, never the 3 pm walk.
    r = resolve_occurrence("I did my morning walk", walks(), at("15:10"))
    assert (r.action, r.occurrence["occurrence_id"]) == ("record", WALK_1)

    # Not certain: no walk in the evening, or a clock time beside the part of day.
    assert resolve_occurrence("I've done my evening walk", walks(), at("19:00")).action == "model"
    assert resolve_occurrence("I've done my morning walk at 7:30 am", walks(), at("08:00")).action == "model"


def test_a_named_part_already_done_is_not_written_again():
    done = walks()
    done[0]["status"] = "completed"

    r = resolve_occurrence("I've done my morning walk", done, at("09:00"))

    assert r.action == "already_done" and r.done["occurrence_id"] == WALK_1
    assert r.next_up["occurrence_id"] == WALK_2


def test_item_without_clock_time_uses_its_time_of_day():
    r = resolve_occurrence("I've done my knee exercises", exercises(), at("09:00"))
    assert (r.action, r.occurrence["occurrence_id"]) == ("record", "task_ex#2026-10-23#1")


def test_unclear_item_is_left_to_the_model():
    assert resolve_occurrence("I've finished", walks(), at("07:00")).action == "model"


def test_reminded_item_is_used_when_the_item_is_not_named():
    r = resolve_occurrence("I'm back now", walks(), at("07:10"), REMINDER)
    assert (r.action, r.occurrence["occurrence_id"]) == ("record", WALK_1)


def test_ask_names_walks_the_way_people_speak():
    assert ask_reply(walks()) == "Was that your morning walk or your afternoon walk?"


def test_already_done_reply_gives_the_next_time():
    first, second = walks(first="completed")
    assert already_done_reply(first, second, "Margaret") == (
        "Your morning walk is already recorded, Margaret. Your next one is at three o'clock."
    )


def test_hollow_opener_is_removed():
    assert remove_hollow_openers("You're right, your walk is next.") == "Your walk is next."
    assert remove_hollow_openers("Your walk is next.") == "Your walk is next."


# ---------- Whole turns through chat(), with the demo clock ----------

@pytest.fixture
def day(monkeypatch):
    """
    A fake MCP server holding today's occurrences. A report_* write
    marks the occurrence completed. The model must not be called.
    """

    run = SimpleNamespace(tasks=[], calls=[])

    async def call_tool(name, arguments):
        run.calls.append((name, arguments))
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [dict(t) for t in run.tasks]}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": []}
        elif name == "report_task_completed":
            target = next(t for t in run.tasks if t["occurrence_id"] == arguments["occurrence_id"])
            already = target["status"] == "completed"
            target["status"] = "completed"
            data = {"occurrence_id": target["occurrence_id"], "already_completed": already}
        else:
            raise AssertionError(f"unexpected tool {name}")
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def no_model(**kwargs):
        raise AssertionError("the model should not be needed for this report")

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", no_model)

    def say(message, clock, pending_checkin=None, session="resolver"):
        monkeypatch.setenv("DEMO_FIXED_NOW", f"2026-10-23T{clock}:00+01:00")
        result = asyncio.run(service.chat(
            message, f"{session}-{clock}", pending_checkin=pending_checkin, first_name="Margaret",
        ))
        writes = [args["occurrence_id"] for name, args in run.calls if name.startswith("report_")]
        run.calls.clear()
        return result, writes

    run.say = say
    return run


def test_0700_with_reminder_records_walk_one_without_asking(day):
    day.tasks = walks()

    result, writes = day.say("Alexa, I'm back from my walk.", "07:00", REMINDER)

    assert writes == [WALK_1]
    assert result["response"] == (
        "Well done, Margaret, that's your morning walk done. "
        "Next is your afternoon walk at three o'clock."
    )
    write, read = result["tool_trace"][-2:]
    assert write == {"tool": "report_task_completed", "arguments": {"occurrence_id": WALK_1}, "ok": True}
    # next_up shows in Developer view as a read after the write.
    assert read["tool"] == "next_up" and read["ok"] is True


def test_0700_without_reminder_records_walk_one(day):
    day.tasks = walks()

    result, writes = day.say("I'm back from my walk.", "07:00")

    assert writes == [WALK_1]
    assert "Next is your afternoon walk" in result["response"]


def test_1600_both_walks_pending_asks_which(day):
    day.tasks = walks()

    result, writes = day.say("I'm back from my walk.", "16:00")

    assert writes == []
    assert result["response"] == "Was that your morning walk or your afternoon walk?"


def test_1600_first_walk_done_records_the_second(day):
    day.tasks = walks(first="completed")

    result, writes = day.say("I'm back from my walk.", "16:00")

    assert writes == [WALK_2]
    assert result["response"] == (
        "Well done, Margaret, that's your afternoon walk done. That's everything for today."
    )


def test_0750_repeat_report_does_not_tick_the_second_walk(day):
    day.tasks = walks()
    day.say("I'm back from my walk.", "07:30")

    result, writes = day.say("I've done my walk.", "07:50")

    assert writes == []
    assert day.tasks[1]["status"] == "pending"
    assert result["response"] == (
        "Your morning walk is already recorded, Margaret. Your next one is at three o'clock."
    )


def test_no_resolved_reply_says_youre_right_or_screen(day):
    replies = []
    for first, clock, reminder in [
        ("pending", "07:00", REMINDER), ("pending", "07:00", None), ("pending", "16:00", None),
        ("completed", "16:00", None), ("completed", "07:50", None),
    ]:
        day.tasks = walks(first=first)
        replies.append(day.say("I'm back from my walk.", clock, reminder)[0]["response"])

    for reply in replies:
        assert "you're right" not in reply.lower()
        assert "screen" not in reply.lower()
        assert "i need to know" not in reply.lower()


# ---------- "Thanks, I'm just getting ready" after a reminder ----------

def test_getting_ready_after_reminder_is_acknowledged_once(day):
    day.tasks = walks()

    result, writes = day.say("thank you Alexa I'm just getting ready", "07:00", REMINDER)

    assert writes == []
    assert result["response"] == (
        "Lovely. It's the first of your two walks today. Tell me when you're back."
    )
    # The reminder is not repeated.
    assert "half past seven" not in result["response"]
    assert "good morning" not in result["response"].lower()


def test_not_yet_after_reminder_is_acknowledged(day):
    day.tasks = walks()

    result, writes = day.say("Not yet, Alexa", "07:05", REMINDER)

    assert writes == []
    assert result["response"].startswith("Lovely. It's the first of your two walks today.")


def test_a_question_after_reminder_still_goes_to_the_model(day, monkeypatch):
    day.tasks = walks()
    asked = []

    def model(**kwargs):
        asked.append(True)
        return {"output": {"message": {"role": "assistant", "content": [{"text": "It's five to ten minutes."}]}},
                "stopReason": "end_turn"}

    async def no_tools():
        return {"tools": []}

    monkeypatch.setattr(service.bedrock, "converse", model)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")

    result, writes = day.say("Thanks. How long should the walk be?", "07:00", REMINDER)

    assert asked and writes == []
    assert result["response"] == "It's five to ten minutes."
