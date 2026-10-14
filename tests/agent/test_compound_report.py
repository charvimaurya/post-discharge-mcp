"""
"I did my walk and I took my paracetamol": one message, two reports.

Both are recorded and both are named in the reply; the next step is given
once and is never something she just reported. Real agent, fake plan, and a
model that must not be needed. Demo clock 08:15.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import service
from app.agent.session import clear_session


WALK = "walk#2026-10-23#1"
KNEE = "knee#2026-10-23#1"
PARA = "para#2026-10-23#1"
APIX = "apix#2026-10-23#1"


@pytest.fixture
def agent(monkeypatch):
    run = SimpleNamespace(saved=[], model_calls=0, session="s-compound")
    clear_session(run.session)
    run.tasks = [
        {"occurrence_id": WALK, "task_id": "walk", "clock_time": "07:30", "occurrence_number": 1, "status": "pending",
         "description": "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame."},
        {"occurrence_id": "walk#2026-10-23#2", "task_id": "walk", "clock_time": "15:00", "occurrence_number": 2,
         "status": "pending",
         "description": "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame."},
        {"occurrence_id": KNEE, "task_id": "knee", "time_of_day_label": "morning", "occurrence_number": 1,
         "status": "pending", "description": "Knee exercises from your physiotherapy sheet: three times a day."},
    ]
    run.meds = [
        {"occurrence_id": PARA, "medication_id": "para", "name": "Paracetamol", "dose": "2 tablets",
         "instructions": "Take the morning dose after breakfast.", "time_of_day_label": "morning",
         "occurrence_number": 1, "status": "pending"},
        {"occurrence_id": APIX, "medication_id": "apix", "name": "Apixaban", "dose": "1 tablet",
         "instructions": "Take the morning dose after breakfast.", "time_of_day_label": "morning",
         "occurrence_number": 1, "status": "pending"},
    ]

    async def call_tool(name, arguments):
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [dict(t) for t in run.tasks]}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.meds]}
        elif name in ("report_task_completed", "report_medication_taken"):
            run.saved.append((name, arguments["occurrence_id"]))
            for item in run.tasks + run.meds:
                if item["occurrence_id"] == arguments["occurrence_id"]:
                    item["status"] = "completed"
            data = {"occurrence_id": arguments["occurrence_id"]}
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def converse(**kwargs):
        run.model_calls += 1
        message = {"role": "assistant", "content": [{"text": "Thank you."}]}
        return {"output": {"message": message}, "stopReason": "end_turn"}

    async def no_tools():
        return {"tools": []}

    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T08:15:00+01:00")
    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")

    run.say = lambda message: asyncio.run(service.chat(message, run.session, first_name="Margaret"))
    return run


def test_walk_and_paracetamol_are_both_recorded_and_both_named(agent):
    reply = agent.say("I did my walk and I took my paracetamol")

    assert agent.saved == [("report_task_completed", WALK), ("report_medication_taken", PARA)]
    assert reply["response"] == (
        "Well done, Margaret, that's your morning walk done. "
        "I've also marked your morning paracetamol, 2 tablets, as taken. "
        "Next is 1 tablet of your blood thinner, after breakfast."
    )
    assert agent.model_calls == 0


def test_the_next_step_is_never_something_she_just_reported(agent):
    reply = agent.say("I did my walk and I took my paracetamol")["response"]

    next_step = reply.split("Next is", 1)[1]
    assert "paracetamol" not in next_step and "walk" not in next_step


@pytest.mark.parametrize("message", [
    "I've taken my paracetamol and also done my morning walk",
    "I have done my morning walk and taken my morning paracetamol",
    "I took my paracetamol and I did my walk",
    "I've taken my paracetamol, and I'm back from my walk",
    "I finished my walk then took my paracetamol",
])
def test_either_order_and_other_wording(agent, message):
    agent.say(message)

    assert sorted(agent.saved) == sorted([("report_task_completed", WALK), ("report_medication_taken", PARA)])


def test_three_things_in_one_report(agent):
    reply = agent.say("I did my walk, took my paracetamol and my blood thinner")

    assert sorted(agent.saved) == sorted([
        ("report_task_completed", WALK), ("report_medication_taken", PARA), ("report_medication_taken", APIX),
    ])
    for named in ("walk", "paracetamol", "blood thinner"):
        assert named in reply["response"]


def test_a_part_that_is_already_done_is_not_written_again(agent):
    agent.tasks[0]["status"] = "completed"

    reply = agent.say("I did my walk and I took my paracetamol")

    # Only the 07:30 walk was meant: the 3 pm walk is never ticked for it.
    assert ("report_medication_taken", PARA) in agent.saved
    assert ("report_task_completed", "walk#2026-10-23#2") not in agent.saved
    assert "paracetamol" in reply["response"]


def test_less_than_the_letters_dose_in_one_part_saves_nothing_for_that_medicine(agent):
    agent.say("I did my walk and I took one paracetamol tablet")

    assert ("report_medication_taken", PARA) not in agent.saved


def test_a_report_of_one_thing_is_unchanged(agent):
    reply = agent.say("I'm back from my walk")

    assert agent.saved == [("report_task_completed", WALK)]
    assert reply["response"].startswith("Well done, Margaret, that's your morning walk done.")


def test_a_no_in_the_message_still_records_nothing(agent):
    agent.say("I did my walk but I haven't taken my paracetamol")

    assert ("report_medication_taken", PARA) not in agent.saved
