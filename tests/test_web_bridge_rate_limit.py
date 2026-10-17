"""Demo chat limits: 30 messages per session and 100 per visitor IP in any hour."""

import pytest
from tests.bridge_client import BridgeClient as TestClient

from app import turn, web_bridge


@pytest.fixture
def counted(monkeypatch):
    """Fakes for everything a chat turn touches, counting each call."""

    seen = {"agent": 0, "activity": 0, "state": 0}
    now = [1000.0]

    async def fake_chat(message, session_id, **kwargs):
        seen["agent"] += 1
        return {"response": "Fine.", "tool_trace": [], "source": None, "completed": True}

    def fake_activity(patient_id, at):
        seen["activity"] += 1

    def fake_state(patient_id):
        seen["state"] += 1
        return {}

    # The chat turn itself runs in app.turn (shared with Alexa); the limit is checked in the bridge first.
    monkeypatch.setattr(turn, "chat", fake_chat)
    monkeypatch.setattr(turn, "record_chat_activity", fake_activity)
    monkeypatch.setattr(turn, "get_recovery_state", fake_state)
    monkeypatch.setattr(turn, "clear_pending_checkin", lambda patient_id: None)
    for limiter in (web_bridge.CHAT_SESSION_LIMIT, web_bridge.CHAT_IP_LIMIT):
        monkeypatch.setattr(limiter, "clock", lambda: now[0])
    seen["now"] = now
    return seen


def send(client, session_id, ip="203.0.113.7", headers=None):
    return client.post(
        "/chat",
        json={"message": "What's next?", "session_id": session_id},
        headers={"X-AfterWard-Client-IP": ip, **(headers or {})},
    )


def assert_limited(response):
    assert response.status_code == 200
    body = response.json()
    assert body["rate_limited"] is True
    assert body["response"] == "You've reached the demo limit for now. Please try again in a little while."
    assert body["tool_trace"] == []


def test_31st_message_in_an_hour_gets_the_demo_limit_and_calls_nothing(counted):
    client = TestClient(web_bridge.app)

    for _ in range(30):
        response = send(client, "demo-one")
        assert response.status_code == 200 and "rate_limited" not in response.json()

    assert_limited(send(client, "demo-one"))
    # Only the 30 allowed messages reached DynamoDB or the agent (and so any MCP tool).
    assert counted["agent"] == 30
    assert counted["activity"] == 30
    assert counted["state"] == 30


def test_another_session_keeps_its_own_allowance(counted):
    client = TestClient(web_bridge.app)
    for _ in range(30):
        send(client, "demo-one")

    assert "rate_limited" not in send(client, "demo-two").json()


def test_the_session_can_chat_again_after_the_hour(counted):
    client = TestClient(web_bridge.app)
    for _ in range(30):
        send(client, "demo-one")
    assert_limited(send(client, "demo-one"))

    counted["now"][0] += 3600

    assert "rate_limited" not in send(client, "demo-one").json()


def test_101st_message_from_one_ip_is_limited_across_sessions(counted):
    client = TestClient(web_bridge.app)

    for n in range(100):
        assert "rate_limited" not in send(client, f"demo-{n}").json()

    assert_limited(send(client, "demo-new"))
    assert counted["agent"] == 100


def test_x_forwarded_for_sent_straight_to_the_bridge_cannot_change_the_ip(counted):
    # The bridge only reads X-AfterWard-Client-IP (set by the web server), so a
    # visitor-supplied X-Forwarded-For with a new fake value each time changes nothing.
    client = TestClient(web_bridge.app)

    for n in range(100):
        send(client, f"demo-{n}", headers={"X-Forwarded-For": f"10.0.0.{n}"})

    assert_limited(send(client, "demo-new", headers={"X-Forwarded-For": "10.9.9.9"}))
