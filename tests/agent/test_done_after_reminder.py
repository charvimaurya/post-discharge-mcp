"""
"Thanks Alexa, I am done with my walk" after the walk reminder records the walk.

A thank-you only acknowledges a reminder when she has NOT said she did it.
Here the model is never called: these turns are answered in code.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import service
from app.agent.session import clear_session

WALK = "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame."
REMINDER = {"checkin_id": "2026-10-23#task_walk#2026-10-23#1", "type": "reminder",
            "occurrence_id": "walk#1", "item_type": "task", "clock_time": "07:30",
            "text": "Good morning, Margaret. You have about thirty minutes until your morning walk."}


@pytest.fixture
def margaret(monkeypatch):
    run = SimpleNamespace(calls=[])
    run.tasks = [
        {"occurrence_id": "walk#1", "task_id": "walk", "description": WALK, "clock_time": "07:30",
         "occurrence_number": 1, "occurrence_total": 2, "status": "pending"},
        {"occurrence_id": "walk#2", "task_id": "walk", "description": WALK, "clock_time": "15:00",
         "occurrence_number": 2, "occurrence_total": 2, "status": "pending"},
    ]
    run.meds = [
        {"occurrence_id": "para#1", "medication_id": "para", "name": "Paracetamol", "dose": "2 tablets",
         "time_of_day_label": "morning", "occurrence_number": 1, "status": "pending"},
    ]

    async def call_tool(name, arguments):
        run.calls.append((name, arguments))
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [dict(t) for t in run.tasks]}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.meds]}
        elif name == "report_task_completed":
            for task in run.tasks:
                if task["occurrence_id"] == arguments["occurrence_id"]:
                    task["status"] = "completed"
            data = {"occurrence_id": arguments["occurrence_id"], "already_completed": False}
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def no_model(**kwargs):
        raise AssertionError("the model should not be needed")

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", no_model)
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T07:45:00+01:00")

    def say(message):
        clear_session("after-reminder")
        result = asyncio.run(service.chat(message, "after-reminder", pending_checkin=REMINDER, first_name="Margaret"))
        writes = [args["occurrence_id"] for name, args in run.calls if name.startswith("report_")]
        run.calls.clear()
        return result["response"], writes

    run.say = say
    return run


@pytest.mark.parametrize("message", [
    "thanks Alexa I am done with my walk",
    "Thanks, I'm done with my walk",
    "I am done with my walk",
    "I'm done with my walk now",
    "Thank you, I've finished my walk",
    "Thanks, all done with my walk",
])
def test_saying_the_walk_is_done_records_it_even_with_a_thank_you(margaret, message):
    reply, writes = margaret.say(message)

    assert writes == ["walk#1"], reply
    assert "Tell me when you're back" not in reply


@pytest.mark.parametrize("message", [
    "Thanks, I'm just getting ready",
    "Okay, thank you",
    "Thanks Alexa",
])
def test_a_plain_thank_you_still_only_acknowledges_the_reminder(margaret, message):
    reply, writes = margaret.say(message)

    assert writes == []
    assert "Tell me when you're back" in reply


@pytest.mark.parametrize("message", [
    "Thanks, I'm not done with my walk yet",
    "I am not done with my walk",
])
def test_not_done_is_never_recorded(margaret, message):
    _, writes = margaret.say(message)

    assert writes == []
