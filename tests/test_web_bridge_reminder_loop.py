"""The web bridge's local reminder loop, with the reminder handler replaced by a fake."""

import threading
import time

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import web_bridge


DEMO_NOW = "2026-10-23T07:00:00+01:00"


@pytest.fixture
def fake_handler(monkeypatch):
    """Record each handler call; optionally fail on chosen calls."""

    record = {"events": [], "fail_on": set(), "called": threading.Event()}

    def handler(event, context):
        record["events"].append(event)
        record["called"].set()

        if len(record["events"]) in record["fail_on"]:
            raise ConnectionError("DynamoDB unreachable")

        return {"created": False, "reason": "nothing_due"}

    monkeypatch.setattr(web_bridge, "reminder_handler", handler)
    monkeypatch.setenv("REMINDER_LOOP_SECONDS", "0.01")
    monkeypatch.delenv("LOCAL_REMINDER_LOOP", raising=False)
    monkeypatch.delenv("DEMO_FIXED_NOW", raising=False)

    return record


def _wait_for(condition, timeout=2.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)

    return False


def test_loop_passes_demo_now_when_the_clock_is_pinned(fake_handler, monkeypatch):
    monkeypatch.setenv("LOCAL_REMINDER_LOOP", "1")
    monkeypatch.setenv("DEMO_FIXED_NOW", DEMO_NOW)

    with TestClient(web_bridge.app):
        assert fake_handler["called"].wait(2.0)

    assert fake_handler["events"][0] == {"demo_now": DEMO_NOW}


def test_loop_passes_an_empty_event_without_a_demo_clock(fake_handler, monkeypatch):
    monkeypatch.setenv("LOCAL_REMINDER_LOOP", "1")
    monkeypatch.setenv("CLOCK_MODE", "real")

    with TestClient(web_bridge.app):
        assert fake_handler["called"].wait(2.0)

    assert fake_handler["events"][0] == {}


def test_loop_does_nothing_unless_enabled(fake_handler):
    with TestClient(web_bridge.app) as client:
        time.sleep(0.1)

        assert client.app.state.reminder_task is None

    assert fake_handler["events"] == []


def test_handler_error_does_not_stop_the_loop(fake_handler, monkeypatch):
    monkeypatch.setenv("LOCAL_REMINDER_LOOP", "1")
    fake_handler["fail_on"] = {1}

    with TestClient(web_bridge.app):
        assert _wait_for(lambda: len(fake_handler["events"]) >= 3)


def test_loop_stops_when_the_bridge_shuts_down(fake_handler, monkeypatch):
    monkeypatch.setenv("LOCAL_REMINDER_LOOP", "1")

    with TestClient(web_bridge.app) as client:
        assert fake_handler["called"].wait(2.0)
        task = client.app.state.reminder_task

    assert task.cancelled() or task.done()
    calls_after_shutdown = len(fake_handler["events"])
    time.sleep(0.1)
    assert len(fake_handler["events"]) == calls_after_shutdown


@pytest.mark.parametrize(
    ("result", "outcome"),
    [
        ({"created": True, "pending_checkin": {}}, "created"),
        ({"created": False, "reason": "already_reminded"}, "already_reminded"),
        ({"created": False, "reason": "nothing_due"}, "nothing_due"),
    ],
)
def test_run_once_reports_the_handler_outcome(monkeypatch, result, outcome):
    monkeypatch.setattr(web_bridge, "reminder_handler", lambda event, context: result)

    assert web_bridge.run_reminder_once() == outcome


def test_run_once_reports_an_error_instead_of_raising(monkeypatch):
    def broken(event, context):
        raise RuntimeError("boom")

    monkeypatch.setattr(web_bridge, "reminder_handler", broken)

    assert web_bridge.run_reminder_once() == "error"


def test_bad_interval_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("REMINDER_LOOP_SECONDS", "soon")

    assert web_bridge._reminder_loop_seconds() == web_bridge.REMINDER_LOOP_DEFAULT_SECONDS
