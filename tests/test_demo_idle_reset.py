"""The demo starts fresh after a long idle gap, and never shows a reminder for something done."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from tests.bridge_client import BridgeClient

from app import demo_reset, web_bridge


NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
WALK_ID = "walk#2026-10-23#1"


@pytest.fixture
def record(monkeypatch):
    """Her record in memory; resets are counted, not run."""

    run = SimpleNamespace(state={"patient_id": "demo_patient_001"}, resets=0)

    def fake_reset():
        run.resets += 1

    monkeypatch.setenv("DEMO_IDLE_RESET_HOURS", "2")
    monkeypatch.setattr(demo_reset, "get_recovery_state", lambda patient_id: run.state)
    monkeypatch.setattr(demo_reset, "reset_demo_patient", fake_reset)
    return run


def test_resets_after_two_idle_hours(record):
    record.state["last_chat_at"] = (NOW - timedelta(hours=3)).isoformat()

    assert demo_reset.reset_if_idle(NOW) is True
    assert record.resets == 1


def test_a_recent_chat_keeps_the_day(record):
    record.state["last_chat_at"] = (NOW - timedelta(minutes=30)).isoformat()

    assert demo_reset.reset_if_idle(NOW) is False
    assert record.resets == 0


def test_a_recent_reset_counts_as_activity(record):
    # Reset removes last_chat_at, so its own time stops the next visit resetting again.
    record.state["demo_reset_at"] = (NOW - timedelta(minutes=5)).isoformat()

    assert demo_reset.reset_if_idle(NOW) is False


def test_a_record_with_no_times_counts_as_idle(record):
    assert demo_reset.reset_if_idle(NOW) is True


@pytest.mark.parametrize("hours", ["0", "-1"])
def test_zero_turns_it_off(record, monkeypatch, hours):
    monkeypatch.setenv("DEMO_IDLE_RESET_HOURS", hours)

    assert demo_reset.reset_if_idle(NOW) is False


def test_never_in_production(record, monkeypatch):
    monkeypatch.setenv("CLOCK_MODE", "production")

    assert demo_reset.reset_if_idle(NOW) is False


def test_no_plan_means_nothing_to_reset(record):
    record.state = None

    assert demo_reset.reset_if_idle(NOW) is False


@pytest.mark.parametrize("setting", [None, "soon"])
def test_missing_or_invalid_setting_keeps_progress(monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv("DEMO_IDLE_RESET_HOURS", raising=False)
    else:
        monkeypatch.setenv("DEMO_IDLE_RESET_HOURS", setting)

    assert demo_reset.idle_reset_hours() == 0


# ---------- /today ----------

@pytest.fixture
def today(monkeypatch):
    run = SimpleNamespace(cleared=[], walk_status="completed", state={
        "first_name": "Margaret",
        "pending_checkin": {"occurrence_id": WALK_ID, "text": "You have about thirty minutes until your walk."},
    })

    async def call_tool(name, arguments):
        if name == "get_today_tasks":
            data = {"date": "2026-10-23", "tasks": [
                {"occurrence_id": WALK_ID, "clock_time": "07:30", "status": run.walk_status}]}
        else:
            data = {"date": "2026-10-23", "medications": []}
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    monkeypatch.setattr(web_bridge, "call_mcp_tool", call_tool)
    monkeypatch.setattr(web_bridge, "get_recovery_state", lambda patient_id: run.state)
    monkeypatch.setattr(web_bridge, "clear_pending_checkin", lambda patient_id: run.cleared.append(patient_id))
    run.client = BridgeClient(web_bridge.app)
    return run


def test_reminder_for_a_done_walk_is_hidden_and_cleared(today):
    body = today.client.get("/today").json()

    assert body["pending_checkin"] is None
    assert today.cleared == ["demo_patient_001"]


def test_reminder_for_a_pending_walk_is_shown(today):
    today.walk_status = "pending"

    body = today.client.get("/today").json()

    assert body["pending_checkin"]["occurrence_id"] == WALK_ID
    assert today.cleared == []


def test_today_runs_the_idle_check_first(today, monkeypatch):
    calls = []
    monkeypatch.setattr(web_bridge, "reset_if_idle", lambda: calls.append("checked") or True)

    assert today.client.get("/today").status_code == 200
    assert calls == ["checked"]


def test_a_failed_idle_check_does_not_break_today(today, monkeypatch):
    def broken():
        raise RuntimeError("DynamoDB unavailable")

    monkeypatch.setattr(web_bridge, "reset_if_idle", broken)

    assert today.client.get("/today").status_code == 200


def test_today_reports_when_the_demo_was_last_reset(today):
    # /demo clears its chat when this changes.
    today.state["demo_reset_at"] = "2026-10-17T15:00:00+00:00"

    assert today.client.get("/today").json()["demo_reset_at"] == "2026-10-17T15:00:00+00:00"
