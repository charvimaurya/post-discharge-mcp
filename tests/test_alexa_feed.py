"""The Alexa feed for /demo: off by default, memory only (last 20), never logged, cleared by reset."""

import pytest
from starlette.testclient import TestClient

from app import demo_reset, web_bridge
from app.alexa import feed, handlers
from tests.test_alexa import _intent, alexa  # noqa: F401 (the fixture)

KEY = "test-bridge-key"


@pytest.fixture(autouse=True)
def fresh_feed(monkeypatch):
    monkeypatch.setenv("BRIDGE_KEY", KEY)
    monkeypatch.setattr(feed, "_turns", type(feed._turns)(maxlen=feed.MAX_TURNS))
    monkeypatch.setattr(feed, "_last_id", 0)


def get(query="", key=KEY):
    headers = {"X-AfterWard-Key": key} if key is not None else {}
    return TestClient(web_bridge.app).get(f"/conversation{query}", headers=headers)


def test_off_by_default_records_nothing_and_the_route_says_off(monkeypatch, alexa):
    monkeypatch.delenv("ALEXA_FEED_ENABLED", raising=False)
    alexa.send(_intent("BackFromIntent", query="my walk"))

    assert feed.since(0) == {"turns": [], "latest": 0}
    assert get("?after=0").status_code == 404


def test_an_alexa_turn_is_in_the_feed_and_never_in_the_logs(monkeypatch, alexa, capsys):
    monkeypatch.setenv("ALEXA_FEED_ENABLED", "true")
    alexa.send(_intent("UnwellMyIntent", query="calf is swollen"))

    # A page that just opened gets only the latest id; a page that has seen id 0 gets the turn.
    assert get().json() == {"turns": [], "latest": 1}
    assert get("?after=0").json() == {"turns": [
        {"id": 1, "said": "my calf is swollen", "reply": "Reply to: my calf is swollen",
         "source": None, "tool_trace": [], "help": None, "crisis": False, "kind": "turn"}], "latest": 1}
    assert get("?after=1").json() == {"turns": [], "latest": 1}
    assert "calf" not in capsys.readouterr().out


def test_the_feed_keeps_what_the_screen_shows_beside_a_web_reply(monkeypatch, alexa, capsys):
    monkeypatch.setenv("ALEXA_FEED_ENABLED", "true")
    source = {"page": 2, "section": "Warning signs", "text": "Call the ward if you have: Pain in your calf."}
    help_card = {"actions": [{"urgency": "contact_care_team", "action": "Call the ward"}]}
    trace = [{"tool": "get_recovery_plan", "arguments": {}, "ok": True}]

    async def symptom_turn(message, session_id):
        return {"response": "I'm sorry to hear that.", "tool_trace": trace, "source": source,
                "help": help_card, "crisis": False}

    monkeypatch.setattr(handlers, "run_turn", symptom_turn)
    alexa.send(_intent("UnwellMyIntent", query="calf is swollen"))

    (turn,) = feed.since(0)["turns"]
    assert turn["source"] == source and turn["help"] == help_card and turn["tool_trace"] == trace
    assert turn["crisis"] is False
    assert "calf" not in capsys.readouterr().out


def test_the_route_needs_the_bridge_key(monkeypatch):
    monkeypatch.setenv("ALEXA_FEED_ENABLED", "true")

    assert get("?after=0", key=None).status_code == 401
    assert get("?after=0", key="wrong").status_code == 401


def test_only_the_last_20_turns_are_kept(monkeypatch):
    monkeypatch.setenv("ALEXA_FEED_ENABLED", "true")
    for n in range(25):
        feed.record(f"said {n}", f"reply {n}")

    turns = feed.since(0)["turns"]
    assert len(turns) == 20 and turns[0]["id"] == 6 and feed.since(0)["latest"] == 25


def test_the_demo_reset_clears_the_feed_and_ids_keep_counting(monkeypatch):
    monkeypatch.setenv("ALEXA_FEED_ENABLED", "true")
    feed.record("I'm back from my walk", "Well done.")

    class Table:
        def batch_writer(self): return self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def query(self, **kwargs): return {"Items": []}

    monkeypatch.setattr(demo_reset, "get_recovery_state", lambda patient_id: {"tasks": [], "medications": []})
    monkeypatch.setattr(demo_reset, "save_recovery_state", lambda state: None)
    monkeypatch.setattr(demo_reset, "event_table", Table())
    demo_reset.reset_demo_patient()

    assert feed.since(0) == {"turns": [], "latest": 1}
    feed.record("what's next", "Your paracetamol.")
    assert [t["id"] for t in feed.since(1)["turns"]] == [2]


def test_opening_the_skill_is_a_launch_turn_in_the_feed(monkeypatch, alexa):
    monkeypatch.setenv("ALEXA_FEED_ENABLED", "true")
    alexa.send({"type": "LaunchRequest"})
    alexa.state["pending_checkin"] = {"text": "Good morning, Margaret. It's time for your morning walk."}
    alexa.send({"type": "LaunchRequest"})

    turns = feed.since(0)["turns"]
    assert [t["kind"] for t in turns] == ["launch", "launch"]
    assert turns[0]["reply"] == "Hello, Margaret. Reply to: What is next?"
    assert turns[1]["reply"] == "Good morning, Margaret. It's time for your morning walk."
