"""'How is my week?': her saved days since leaving hospital, given to the model as facts."""

import asyncio

import pytest

from app.agent import service


@pytest.mark.parametrize("message", [
    "how is your week", "How's my week going?", "How has my week been?",
    "how have I been doing this week", "How am I doing so far?",
])
def test_week_questions_are_recognised(message):
    assert service.asks_about_week(message)


@pytest.mark.parametrize("message", ["what's next", "how long do I take it for", "I've done my walk"])
def test_other_messages_are_not_week_questions(message):
    assert not service.asks_about_week(message)


def _dose(day, due, at):
    return {"name": "Paracetamol", "status": "taken" if at else "pending",
            "due_at": f"{day}T{due}:00+01:00", "recorded_at": f"{day}T{at}:00+01:00" if at else None}


def _task(name, done):
    return {"name": name, "status": "completed" if done else "pending"}


def _days(records):
    async def call_tool(name, arguments):
        if name == "get_recovery_plan":
            return {"ok": True, "data": {"discharge_date": "2026-10-20"}}
        assert name == "get_recovery_day_details"
        day = arguments["date"]
        return {"ok": True, "data": records.get(day, {"medications": [], "tasks": []})}
    return call_tool


def test_week_facts_from_a_tuesday_discharge(monkeypatch):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T09:00:00+01:00")
    records = {
        "2026-10-21": {"medications": [_dose("2026-10-21", "08:00", "08:10"), _dose("2026-10-21", "18:00", "18:10")],
                       "tasks": [_task("Walking", True), _task("Knee exercises", True)]},
        "2026-10-22": {"medications": [_dose("2026-10-22", "08:00", "10:30"), _dose("2026-10-22", "18:00", "18:05")],
                       "tasks": [_task("Walking", True), _task("Knee exercises", False)]},
        "2026-10-23": {"medications": [_dose("2026-10-23", "08:00", "08:05"), _dose("2026-10-23", "18:00", None)],
                       "tasks": [_task("Walking", False)]},
    }
    monkeypatch.setattr(service, "call_mcp_tool", _days(records))
    monkeypatch.setattr(service, "get_structured_tool_result", lambda raw: raw)
    trace = []

    facts = asyncio.run(service._preload_week(trace, "Europe/London"))

    assert "She left hospital on Tuesday 20 October 2026" in facts
    assert "she has been home 3 days" in facts
    assert "Her recovery at home started on Wednesday 21 October 2026" in facts
    # Only the days since discharge, not the whole seven-day window.
    assert "Monday 19 October" not in facts and "Tuesday 20 October 2026:" not in facts
    assert ("- Wednesday 21 October 2026: medicine doses recorded taken 2 of 2; all of them on time; "
            "recovery tasks done 2 of 2; everything done.") in facts
    assert ("- Thursday 22 October 2026: medicine doses recorded taken 2 of 2; 1 of 2 on time; "
            "recovery tasks done 1 of 2.") in facts
    assert ("- Friday 23 October 2026 (today, so far): medicine doses recorded taken 1 of 2; all of them on time; "
            "recovery tasks done 0 of 1; still to do today: Paracetamol, Walking.") in facts
    assert [t["tool"] for t in trace] == ["get_recovery_plan"] + ["get_recovery_day_details"] * 3
    assert all(t["ok"] for t in trace)


def test_no_week_facts_when_the_plan_cannot_be_read(monkeypatch):
    async def broken(name, arguments):
        raise RuntimeError("offline")

    monkeypatch.setattr(service, "call_mcp_tool", broken)
    trace = []

    assert asyncio.run(service._preload_week(trace, "Europe/London")) is None
    assert trace == [{"tool": "get_recovery_plan", "arguments": {}, "ok": False}]


def test_a_day_with_nothing_saved_says_so():
    from datetime import date
    assert service._day_line(date(2026, 10, 21), {"medications": [], "tasks": []}, False) == (
        "- Wednesday 21 October 2026: nothing recorded.")
