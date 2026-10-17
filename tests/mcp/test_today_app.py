"""MCP App registration, real SDK result shape, and standalone JavaScript checks."""

import asyncio
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app.auth.patient_scope import PatientContext
from app.mcp.context import reset_current_patient_context, set_current_patient_context
from app.mcp.server import mcp


URI = "ui://afterward/today.html"
MIME = "text/html;profile=mcp-app"


def test_today_resource_is_discoverable_and_has_app_mime_type():
    resources = {str(resource.uri): resource for resource in asyncio.run(mcp.list_resources())}
    assert resources[URI].mime_type == MIME


def test_today_resource_read_returns_standalone_html():
    contents = list(asyncio.run(mcp.read_resource(URI)))
    assert len(contents) == 1
    assert contents[0].mime_type == MIME
    html = contents[0].content
    assert html == (Path(__file__).parents[2] / "app/mcp/ui/today.html").read_text()
    assert html.startswith("<!DOCTYPE html>")
    assert "Waiting for today's plan" in html
    assert '<h1 id="heading">Today</h1>' in html
    assert "innerHTML" not in html
    assert '<script src=' not in html
    assert '@import' not in html
    assert 'url(' not in html
    assert contents[0].meta["ui"]["csp"] == {"connectDomains": [], "resourceDomains": []}


def test_today_tool_has_ui_link_and_existing_prompts_remain():
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert len(tools) == 7
    assert tools["get_today_tasks"].model_dump(by_alias=True)["_meta"]["ui"]["resourceUri"] == URI
    assert tools["get_today_tasks"].input_schema.get("properties", {}) == {}
    assert all(tool.meta is None for name, tool in tools.items() if name != "get_today_tasks")
    assert {prompt.name for prompt in asyncio.run(mcp.list_prompts())} == {"ask_my_letter", "morning_checkin"}


def test_today_card_javascript_with_real_sdk_result(monkeypatch):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the standalone MCP App JavaScript checks")
    from app.mcp.tools import recovery

    tasks = [
        {"description": "Walk", "status": "completed", "completed_at": "2026-10-17T08:10:00Z", "clock_time": "08:00"},
        {"description": "Confirm exercise plan", "status": "pending", "needs_confirmation": True, "clock_time": "08:30"},
        {"description": "Gentle exercise", "status": "pending", "clock_time": "09:00"},
        {"description": "Rest", "status": "pending", "time_of_day_label": "Afternoon"},
    ]
    patients = []

    def read(patient_id, date):
        patients.append(patient_id)
        return tasks

    monkeypatch.setattr(recovery, "get_today_tasks", read)
    monkeypatch.setattr(recovery, "get_recovery_state", lambda patient: {"timezone": "Europe/London"})
    token = set_current_patient_context(PatientContext("test_user", "scoped_test_patient", "test_session"))
    try:
        result = asyncio.run(mcp.call_tool("get_today_tasks", {}))
    finally:
        reset_current_patient_context(token)
    assert patients == ["scoped_test_patient"]
    actual_payload = result.structured_content or json.loads(result.content[0].text)
    assert actual_payload["data"]["tasks"] == tasks
    completed = subprocess.run(
        [node, str(Path(__file__).with_name("today_ui_checks.cjs"))],
        input=json.dumps(result.model_dump(by_alias=True, exclude_none=True)),
        text=True, capture_output=True, timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "14 UI checks passed" in completed.stdout
