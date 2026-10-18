"""Local storage simulation, not evidence of live AWS or MCPJam repeatability."""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

from botocore.client import BaseClient
from botocore.exceptions import ClientError
import pytest

from app.auth.patient_scope import PatientContext
from app.database import event_history, recovery_state
from app.mcp.context import reset_current_patient_context, set_current_patient_context
from app.mcp.server import mcp


@pytest.fixture
def isolated_store(monkeypatch):
    """Exercise real tool/business/event code with no reachable AWS operations."""
    def forbid_aws(*args, **kwargs):
        pytest.fail("Isolated repeatability tests must never call AWS")

    monkeypatch.setattr(BaseClient, "_make_api_call", forbid_aws)
    monkeypatch.setenv("CLOCK_MODE", "demo")
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T08:00:00+01:00")
    patients = ("isolated_s4_a", "isolated_s4_b")
    plans = {
        patient: {
            "patient_id": patient,
            "timezone": "Europe/London",
            "tasks": [{"id": "walk", "description": "Synthetic walk", "times_per_day": 2}],
        }
        for patient in patients
    }
    events = {}

    def get_item(*, Key, ConsistentRead=False):
        assert ConsistentRead
        assert Key["patient_id"] in patients
        return {"Item": deepcopy(plans[Key["patient_id"]])}

    def query(*, KeyConditionExpression, ConsistentRead=False):
        assert ConsistentRead
        patient = KeyConditionExpression.get_expression()["values"][1]
        assert patient in patients
        return {"Items": deepcopy([row for (owner, _), row in events.items() if owner == patient])}

    def put_item(*, Item, ConditionExpression, ExpressionAttributeNames):
        assert Item["patient_id"] in patients
        assert ConditionExpression and ExpressionAttributeNames
        key = (Item["patient_id"], Item["timestamp"])
        if key in events:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        events[key] = deepcopy(Item)
        return {}

    monkeypatch.setattr(recovery_state, "table", SimpleNamespace(get_item=get_item))
    monkeypatch.setattr(event_history, "event_table", SimpleNamespace(query=query, put_item=put_item))
    return SimpleNamespace(patients=patients, plans=plans, original=deepcopy(plans), events=events)


def call(patient, name, arguments=None):
    async def run():
        context = set_current_patient_context(PatientContext("isolated_test", patient, "isolated_session"))
        try:
            result = await mcp.call_tool(name, arguments or {})
            assert not result.is_error
            payload = result.structured_content or json.loads(result.content[0].text)
            assert payload["ok"] is True
            return payload["data"]
        finally:
            reset_current_patient_context(context)
    return asyncio.run(run())


@pytest.mark.parametrize("patient_index", [0, 1])
def test_completion_persists_across_reads_and_retry_without_cross_patient_changes(isolated_store, patient_index):
    store = isolated_store
    patient = store.patients[patient_index]
    other = store.patients[1 - patient_index]
    before = call(patient, "get_today_tasks")
    other_before = call(other, "get_today_tasks")
    assert [task["status"] for task in before["tasks"]] == ["pending", "pending"]
    occurrence = before["tasks"][0]["occurrence_id"]

    saved = call(patient, "report_task_completed", {"occurrence_id": occurrence})
    assert saved["already_completed"] is False
    for _ in range(5):
        after = call(patient, "get_today_tasks")
        assert [task["status"] for task in after["tasks"]] == ["completed", "pending"]
        assert after["tasks"][0]["completed_at"] == "2026-10-23T08:00:00+01:00"
        assert call(other, "get_today_tasks") == other_before

    retry = call(patient, "report_task_completed", {"occurrence_id": occurrence})
    assert retry["already_completed"] is True
    assert call(patient, "get_today_tasks") == after
    assert len(store.events) == 1
    assert store.plans == store.original
