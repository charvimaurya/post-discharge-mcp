"""Test context-scoped completion tools locally and optionally against DynamoDB."""

import pytest

from app.auth.patient_scope import PatientContext
from app.mcp.context import get_demo_patient_context
from app.mcp.tools import actions
from app.mcp.tools.actions import (
    report_medication_taken_for_context,
    report_task_completed_for_context,
)
from app.mcp.tools.recovery import get_today_tasks_for_context


@pytest.mark.integration
def test_report_walk_completed_twice_is_idempotent():
    context = get_demo_patient_context()

    before = get_today_tasks_for_context(context)

    walk = next(
        task
        for task in before["data"]["tasks"]
        if "walk" in task["description"].lower()
        and task.get("status", "pending") == "pending"
    )

    first = report_task_completed_for_context(context, walk["id"])
    assert first["ok"] is True
    assert first["data"]["already_completed"] is False

    second = report_task_completed_for_context(context, walk["id"])
    assert second["ok"] is True
    assert second["data"]["already_completed"] is True


def test_task_report_uses_context_patient_and_shared_clock(monkeypatch):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-03-15T09:30:00Z")
    calls = []

    def mark(patient_id, task_id, occurrence_key):
        calls.append((patient_id, task_id, occurrence_key))
        return {"success": True, "already_completed": False, "task": {"id": task_id}, "event": None}

    monkeypatch.setattr(actions, "mark_task_completed", mark)
    result = report_task_completed_for_context(PatientContext("user", "different_patient", "session"), "task_1")
    assert calls == [("different_patient", "task_1", "2026-03-15")]
    assert result["ok"] is True
    assert result["message"] == "That recovery task is now marked complete."


def test_task_report_already_completed(monkeypatch):
    monkeypatch.setattr(
        actions,
        "mark_task_completed",
        lambda *args: {"success": True, "already_completed": True, "task": {}, "event": None},
    )
    result = report_task_completed_for_context(get_demo_patient_context(), "task_1")
    assert result["ok"] is True
    assert result["message"] == "That recovery task was already marked complete."


def test_task_report_unknown_task(monkeypatch):
    def mark(*args):
        raise ValueError("Task not found: nope")

    monkeypatch.setattr(actions, "mark_task_completed", mark)
    result = report_task_completed_for_context(get_demo_patient_context(), "nope")
    assert result["ok"] is False
    assert result["error"]["code"] == "TASK_NOT_COMPLETABLE"


def test_task_report_requires_task_id():
    result = report_task_completed_for_context(get_demo_patient_context(), " ")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_TASK_ID"


def test_medication_report_builds_daily_idempotency_key(monkeypatch):
    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-03-15T09:30:00Z")
    calls = []

    def mark(patient_id, medication_id, idempotency_key):
        calls.append((patient_id, medication_id, idempotency_key))
        return {"success": True, "already_completed": False, "medication": {"id": medication_id}, "event": None}

    monkeypatch.setattr(actions, "mark_medication_taken", mark)
    result = report_medication_taken_for_context(PatientContext("user", "different_patient", "session"), "med_1")
    assert calls == [("different_patient", "med_1", "different_patient#med_1#2026-03-15")]
    assert result["ok"] is True
    assert result["message"] == "I've recorded that medication as taken."


def test_medication_report_unknown_medication(monkeypatch):
    def mark(*args):
        raise ValueError("Medication not found: nope")

    monkeypatch.setattr(actions, "mark_medication_taken", mark)
    result = report_medication_taken_for_context(get_demo_patient_context(), "nope")
    assert result["ok"] is False
    assert result["error"]["code"] == "MEDICATION_NOT_RECORDABLE"


def test_medication_report_requires_medication_id():
    result = report_medication_taken_for_context(get_demo_patient_context(), "")
    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_MEDICATION_ID"
