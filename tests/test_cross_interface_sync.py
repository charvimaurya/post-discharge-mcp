"""Alexa/web -> real agent/MCP auth/tools -> real readers/writer -> isolated tables.

The identity is synthetic Margaret, but every table operation is in memory.
These are not live DynamoDB or Alexa NLU tests. Unexpected AWS calls are forbidden.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

from botocore.client import BaseClient
from botocore.exceptions import ClientError
import pytest
from starlette.testclient import TestClient

from app import turn, web_bridge
from app.agent import service
from app.agent.session import clear_session
from app.database import event_history, recovery_state
from app.mcp import server
from app.mcp.tools import actions, recovery, week
from tests.bridge_client import BridgeClient
from tests.test_alexa import _envelope, _intent, SKILL

PATIENT = "demo_patient_001"
DAY = "2026-10-23"
WALK = f"walk#{DAY}#1"


@pytest.fixture
def sync(monkeypatch, mcp_hop):
    state = {"patient_id": PATIENT, "first_name": "Margaret", "timezone": "Europe/London",
             "discharge_date": "2026-10-16", "medications": [], "tasks": [
        {"id": "walk", "description": "Walking: a short walk", "times_per_day": 2,
         "clock_times": ["07:30", "15:00"]},
        {"id": "dressing", "description": "Change dressing", "times_per_day": 1},
    ]}
    saved_state = deepcopy(state)
    # A first page unrelated to today's completion. Real reads must paginate.
    events = {"old": {"patient_id": PATIENT, "timestamp": "old", "event_type": "task_completed",
                      "idempotency_key": "old", "details": {"date": "2026-10-01",
                      "occurrence_id": "walk#2026-10-01#1", "completed_at": "2026-10-01T08:00:00+01:00"}}}
    run = SimpleNamespace(events=events, state=state, fail_writes=False, queries=[], reads=[], tools=[])

    class StateTable:
        def get_item(self, *, Key, ConsistentRead=False):
            assert Key == {"patient_id": PATIENT}
            run.reads.append(ConsistentRead)
            assert ConsistentRead, "A current-state read must not be eventually consistent"
            return {"Item": deepcopy(state)}

    class EventTable:
        def query(self, *, KeyConditionExpression, ConsistentRead=False, ExclusiveStartKey=None):
            assert KeyConditionExpression.get_expression()["values"][1] == PATIENT
            assert ConsistentRead, "Simulate a stale replica unless a strong read is requested"
            run.queries.append(ExclusiveStartKey)
            rows = list(events.values())
            start = 0 if ExclusiveStartKey is None else next(
                i + 1 for i, row in enumerate(rows) if row["timestamp"] == ExclusiveStartKey["timestamp"])
            page = deepcopy(rows[start:start + 1])
            result = {"Items": page}
            if start + 1 < len(rows):
                result["LastEvaluatedKey"] = {"patient_id": PATIENT, "timestamp": page[-1]["timestamp"]}
            return result

        def put_item(self, *, Item, ConditionExpression, ExpressionAttributeNames):
            assert Item["patient_id"] == PATIENT
            assert ConditionExpression and ExpressionAttributeNames
            if run.fail_writes:
                raise ClientError({"Error": {"Code": "AccessDeniedException"}}, "PutItem")
            if Item["timestamp"] in events:
                raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
            events[Item["timestamp"]] = deepcopy(Item)
            return {}

    def forbid_aws(*args, **kwargs):
        raise AssertionError("No real AWS call is permitted in this isolated test")
    monkeypatch.setattr(BaseClient, "_make_api_call", forbid_aws)
    monkeypatch.setattr(recovery_state, "table", StateTable())
    monkeypatch.setattr(event_history, "event_table", EventTable())
    for module in (recovery, actions, week):
        for name in dir(module):
            if name.endswith("_for_context") and hasattr(server, name):
                monkeypatch.setattr(server, name, getattr(module, name))
    async def call(name, arguments):
        run.tools.append((name, arguments))
        return await mcp_hop(name, arguments)
    monkeypatch.setattr(service, "call_mcp_tool", call)
    monkeypatch.setattr(web_bridge, "call_mcp_tool", call)
    monkeypatch.setattr(service.bedrock, "converse", forbid_aws)
    # Ancillary greeting/chat metadata is unrelated to completion; never touch real storage.
    monkeypatch.setattr(turn, "record_chat_activity", lambda *args: None)
    monkeypatch.setattr(turn, "add_scheduled_checkin", lambda *args: None)
    monkeypatch.setenv("DEMO_FIXED_NOW", DAY + "T08:00:00+01:00")
    monkeypatch.setenv("DEMO_IDLE_RESET_HOURS", "0")
    monkeypatch.setenv("ALEXA_SKILL_ID", SKILL)
    monkeypatch.setenv("ALEXA_VERIFY_SIGNATURE", "false")
    monkeypatch.setenv("ALEXA_VERIFY_TIMESTAMP", "false")
    monkeypatch.setenv("ALEXA_FEED_ENABLED", "false")
    clear_session("sync-web")
    clear_session("amzn1.echo-api.session.s-1")
    run.client = BridgeClient(web_bridge.app)
    def alexa(intent, **slots):
        response = run.client.post("/alexa", content=json.dumps(_envelope(_intent(intent, **slots))))
        assert response.status_code == 200
        return response.json()["response"]["outputSpeech"]["text"]
    run.alexa = alexa
    yield run
    assert state == saved_state, "Completion must never overwrite the base plan"


def chart(client):
    response = client.get("/week-summary")
    assert response.status_code == 200, response.text
    return response.json()["week"]["activity"][-1]["completed_tasks"]


def test_alexa_web_and_chart_share_persisted_events_across_reload_and_retry(sync):
    run = sync
    assert chart(run.client) == 0
    speech = run.alexa("CameBackFromIntent", query="my walk")
    assert "couldn't" not in speech.lower(), speech
    today = run.client.get("/today")
    assert today.status_code == 200
    first, second, dressing = today.json()["tasks"]
    assert first["occurrence_id"] == WALK and first["status"] == "completed"
    assert first["completed_at"] and second["status"] == dressing["status"] == "pending"
    event = next(row for row in run.events.values() if row["details"].get("occurrence_id") == WALK)
    assert event["event_type"] == "task_completed" and event["recorded_at"]
    assert event["details"]["completed_at"]
    assert chart(run.client) == 1
    assert any(key is not None for key in run.queries), "Completion was on a later history page"

    response = run.client.post("/tasks/complete", json={"occurrence_id": f"dressing#{DAY}#1"})
    assert response.status_code == 200, response.text
    assert any(step["tool"] == "report_task_completed" and step["ok"] for step in response.json()["tool_trace"])
    assert chart(run.client) == 2
    # Alexa's next turn must load the new state, not write the same task again.
    before = deepcopy(run.events)
    speech = run.alexa("CompletedIntent", query="my dressing")
    assert "already recorded" in speech.lower(), speech
    assert run.events == before
    # A fresh HTTP client represents browser reload; nothing comes from a component snapshot.
    reloaded = BridgeClient(web_bridge.app).get("/today").json()
    assert sum(task["status"] == "completed" for task in reloaded["tasks"]) == 2
    run.alexa("CameBackFromIntent", query="my walk")
    assert run.events == before and chart(run.client) == 2


@pytest.mark.parametrize("patient", ["another_patient", PATIENT])
def test_caller_patient_ids_are_rejected_before_any_write(sync, patient):
    before = deepcopy(sync.events)
    assert sync.client.post("/chat", json={"message": "I completed my walk", "patient_id": patient}).status_code == 400
    assert sync.client.get(f"/today?patient_id={patient}").status_code == 400
    assert sync.client.get(f"/week-summary?patient_id={patient}").status_code == 400
    assert sync.client.post("/tasks/complete", json={"occurrence_id": WALK, "patient_id": patient}).status_code == 400
    assert sync.events == before and sync.tools == []


@pytest.mark.parametrize("interface", ["alexa", "web", "button"])
def test_failed_writes_never_confirm_or_change_progress(sync, interface):
    before = deepcopy(sync.events)
    sync.fail_writes = True
    if interface == "alexa":
        text = sync.alexa("CameBackFromIntent", query="my walk")
    elif interface == "button":
        response = sync.client.post("/tasks/complete", json={"occurrence_id": WALK})
        assert response.status_code == 502
        assert sync.events == before and chart(sync.client) == 0
        return
    else:
        response = sync.client.post("/chat", json={"message": "I completed my walk", "session_id": "sync-web"})
        assert response.status_code == 200
        text = response.json()["response"]
    assert "couldn't record" in text.lower(), text
    assert sync.events == before and chart(sync.client) == 0
    assert all(task["status"] == "pending" for task in sync.client.get("/today").json()["tasks"])


@pytest.mark.parametrize("occurrence", [f"unknown#{DAY}#1", "walk#2026-10-22#1", f"walk#{DAY}#99"])
def test_forged_or_wrong_day_occurrences_do_not_persist(sync, occurrence):
    before = deepcopy(sync.events)
    response = sync.client.post("/tasks/complete", json={"occurrence_id": occurrence})
    assert response.status_code == 502
    assert sync.events == before and chart(sync.client) == 0


def test_task_button_preserves_the_exact_selected_occurrence_and_is_idempotent(sync):
    occurrence = f"walk#{DAY}#2"
    for _ in range(2):
        response = sync.client.post("/tasks/complete", json={"occurrence_id": occurrence})
        assert response.status_code == 200, response.text
    first, second, _ = sync.client.get("/today").json()["tasks"]
    assert first["status"] == "pending" and second["status"] == "completed"
    assert chart(sync.client) == 1


def test_task_button_requires_bridge_authentication_before_any_tool_call(sync):
    before = deepcopy(sync.events)
    assert TestClient(web_bridge.app).post('/tasks/complete', json={"occurrence_id": WALK}).status_code == 401
    assert sync.events == before and sync.tools == []
