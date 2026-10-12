"""Stage 1: shared check-in rules and the missed-dose check. No AWS, no model."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.agent import service
from app.agent.session import add_message, clear_session
from app.reminders.engine import choose_checkin
from lambdas.reminder_checker import handler as checker


LONDON = ZoneInfo("Europe/London")
REAL_NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
WALK = "Walking: one short walk of 5 to 10 minutes, twice a day, using your walking frame."


def at(hhmm, day="2026-10-23"):
    hour, minute = map(int, hhmm.split(":"))
    y, m, d = map(int, day.split("-"))
    return datetime(y, m, d, hour, minute, tzinfo=LONDON)


def day(date="2026-10-23"):
    """Margaret's day: walks, paracetamol x4, apixaban x2, codeine only if needed."""

    tasks = [
        {"occurrence_id": f"walk#{date}#{n}", "task_id": "walk", "description": WALK, "clock_time": t,
         "occurrence_number": n, "status": "pending"}
        for n, t in [(1, "07:30"), (2, "15:00")]
    ]
    meds = [
        *[{"occurrence_id": f"para#{date}#{n}", "medication_id": "para", "name": "Paracetamol",
           "dose": "2 tablets", "time_of_day_label": s, "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "midday"), (3, "evening"), (4, "bedtime")]],
        *[{"occurrence_id": f"apix#{date}#{n}", "medication_id": "apix", "name": "Apixaban",
           "dose": "1 tablet", "time_of_day_label": s, "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "evening")]],
        {"occurrence_id": f"cod#{date}#1", "medication_id": "cod", "name": "Codeine",
         "as_needed": True, "occurrence_number": 1, "status": "pending"},
    ]
    return tasks, meds


def done(items, *ids):
    for item in items:
        if item["occurrence_id"] in ids:
            item["status"] = "completed"


def choose(state, tasks, meds, now, real_now=REAL_NOW):
    return choose_checkin(state, tasks, meds, now, real_now_utc=real_now, first_name="Margaret")


# ---------- The missed-dose check ----------

def test_0905_morning_apixaban_not_done_makes_a_missed_dose_checkin():
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")
    done(meds, "para#2026-10-23#1")

    decision = choose({}, tasks, meds, at("09:05"))

    assert decision.checkin.type == "missed_dose"
    assert decision.checkin.occurrence_id == "apix#2026-10-23#1"
    assert decision.checkin.checkin_id == "2026-10-23#missed_dose#apix#2026-10-23#1"
    assert decision.checkin.text == (
        "Margaret, I haven't heard about your blood thinner this morning. Have you taken it?"
    )


def test_already_taken_means_no_checkin():
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")
    done(meds, "para#2026-10-23#1", "apix#2026-10-23#1")

    assert choose({}, tasks, meds, at("09:05")).checkin is None


def test_as_needed_medicine_is_never_asked_about():
    tasks, meds = day()
    done(tasks, *[t["occurrence_id"] for t in tasks])
    done(meds, *[m["occurrence_id"] for m in meds if not m.get("as_needed")])

    for clock in ("09:05", "13:40", "19:10"):
        assert choose({}, tasks, meds, at(clock)).checkin is None


def test_not_before_an_hour_after_the_slot_starts():
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")

    # 08:59: still the reminder for the morning medicines, not yet "have you taken it?".
    assert choose({}, tasks, meds, at("08:59")).checkin.type == "medicine"
    assert choose({}, tasks, meds, at("09:00")).checkin.type == "missed_dose"


def test_morning_dose_is_not_asked_about_once_midday_has_started():
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")

    # 12:40: the morning doses are untaken, but midday has begun; midday's own check waits until 13:30.
    # Only the reminder for the midday medicine is inside its window.
    decision = choose({}, tasks, meds, at("12:40"))
    assert decision.checkin.type == "medicine" and decision.checkin.slot == "midday"
    assert not [c for c in decision.candidates if c.type == "missed_dose"]


def test_evening_says_this_evening_and_never_a_clock_time():
    tasks, meds = day()
    done(tasks, *[t["occurrence_id"] for t in tasks])
    done(meds, "para#2026-10-23#1", "para#2026-10-23#2", "apix#2026-10-23#1", "para#2026-10-23#3")

    checkin = choose({}, tasks, meds, at("19:05")).checkin

    assert checkin.text == "Margaret, I haven't heard about your blood thinner this evening. Have you taken it?"
    assert ":" not in checkin.text and "o'clock" not in checkin.text


# ---------- Shared rules ----------

def test_no_repeat_of_a_checkin_already_made_today():
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")
    done(meds, "para#2026-10-23#1")
    state = {"checkins_today_date": "2026-10-23",
             "checkins_today_ids": ["2026-10-23#missed_dose#apix#2026-10-23#1"]}

    decision = choose(state, tasks, meds, at("09:30"))

    assert decision.checkin is None
    assert decision.reason == "already_reminded"


def test_one_checkin_at_a_time():
    tasks, meds = day()
    assert choose({"pending_checkin": {"checkin_id": "x"}}, tasks, meds, at("09:05")).reason == "checkin_waiting"


@pytest.mark.parametrize("clock", ["21:00", "23:30", "02:00", "06:59"])
def test_quiet_hours(clock):
    tasks, meds = day()
    assert choose({}, tasks, meds, at(clock)).reason == "quiet_hours"


def test_not_while_she_is_chatting():
    tasks, meds = day()
    recent = {"last_chat_at": (REAL_NOW - timedelta(seconds=60)).isoformat()}
    earlier = {"last_chat_at": (REAL_NOW - timedelta(minutes=3)).isoformat()}

    assert choose(recent, tasks, meds, at("09:05")).reason == "recent_chat"
    assert choose(earlier, tasks, meds, at("09:05")).checkin is not None


def test_daily_limit():
    tasks, meds = day()
    state = {"checkins_today_date": "2026-10-23", "checkins_today_ids": [f"k{n}" for n in range(6)]}

    assert choose(state, tasks, meds, at("09:05")).reason == "daily_limit"


def test_limit_counts_today_only():
    tasks, meds = day()
    state = {"checkins_today_date": "2026-10-22", "checkins_today_ids": [f"k{n}" for n in range(6)]}

    assert choose(state, tasks, meds, at("09:05")).checkin is not None


def test_missed_dose_outranks_a_walk_reminder():
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")
    done(meds, "para#2026-10-23#1", "apix#2026-10-23#1")

    # 14:31: the 3 pm walk reminder is due, and the midday paracetamol is an hour late.
    decision = choose({}, tasks, meds, at("14:31"))

    assert decision.checkin.type == "missed_dose"
    assert decision.checkin.occurrence_id == "para#2026-10-23#2"
    assert {c.type for c in decision.candidates} == {"missed_dose", "reminder"}


def test_scheduled_checkin_fires_when_due_and_not_before():
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")
    done(meds, "para#2026-10-23#1")
    entry = {"checkin_id": "2026-10-23#missed_dose#apix#2026-10-23#1#recheck", "type": "missed_dose",
             "due_at": at("09:35").isoformat(), "text": "Just checking again, Margaret.",
             "occurrence_id": "apix#2026-10-23#1", "recheck": True}
    state = {"scheduled_checkins": [entry], "checkins_today_date": "2026-10-23",
             "checkins_today_ids": ["2026-10-23#missed_dose#apix#2026-10-23#1"]}

    assert choose(state, tasks, meds, at("09:20")).checkin is None
    fired = choose(state, tasks, meds, at("09:36")).checkin
    assert fired.checkin_id == entry["checkin_id"] and fired.recheck and fired.scheduled_id

    done(meds, "apix#2026-10-23#1")
    assert choose(state, tasks, meds, at("09:36")).checkin is None


def test_every_checkin_has_type_occurrence_and_checkin_id():
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")

    pending = choose({}, tasks, meds, at("09:05")).checkin.as_pending("2026-10-23", at("09:05"))

    assert pending["type"] == "missed_dose"
    assert pending["occurrence_id"] and pending["checkin_id"]


# ---------- The checker, twice in a row ----------

def test_checker_makes_it_once_and_not_on_the_next_run(monkeypatch):
    tasks, meds = day()
    done(tasks, "walk#2026-10-23#1")
    done(meds, "para#2026-10-23#1")
    state = {"first_name": "Margaret", "timezone": "Europe/London"}

    def save(patient_id, pending, key, *, today=None, max_per_day=None, scheduled_checkins=None):
        if state.get("pending_checkin") or key in state.get("checkins_today_ids", []):
            return False
        state.update(pending_checkin=pending, last_checkin_key=key, checkins_today_date=today,
                     checkins_today_ids=state.get("checkins_today_ids", []) + [key])
        return True

    monkeypatch.setattr(checker, "get_recovery_state", lambda patient_id: state)
    monkeypatch.setattr(checker, "get_today_tasks", lambda patient_id, date: tasks)
    monkeypatch.setattr(checker, "get_medications", lambda patient_id, date: meds)
    monkeypatch.setattr(checker, "save_pending_checkin", save)

    first = checker.handler({"demo_now": "2026-10-23T09:05:00+01:00"}, None)
    assert first["created"] is True and first["pending_checkin"]["type"] == "missed_dose"

    state.pop("pending_checkin")  # she replied
    second = checker.handler({"demo_now": "2026-10-23T09:10:00+01:00"}, None)
    assert second == {"created": False, "reason": "already_reminded"}


# ---------- Her replies ----------

PENDING = {"checkin_id": "2026-10-23#missed_dose#apix#2026-10-23#1", "type": "missed_dose",
           "occurrence_id": "apix#2026-10-23#1", "item_type": "medication", "slot": "morning",
           "text": "Margaret, I haven't heard about your blood thinner this morning. Have you taken it?"}

NO_MISSED_DOSE_LINE = {"chunk_id": "c1", "document_id": "doc", "page": 1,
                       "text": "3.\nApixaban 2.5 mg tablets. Take 1 tablet twice a day (morning and evening). "
                               "Take the morning dose after\nbreakfast. Continue as directed."}


@pytest.fixture
def margaret(monkeypatch):
    run = SimpleNamespace(calls=[], scheduled=[], letter=[NO_MISSED_DOSE_LINE])
    run.tasks, run.meds = day()
    done(run.tasks, "walk#2026-10-23#1")
    done(run.meds, "para#2026-10-23#1")

    async def call_tool(name, arguments):
        run.calls.append((name, arguments))
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [dict(t) for t in run.tasks]}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.meds]}
        elif name == "report_medication_taken":
            done(run.meds, arguments["occurrence_id"])
            data = {"occurrence_id": arguments["occurrence_id"], "already_completed": False}
        elif name == "search_discharge_instructions":
            data = run.letter
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def no_model(**kwargs):
        raise AssertionError("the model should not be needed")

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", no_model)
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T09:05:00+01:00")

    def say(message, pending=PENDING, session="missed", fresh=True):
        if fresh:
            clear_session(session)
        result = asyncio.run(service.chat(
            message, session, pending_checkin=pending, first_name="Margaret",
            schedule_checkin=run.scheduled.append,
        ))
        writes = [args["occurrence_id"] for name, args in run.calls if name.startswith("report_")]
        run.calls.clear()
        return result, writes

    run.say = say
    return run


def test_no_writes_nothing_and_offers_one_recheck(margaret):
    result, writes = margaret.say("No, not yet")

    assert writes == []
    assert result["response"] == "That's okay, Margaret. Would you like me to remind you again in 30 minutes?"
    assert any(step.get("blocked") for step in result["tool_trace"])


def test_yes_to_the_recheck_schedules_one_checkin_30_minutes_later(margaret):
    margaret.say("No, not yet", session="recheck")

    result, writes = margaret.say("Yes please", pending=None, session="recheck", fresh=False)

    assert writes == []
    assert result["response"] == "Okay, Margaret. I'll check with you again in 30 minutes."
    (entry,) = margaret.scheduled
    assert entry["type"] == "missed_dose" and entry["occurrence_id"] == "apix#2026-10-23#1"
    assert entry["due_at"] == "2026-10-23T09:35:00+01:00"
    assert entry["recheck"] is True
    assert result["tool_trace"][-1]["tool"] == "schedule_checkin"


def test_no_second_recheck(margaret):
    result, writes = margaret.say("No", pending=dict(PENDING, recheck=True))

    assert writes == []
    assert result["response"] == "That's okay, Margaret. Your blood thinner is still in today's plan."
    assert margaret.scheduled == []


@pytest.mark.parametrize("answer", ["Yes", "Yes, I have", "I took it"])
def test_yes_records_that_dose_only(margaret, answer):
    result, writes = margaret.say(answer)

    assert writes == ["apix#2026-10-23#1"]
    assert result["response"].startswith("Thank you, Margaret, I've marked your morning blood thinner, 1 tablet, as taken.")


@pytest.mark.parametrize("question", ["Should I take two?", "What if I missed it?"])
def test_dose_questions_are_answered_only_from_the_letter(margaret, question):
    result, writes = margaret.say(question)

    assert writes == []
    assert result["response"] == service.MISSED_DOSE_NOT_IN_LETTER
    assert [t["tool"] for t in result["tool_trace"]][-1] == "search_discharge_instructions"
    assert "two" not in result["response"].lower().replace("take two", "")


def test_a_letter_line_about_missed_doses_is_quoted_word_for_word(margaret):
    margaret.letter = [{"chunk_id": "c9", "document_id": "doc", "page": 2,
                        "text": "MEDICINES\nIf you miss a dose of apixaban, take it as soon as you remember "
                                "on the same day.\nNever take two doses at once."}]

    result, writes = margaret.say("What if I missed it?")

    assert writes == []
    assert result["response"] == (
        "Your letter says: If you miss a dose of apixaban, take it as soon as you remember on the same day."
    )
    assert result["source"]["page"] == 2


def test_replies_are_tidy(margaret):
    for message in ("No, not yet", "Yes", "Should I take two?"):
        reply = margaret.say(message)[0]["response"]
        assert not reply.startswith(("—", "-"))
        assert "screen" not in reply.lower() and "you're right" not in reply.lower()
