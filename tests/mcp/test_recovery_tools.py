"""Test context-scoped recovery reads locally and optionally against DynamoDB."""

import pytest

from app.mcp.context import (
    get_demo_patient_context,
)

from app.mcp.tools.recovery import (
    get_recovery_plan_for_context,
)


@pytest.mark.integration
def test_get_recovery_plan_returns_real_state():

    context = get_demo_patient_context()

    result = get_recovery_plan_for_context(
        context
    )

    assert result["ok"] is True

    plan = result["data"]

    assert (
        plan["patient_id"]
        == "demo_patient_001"
    )

    assert "medications" in plan
    assert "tasks" in plan
    assert "appointments" in plan
    assert "restrictions" in plan
    assert "monitoring" in plan
    assert "warning_signs" in plan


def test_demo_context():
    context = get_demo_patient_context()
    assert context.user_id == "demo_user_001"
    assert context.patient_id == "demo_patient_001"
    assert context.session_id == "demo_session_001"


def test_recovery_read_uses_context_patient(monkeypatch):
    from app.auth.patient_scope import PatientContext
    from app.mcp.tools import recovery
    from decimal import Decimal

    calls = []
    def read(patient_id):
        calls.append(patient_id)
        return {"patient_id": patient_id, "medications": [{"times_per_day": Decimal(3)}]}

    monkeypatch.setattr(recovery, "get_recovery_state", read)
    result = get_recovery_plan_for_context(PatientContext("user", "different_patient", "session"))
    assert calls == ["different_patient"]
    assert result["ok"] is True
    assert result["data"]["medications"][0]["times_per_day"] == 3


def test_missing_recovery_plan(monkeypatch):
    from app.mcp.tools import recovery
    monkeypatch.setattr(recovery, "get_recovery_state", lambda patient_id: None)
    result = get_recovery_plan_for_context(get_demo_patient_context())
    assert result["ok"] is False
    assert result["error"]["code"] == "RECOVERY_PLAN_NOT_FOUND"


def test_today_tasks_uses_context_patient_and_shared_clock(monkeypatch):
    from app.auth.patient_scope import PatientContext
    from app.mcp.tools import recovery

    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-03-15T09:30:00Z")
    calls = []

    def read(patient_id, date):
        calls.append((patient_id, date))
        return [{"id": "task_1", "description": "Walk"}]

    monkeypatch.setattr(recovery, "get_today_tasks", read)
    result = recovery.get_today_tasks_for_context(PatientContext("user", "different_patient", "session"))
    assert calls == [("different_patient", "2026-03-15")]
    assert result["ok"] is True
    assert result["data"] == {"date": "2026-03-15", "tasks": [{"id": "task_1", "description": "Walk"}]}
    assert result["message"] == "You have 1 recovery items today."


def test_empty_day_messages_say_nothing_is_scheduled(monkeypatch):
    from app.auth.patient_scope import PatientContext
    from app.mcp.tools import recovery

    monkeypatch.setattr(recovery, "get_today_tasks", lambda *args: [])
    monkeypatch.setattr(recovery, "get_medications", lambda *args: [])
    context = PatientContext("user", "patient", "session")
    assert recovery.get_today_tasks_for_context(context)["message"] == (
        "There are no recovery tasks scheduled for today."
    )
    assert recovery.get_medications_for_context(context)["message"] == (
        "There are no medication doses scheduled for today."
    )
