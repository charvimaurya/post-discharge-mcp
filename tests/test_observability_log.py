"""
The shared log module (app/observability/log.py): what a line may hold,
and one request id from the bridge through the agent to the MCP tools.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app import web_bridge
from app.agent import service
from app.mcp import server
from app.observability import log as obs
from tests.conftest import log_lines


LETTER = "Apixaban 2.5 mg tablets. Take 1 tablet twice a day."


def _last(capsys) -> dict:
    return log_lines(capsys.readouterr().out)[-1]


# ---------- What a line may hold ----------

def test_line_has_the_standard_fields(capsys):
    token = obs.set_request_id("req-12345678")
    obs.service_log("bridge")("request_end", route="/chat", status=200, ms=41)
    obs.reset_request_id(token)

    line = _last(capsys)

    assert line["service"] == "bridge" and line["event"] == "request_end" and line["level"] == "info"
    assert line["request_id"] == "req-12345678"
    assert line["route"] == "/chat" and line["status"] == 200 and line["ms"] == 41
    assert line["timestamp"].endswith("+00:00")


def test_unknown_fields_are_dropped_and_counted(capsys):
    before = obs.dropped_fields_total()

    obs.log_event("tool_call", tool="get_medications", message=LETTER, reply="Take it now", medicine="Apixaban")

    line = _last(capsys)
    assert line["tool"] == "get_medications"
    assert line["dropped_fields"] == 3
    assert not {"message", "reply", "medicine"} & set(line)
    assert obs.dropped_fields_total() == before + 3
    assert "Apixaban" not in json.dumps(line)


@pytest.mark.parametrize("value", [LETTER, "Margaret Ellis", "2 tablets", {"name": "Apixaban"}, ["Apixaban"]])
def test_an_allowed_name_cannot_carry_a_sentence(capsys, value):
    obs.log_event("write_blocked", reason=value, tool="report_medication_taken")

    line = _last(capsys)
    assert "reason" not in line and line["dropped_fields"] == 1
    assert line["tool"] == "report_medication_taken"


def test_errors_are_logged_by_type_only(capsys):
    obs.log_event("chat_failed", level="error", error=ValueError(f"Could not read: {LETTER}"))

    line = _last(capsys)
    assert line["error_type"] == "ValueError" and line["level"] == "error"
    assert "Apixaban" not in json.dumps(line)


def test_event_name_must_be_a_code(capsys):
    obs.log_event(LETTER)

    assert _last(capsys)["event"] == "invalid_event"


def test_request_id_from_a_header_is_checked():
    assert obs.clean_request_id("abc12345-def") == "abc12345-def"
    assert obs.clean_request_id("x") is None
    assert obs.clean_request_id("Margaret Ellis took apixaban") is None
    assert obs.clean_request_id(None) is None


def test_session_id_is_hashed():
    hashed = obs.hash_session("session-abc")

    assert hashed == obs.hash_session("session-abc") and len(hashed) == 12
    assert "session" not in hashed and obs.hash_session(None) is None


def test_patient_id_is_hashed_and_never_logged_as_it_is(capsys):
    hashed = obs.hash_patient("demo_patient_001")

    assert hashed == obs.hash_patient("demo_patient_001") and len(hashed) == 12
    assert "patient" not in hashed and obs.hash_patient(None) is None
    # The same short hash as sessions use, so one rule covers both.
    assert hashed == obs.hash_session("demo_patient_001")

    obs.service_log("bridge")("probe", patient_id="demo_patient_001", patient_id_hash=hashed)
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert "patient_id" not in line and line["patient_id_hash"] == hashed
    assert line["dropped_fields"] == 1
    assert "demo_patient_001" not in json.dumps(line)


def test_metrics_use_the_embedded_metric_format(capsys):
    obs.service_log("mcp")("tool_call", tool="get_medications", ms=41, tool_ms=41, tool_errors=0)

    line = _last(capsys)
    block = line["_aws"]["CloudWatchMetrics"][0]

    assert block["Namespace"] == "AfterWard" and block["Dimensions"] == [["service"]]
    assert {"Name": "tool_ms", "Unit": "Milliseconds"} in block["Metrics"]
    assert {"Name": "tool_errors", "Unit": "Count"} in block["Metrics"]
    assert line["tool_ms"] == 41 and line["service"] == "mcp"
    assert isinstance(line["_aws"]["Timestamp"], int)


def test_a_plain_line_has_no_metric_block(capsys):
    obs.log_event("request_start", route="/today")

    assert "_aws" not in _last(capsys)


# ---------- One request id, end to end ----------

@pytest.fixture
def chat_bridge(monkeypatch, mcp_hop):
    """The real bridge, agent, MCP middleware and tool logging. Scripted model, fake plan data."""

    tasks = [{"occurrence_id": "walk#2026-10-23#1", "task_id": "walk", "description": "Short walk",
              "clock_time": "07:30", "occurrence_number": 1, "status": "pending"}]

    monkeypatch.setattr(server, "get_today_tasks_for_context",
                        lambda context: {"ok": True, "data": {"date": "2026-10-23", "tasks": tasks}})
    monkeypatch.setattr(server, "get_medications_for_context",
                        lambda context: {"ok": True, "data": {"date": "2026-10-23", "medications": []}})
    monkeypatch.setattr(server, "search_discharge_instructions_for_context",
                        lambda context, query: {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE", "message": LETTER}})

    def converse(**kwargs):
        text = {"role": "assistant", "content": [{"text": "Your letter does not say."}]}
        return {"output": {"message": text}, "stopReason": "end_turn",
                "usage": {"inputTokens": 1200, "outputTokens": 30}}

    async def no_tools():
        return SimpleNamespace(tools=[])

    monkeypatch.setattr(service, "call_mcp_tool", mcp_hop)
    monkeypatch.setattr(web_bridge, "call_mcp_tool", mcp_hop)
    monkeypatch.setattr(service, "get_mcp_tools", no_tools)
    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model-1")
    monkeypatch.setattr(web_bridge, "get_recovery_state", lambda patient_id: {"first_name": "Margaret"})
    monkeypatch.setattr(web_bridge, "record_chat_activity", lambda patient_id, at: None)

    return TestClient(web_bridge.app)


def test_one_request_id_in_bridge_agent_and_tool_logs(chat_bridge, capsys):
    response = chat_bridge.post("/chat", json={"message": "Is there a film on tonight?", "session_id": "s-1"},
                                headers={"X-Request-ID": "web-0123456789abcdef"})

    assert response.status_code == 200
    assert response.json()["request_id"] == "web-0123456789abcdef"
    assert response.headers["x-request-id"] == "web-0123456789abcdef"

    lines = log_lines(capsys.readouterr().out)
    by_service = {}
    for line in lines:
        by_service.setdefault(line["service"], []).append(line)

    assert {"bridge", "agent", "mcp"} <= set(by_service)
    assert {line["request_id"] for line in lines} == {"web-0123456789abcdef"}

    events = [line["event"] for line in by_service["bridge"]]
    assert events[0] == "request_start" and events[-1] == "request_end"
    end = by_service["bridge"][-1]
    assert end["route"] == "/chat" and end["status"] == 200 and isinstance(end["ms"], int)

    tools = [line for line in by_service["mcp"] if line["event"] == "tool_call"]
    assert {line["tool"] for line in tools} >= {"get_today_tasks", "get_medications"}
    assert all(line["kind"] == "read" and line["status"] == "ok" and "tool_ms" in line for line in tools)

    turn = next(line for line in by_service["agent"] if line["event"] == "agent_turn")
    assert turn["kind"] == "model" and turn["model"] == "test-model-1"
    assert turn["tokens_in"] == 1200 and turn["tokens_out"] == 30
    assert turn["tool_calls"] >= 2 and turn["status"] == "ok"
    assert turn["session_id_hash"] == obs.hash_session("s-1") and "chat_ms" in turn


def test_bridge_makes_a_request_id_when_none_is_sent(chat_bridge, capsys):
    response = chat_bridge.get("/today")

    request_id = response.headers["x-request-id"]
    lines = log_lines(capsys.readouterr().out)

    assert obs.clean_request_id(request_id) == request_id
    assert lines and {line["request_id"] for line in lines} == {request_id}


def test_a_rejected_tool_result_is_not_a_tool_error(mcp_hop, monkeypatch, capsys):
    monkeypatch.setattr(server, "search_discharge_instructions_for_context",
                        lambda context, query: {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE", "message": LETTER}})

    asyncio.run(mcp_hop("search_discharge_instructions", {"query": "apixaban"}))

    line = _last(capsys)
    assert line["status"] == "rejected" and line["error_code"] == "INSUFFICIENT_EVIDENCE"
    assert line["tool_errors"] == 0 and "Apixaban" not in json.dumps(line)


def test_a_tool_that_raises_counts_as_a_tool_error(mcp_hop, monkeypatch, capsys):
    def broken(context):
        raise RuntimeError(f"DynamoDB said: {LETTER}")

    monkeypatch.setattr(server, "get_medications_for_context", broken)

    with pytest.raises(RuntimeError):
        asyncio.run(mcp_hop("get_medications", {}))

    line = _last(capsys)
    assert line["status"] == "error" and line["error_type"] == "RuntimeError" and line["tool_errors"] == 1
    assert "Apixaban" not in json.dumps(line)
