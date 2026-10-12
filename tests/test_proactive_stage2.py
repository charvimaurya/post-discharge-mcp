"""Stage 2: the follow-on task (ice pack after exercises). No AWS, no model."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.agent import service
from app.agent.session import clear_session
from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan
from app.reminders.engine import choose_checkin


LONDON = ZoneInfo("Europe/London")
ICE = "Ice pack on the knee for 20 minutes after each set of exercises."
EXERCISES = "Knee exercises from your physiotherapy sheet: three times a day (morning, afternoon, evening)."
WALK = "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame."
LETTER = f"DAILY ACTIVITIES\n{EXERCISES}\n{WALK}\n{ICE}\nRest with your leg raised between activities.\n"


# ---------- Extraction ----------

def _extracted(follow_on):
    return {"discharge_date": "2026-10-16", "tasks": [
        {"description": EXERCISES, "time_of_day": ["morning", "afternoon", "evening"], "times_per_day": 3,
         "source": {"snippet": EXERCISES, "page": 1}},
        {"description": WALK, "clock_times": ["07:30", "15:00"], "times_per_day": 2,
         "source": {"snippet": WALK, "page": 1}},
        {"description": ICE, "source": {"snippet": ICE, "page": 1}, "follow_on": follow_on},
    ]}


def _plan(follow_on, letter=LETTER):
    state = normalize_recovery_plan(_extracted(follow_on), patient_id="p", document_id="d")
    return validate_recovery_plan(state, document_text=letter)


def _ice(state):
    return next(t for t in state.tasks if t.description == ICE)


GOOD = {"after_task": "each set of exercises", "duration_minutes": 20, "source": {"snippet": ICE, "page": 1}}


def test_follow_on_is_linked_to_the_exercises_task():
    state = _plan(GOOD)
    exercises = next(t for t in state.tasks if t.description == EXERCISES)

    assert _ice(state).follow_on.after_task_id == exercises.id
    assert _ice(state).follow_on.duration_minutes == 20
    assert _ice(state).follow_on.source.snippet == ICE


def test_snippet_not_in_the_letter_is_dropped():
    reworded = dict(GOOD, source={"snippet": "Put ice on your knee for 20 minutes after exercising.", "page": 1})

    assert _ice(_plan(reworded)).follow_on is None


def test_minutes_not_in_the_snippet_are_dropped():
    assert _ice(_plan(dict(GOOD, duration_minutes=30))).follow_on is None


def test_follow_on_pointing_at_no_task_is_dropped():
    assert _ice(_plan(dict(GOOD, after_task="each swim"))).follow_on is None


def test_no_follow_on_when_the_letter_gives_none():
    assert _ice(_plan(None)).follow_on is None


# ---------- Her replies ----------

def _day():
    tasks = [
        *[{"occurrence_id": f"ex#2026-10-23#{n}", "task_id": "ex", "description": EXERCISES,
           "time_of_day_label": s, "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "afternoon"), (3, "evening")]],
        *[{"occurrence_id": f"walk#2026-10-23#{n}", "task_id": "walk", "description": WALK, "clock_time": t,
           "occurrence_number": n, "status": "pending"} for n, t in [(1, "07:30"), (2, "15:00")]],
        {"occurrence_id": "ice#2026-10-23#1", "task_id": "ice", "description": ICE, "occurrence_number": 1,
         "status": "pending",
         "follow_on": {"after_task_id": "ex", "duration_minutes": 20,
                       "source": {"snippet": ICE, "page": 1, "document_id": "doc"}}},
    ]
    return tasks


@pytest.fixture
def margaret(monkeypatch):
    run = SimpleNamespace(tasks=_day(), calls=[], scheduled=[])

    async def call_tool(name, arguments):
        run.calls.append((name, arguments))
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [dict(t) for t in run.tasks]}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": []}
        elif name == "report_task_completed":
            for t in run.tasks:
                if t["occurrence_id"] == arguments["occurrence_id"]:
                    t["status"] = "completed"
            data = {"occurrence_id": arguments["occurrence_id"], "already_completed": False}
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def no_model(**kwargs):
        raise AssertionError("the model should not be needed")

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", no_model)
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T09:10:00+01:00")

    def say(message, session="ice", fresh=True):
        if fresh:
            clear_session(session)
        result = asyncio.run(service.chat(message, session, first_name="Margaret",
                                          schedule_checkin=run.scheduled.append))
        writes = [args["occurrence_id"] for name, args in run.calls if name.startswith("report_")]
        run.calls.clear()
        return result, writes

    run.say = say
    return run


def test_exercises_done_adds_the_ice_pack_line_with_the_letter_as_source(margaret):
    result, writes = margaret.say("I've done my knee exercises")

    assert writes == ["ex#2026-10-23#1"]
    assert result["response"] == (
        "Well done, Margaret, that's your morning exercises done. "
        "Your letter says to put an ice pack on your knee for 20 minutes now. "
        "Shall I remind you when it's time to take it off?"
    )
    assert result["source"]["text"] == ICE
    assert result["source"]["highlight"] == ICE
    assert result["source"]["page"] == 1


def test_yes_schedules_the_take_it_off_checkin_20_minutes_later(margaret):
    margaret.say("I've done my knee exercises", session="ice-yes")

    result, writes = margaret.say("Yes please", session="ice-yes", fresh=False)

    assert writes == []
    assert result["response"] == "Okay, Margaret. I'll remind you in twenty minutes."
    (entry,) = margaret.scheduled
    assert entry == {
        "checkin_id": "2026-10-23#follow_on#ex#2026-10-23#1",
        "due_at": "2026-10-23T09:30:00+01:00",
        "type": "follow_on",
        "text": "Time to take the ice pack off your knee, Margaret.",
        "occurrence_id": "ice#2026-10-23#1",
        "item_type": "task",
    }
    assert result["tool_trace"][-1]["tool"] == "schedule_checkin"


def test_no_schedules_nothing(margaret):
    margaret.say("I've done my knee exercises", session="ice-no")

    result, _ = margaret.say("No thanks", session="ice-no", fresh=False)

    assert result["response"] == "That's fine, Margaret."
    assert margaret.scheduled == []


def test_walk_done_has_no_ice_pack_line(margaret):
    result, writes = margaret.say("I'm back from my walk")

    assert writes == ["walk#2026-10-23#1"]
    assert "ice pack" not in result["response"].lower()
    assert result["source"] is None


def test_replies_are_tidy(margaret):
    reply = margaret.say("I've done my knee exercises")[0]["response"]
    assert not reply.startswith(("—", "-"))
    assert "screen" not in reply.lower() and "you're right" not in reply.lower()


# ---------- The scheduled check-in fires ----------

def test_the_take_it_off_checkin_fires_when_due_and_outranks_a_walk_reminder():
    tasks = _day()
    for t in tasks:
        if t["occurrence_id"] in ("ex#2026-10-23#2", "walk#2026-10-23#1"):
            t["status"] = "completed"
    entry = {"checkin_id": "2026-10-23#follow_on#ex#2026-10-23#2", "due_at": "2026-10-23T14:35:00+01:00",
             "type": "follow_on", "text": "Time to take the ice pack off your knee, Margaret.",
             "occurrence_id": "ice#2026-10-23#1", "item_type": "task"}
    real = datetime(2030, 1, 1, tzinfo=timezone.utc)

    early = choose_checkin({"scheduled_checkins": [entry]}, tasks, [], datetime(2026, 10, 23, 14, 30, tzinfo=LONDON),
                           real_now_utc=real, first_name="Margaret")
    # 14:31 is also the 3 pm walk's reminder window; the follow-on wins.
    due = choose_checkin({"scheduled_checkins": [entry]}, tasks, [], datetime(2026, 10, 23, 14, 35, tzinfo=LONDON),
                         real_now_utc=real, first_name="Margaret")

    assert early.checkin.type == "reminder"
    assert due.checkin.type == "follow_on"
    assert due.checkin.text == "Time to take the ice pack off your knee, Margaret."
