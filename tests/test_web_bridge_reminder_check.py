"""POST /reminders/check on the web bridge, with the reminder handler replaced by a fake."""

import pytest
from starlette.testclient import TestClient

from app import web_bridge


DEMO_NOW = "2026-10-23T07:00:00+01:00"


@pytest.fixture
def check(monkeypatch):
    """Fake handler that records each event and returns a chosen result."""

    calls = []
    reply = {"result": {"created": False, "reason": "nothing_due"}}

    def handler(event, context):
        calls.append(event)
        return reply["result"]

    monkeypatch.setattr(web_bridge, "reminder_handler", handler)
    monkeypatch.setenv("DEMO_FIXED_NOW", DEMO_NOW)
    monkeypatch.delenv("LOCAL_REMINDER_LOOP", raising=False)

    def post(**kwargs):
        return TestClient(web_bridge.app).post("/reminders/check", **kwargs)

    return calls, reply, post


def test_created_reminder_is_returned(check):
    calls, reply, post = check
    pending = {"checkin_id": "2026-10-23#walk#1", "occurrence_id": "walk#1", "text": "Good morning, Margaret."}
    reply["result"] = {"created": True, "pending_checkin": pending}

    response = post()

    assert response.status_code == 200
    assert response.json() == {"created": True, "pending_checkin": pending}
    assert calls == [{"demo_now": DEMO_NOW}]


def test_nothing_due_is_returned(check):
    _, _, post = check

    response = post()

    assert response.status_code == 200
    assert response.json() == {"created": False, "reason": "nothing_due"}


def test_already_reminded_is_returned(check):
    _, reply, post = check
    reply["result"] = {"created": False, "reason": "already_reminded", "checkin_id": "k"}

    assert post().json()["reason"] == "already_reminded"


def test_real_clock_when_no_demo_clock(check, monkeypatch):
    calls, _, post = check
    monkeypatch.setenv("CLOCK_MODE", "real")

    post()

    assert calls == [{}]


def test_handler_error_returns_502(check, monkeypatch):
    _, _, post = check

    def broken(event, context):
        raise ConnectionError("DynamoDB unreachable")

    monkeypatch.setattr(web_bridge, "reminder_handler", broken)

    response = post()

    assert response.status_code == 502
    assert response.json() == {"error": web_bridge.REMINDER_CHECK_ERROR}


def test_caller_cannot_choose_patient_date_or_time(check):
    calls, _, post = check

    post(
        json={"patient_id": "someone_else", "demo_now": "2030-01-01T09:00:00+00:00", "date": "2030-01-01"},
        params={"patient_id": "someone_else", "demo_now": "x"},
    )

    # Only the server's own demo clock reaches the handler; no patient_id,
    # so the handler uses its fixed demo patient.
    assert calls == [{"demo_now": DEMO_NOW}]


def test_only_post_is_allowed(check):
    calls, _, _ = check

    assert TestClient(web_bridge.app).get("/reminders/check").status_code == 405
    assert calls == []
