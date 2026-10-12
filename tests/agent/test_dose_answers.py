"""Saving a dose only when it is clear which medicine and that the full dose was taken; undo."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agent import service
from app.agent.dose_answers import parse_dose_answer
from app.agent.session import clear_session

with patch("boto3.resource"):
    from app.database import recovery_state


AFTER_BREAKFAST = "Take the morning dose after breakfast."
QUESTION = ("Now that you've had breakfast, it's time for your paracetamol, 2 tablets, and your blood thinner, "
            "1 tablet. Have you taken them?")


def _meds():
    return [
        *[{"occurrence_id": f"para#2026-10-23#{n}", "medication_id": "para", "name": "Paracetamol",
           "dose": "2 tablets", "instructions": AFTER_BREAKFAST, "time_of_day_label": s,
           "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "midday"), (3, "evening"), (4, "bedtime")]],
        *[{"occurrence_id": f"apix#2026-10-23#{n}", "medication_id": "apix", "name": "Apixaban",
           "dose": "1 tablet", "instructions": AFTER_BREAKFAST, "time_of_day_label": s,
           "occurrence_number": n, "status": "pending"}
          for n, s in [(1, "morning"), (2, "evening")]],
    ]


@pytest.fixture
def margaret(monkeypatch):
    run = SimpleNamespace(meds=_meds(), calls=[])

    async def call_tool(name, arguments):
        run.calls.append((name, arguments))
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": []}
        elif name == "get_medications":
            data = {"date": "2026-10-23", "medications": [dict(m) for m in run.meds]}
        elif name == "get_recovery_plan":
            data = {"patient_id": "demo_patient_001"}
        elif name in ("report_medication_taken", "undo_report"):
            for m in run.meds:
                if m["occurrence_id"] == arguments["occurrence_id"]:
                    m["status"] = "completed" if name == "report_medication_taken" else "pending"
            data = {"occurrence_id": arguments["occurrence_id"]}
        else:
            raise AssertionError(name)
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def no_model(**kwargs):
        raise AssertionError("the model should not be needed")

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", no_model)
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T08:40:00+01:00")

    def say(message, session="dose", fresh=False):
        if fresh:
            clear_session(session)
        result = asyncio.run(service.chat(message, session, first_name="Margaret"))
        writes = [(name, args["occurrence_id"]) for name, args in run.calls
                  if name in ("report_medication_taken", "undo_report")]
        run.calls.clear()
        return result, writes

    def asked(session="dose"):
        result, _ = say("I ate pizza for breakfast", session=session, fresh=True)
        assert result["response"].endswith("Have you taken them?")

    def done_count():
        return sum(1 for m in run.meds if m["status"] == "completed")

    run.say, run.asked, run.done_count = say, asked, done_count
    return run


def test_one_tablet_saves_nothing_and_asks_which(margaret):
    margaret.asked()

    result, writes = margaret.say("I have taken one tablet")

    assert writes == []
    assert result["response"] == "Which one did you take: your paracetamol or your blood thinner?"


def test_then_the_blood_thinner_saves_only_the_blood_thinner(margaret):
    margaret.asked()
    margaret.say("I have taken one tablet")

    result, writes = margaret.say("the blood thinner")

    assert writes == [("report_medication_taken", "apix#2026-10-23#1")]
    assert result["response"] == (
        "Thank you, Margaret. I've marked your blood thinner, 1 tablet, as taken. "
        "Your paracetamol is still in today's plan."
    )


def test_then_paracetamol_one_tablet_saves_nothing_and_quotes_the_letter_dose(margaret):
    margaret.asked()
    margaret.say("I have taken one tablet")
    margaret.say("the blood thinner")

    result, writes = margaret.say("paracetamol, one tablet")

    assert writes == []
    assert result["response"] == (
        "Your letter says 2 tablets of paracetamol, so I haven't marked it as done yet. "
        "Let me know when you've taken your full dose. If you're unsure, please ask your pharmacist."
    )
    assert "take another" not in result["response"].lower() and "take one more" not in result["response"].lower()


def test_one_tablet_then_paracetamol_does_not_save_it(margaret):
    margaret.asked()
    margaret.say("I have taken one tablet")

    result, writes = margaret.say("the paracetamol")

    assert writes == []
    assert result["response"].startswith("Your letter says 2 tablets of paracetamol")


@pytest.mark.parametrize("answer", ["yes, both", "Yes", "Yes I have", "I've taken them", "both"])
def test_a_plain_yes_saves_both(margaret, answer):
    margaret.asked()

    result, writes = margaret.say(answer)

    assert writes == [("report_medication_taken", "para#2026-10-23#1"), ("report_medication_taken", "apix#2026-10-23#1")]
    assert result["response"] == (
        "Thank you, Margaret. I've marked your paracetamol, 2 tablets, and your blood thinner, 1 tablet, as taken. "
        "Next is your paracetamol, at midday."
    )


def test_paracetamol_but_not_the_blood_thinner_saves_only_paracetamol(margaret):
    margaret.asked()

    result, writes = margaret.say("I took the paracetamol but not the blood thinner")

    assert writes == [("report_medication_taken", "para#2026-10-23#1")]
    assert result["response"] == (
        "Thank you, Margaret. I've marked your paracetamol, 2 tablets, as taken. "
        "Your blood thinner is still in today's plan."
    )


@pytest.mark.parametrize("answer", ["just one", "only one of them", "one of them"])
def test_partial_answers_without_a_name_ask_which(margaret, answer):
    margaret.asked()

    result, writes = margaret.say(answer)

    assert writes == []
    assert result["response"].startswith("Which one did you take")


def test_a_correction_right_after_a_save_undoes_only_that_item(margaret):
    margaret.asked()
    margaret.say("yes, both")
    assert margaret.done_count() == 2

    result, writes = margaret.say("no, I didn't take the blood thinner")

    assert writes == [("undo_report", "apix#2026-10-23#1")]
    assert result["response"] == "Sorry about that. I've changed it back. Your blood thinner is still in today's plan."
    assert margaret.done_count() == 1
    assert result["tool_trace"][-1] == {"tool": "undo_report", "arguments": {"occurrence_id": "apix#2026-10-23#1"}, "ok": True}


def test_thats_wrong_with_two_saved_asks_which_then_undoes_it(margaret):
    margaret.asked()
    margaret.say("yes, both")

    first, writes = margaret.say("that's wrong")
    assert writes == []
    assert first["response"] == "Which one should I change back: your paracetamol or your blood thinner?"

    second, writes = margaret.say("the paracetamol")
    assert writes == [("undo_report", "para#2026-10-23#1")]
    assert second["response"] == "Sorry about that. I've changed it back. Your paracetamol is still in today's plan."


def test_a_plain_no_after_a_save_never_undoes(margaret, monkeypatch):
    margaret.asked()
    margaret.say("yes, both")

    # A bare "no" is not a correction; the model may answer it, but nothing is undone.
    reply = {"role": "assistant", "content": [{"text": "Okay."}]}
    monkeypatch.setattr(service.bedrock, "converse", lambda **kw: {"output": {"message": reply}, "stopReason": "end_turn"})
    monkeypatch.setattr(service, "build_bedrock_tool_config", lambda: asyncio.sleep(0, {"tools": []}))
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")

    _, writes = margaret.say("No")

    assert writes == []
    assert margaret.done_count() == 2


def test_a_direct_short_report_saves_nothing(margaret):
    result, writes = margaret.say("I've taken one paracetamol tablet", fresh=True)

    assert writes == []
    assert result["response"].startswith("Your letter says 2 tablets of paracetamol")


# ---------- The parser on its own ----------

P = {"occurrence_id": "p", "medication_id": "para", "name": "Paracetamol", "dose": "2 tablets"}
A = {"occurrence_id": "a", "medication_id": "apix", "name": "Apixaban", "dose": "1 tablet"}


@pytest.mark.parametrize("message,kind,take", [
    ("yes", "all", ["Paracetamol", "Apixaban"]),
    ("two paracetamol and one blood thinner", "some", ["Paracetamol", "Apixaban"]),
    ("just the apixaban", "some", ["Apixaban"]),
    ("I haven't taken them", "none", []),
    ("not the paracetamol", "none", []),
])
def test_parser(message, kind, take):
    from app.agent.safety import is_negative_report

    answer = parse_dose_answer(message, [P, A], negative=is_negative_report(message))

    assert answer.kind == kind
    assert [d["name"] for d in answer.take] == take


# ---------- Storage: undo keeps history, and a dose can be saved again ----------

def test_undo_keeps_history_and_the_dose_can_be_saved_again(monkeypatch):
    events = []
    state = {"discharge_date": "2026-10-16", "medications": [
        {"id": "apix", "name": "Apixaban", "dose": "1 tablet", "time_of_day": ["morning", "evening"], "times_per_day": 2},
    ]}

    def append_event(patient_id, event_type, details, idempotency_key):
        duplicate = any(e["idempotency_key"] == idempotency_key for e in events)
        if not duplicate:
            events.append({"event_type": event_type, "details": details, "idempotency_key": idempotency_key})
        return {"created": not duplicate, "duplicate": duplicate}

    monkeypatch.setattr(recovery_state, "get_recovery_state", lambda patient_id: state)
    monkeypatch.setattr(recovery_state, "get_events", lambda patient_id: list(events))
    monkeypatch.setattr(recovery_state, "append_event", append_event)

    occurrence = "apix#2026-10-23#1"
    status = lambda: next(m for m in recovery_state.get_medications("p", "2026-10-23")
                          if m["occurrence_id"] == occurrence)["status"]

    recovery_state.mark_medication_taken("p", occurrence, "2026-10-23")
    assert status() == "completed"

    assert recovery_state.undo_completion("p", occurrence, "2026-10-23")["undone"] is True
    assert status() == "pending"
    assert [e["event_type"] for e in events] == ["medication_taken", "medication_undone"]

    # Undoing again changes nothing.
    assert recovery_state.undo_completion("p", occurrence, "2026-10-23")["undone"] is False

    # Taken later after all: a new round is saved, not refused as a duplicate.
    again = recovery_state.mark_medication_taken("p", occurrence, "2026-10-23")
    assert again["already_completed"] is False
    assert status() == "completed"
    assert len(events) == 3 and events[-1]["idempotency_key"].endswith("#r1")
