"""The MCP App and the web app show the same daily counts from one get_week_summary result."""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.auth.patient_scope import PatientContext
from app.mcp import server
from app.mcp.context import reset_current_patient_context, set_current_patient_context
from app.mcp.tools import week
from tests.mcp.week_seed import seed_week_events

PATIENT = "isolated_week_demo"
NOW = datetime.fromisoformat("2026-10-23T08:00:00+01:00")


def test_mcp_app_and_web_app_show_the_same_days(monkeypatch):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to run the two screens' scripts")

    events = seed_week_events(PATIENT, NOW)
    # One task recorded today, as report_task_completed would save it.
    events.append({"patient_id": PATIENT, "timestamp": "event#today-walk", "event_type": "task_completed",
                   "idempotency_key": "today-walk", "details": {"date": "2026-10-23",
                   "occurrence_id": "task_walk#2026-10-23#1", "completed_at": "2026-10-23T07:40:00+01:00"}})
    monkeypatch.setenv("DEMO_FIXED_NOW", NOW.isoformat())
    monkeypatch.setattr(week, "get_complete_patient_events", lambda patient: events)
    monkeypatch.setattr(week, "get_recovery_state", lambda patient: {"timezone": "Europe/London"})
    monkeypatch.setattr(week, "get_today_tasks_for_context",
                        lambda context: {"ok": True, "data": {"date": "2026-10-23", "tasks": []}})
    token = set_current_patient_context(PatientContext("test", PATIENT, "isolated"))
    try:
        result = asyncio.run(server.get_week_summary())
    finally:
        reset_current_patient_context(token)

    completed = subprocess.run(
        [node, "--experimental-strip-types", "--no-warnings", str(Path(__file__).with_name("week_parity_check.mjs"))],
        input=json.dumps({"structuredContent": result}), text=True, capture_output=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    shown = json.loads(completed.stdout)

    # Task counts come only from saved task events, and both screens show exactly those.
    assert shown["raw"] == [2, 3, 1, 3, 2, 0, 1]
    assert shown["web_tasks"] == shown["app_tasks"] == shown["raw"]
    # Morning medicines are a separate series with their own statuses.
    assert shown["web_medicines"] == shown["app_medicines"] == ["completed"] * 5 + ["missed", "not_yet_due"]
    assert shown["web_medicine_days"] == 5
    assert shown["app_medicine_summary"] == "5 of 7 days: all morning medicines taken"
