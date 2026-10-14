"""
Logs hold ids, counts, timings and error TYPES only: never letter text,
medicine names, chat messages or patient names.

These fail if a log line could contain letter text.
"""

import ast
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app import web_bridge
from app.agent import service
from app.ingestion import bedrock
from app.mcp import server as mcp_server
from app.observability.log import ALLOWED_FIELDS, METRICS, hash_patient
from lambdas.document_processor import handler as document_handler
from tests.conftest import log_lines


LETTER = "Apixaban 2.5 mg tablets. Take 1 tablet twice a day (morning and evening). Margaret Ellis"
MESSAGE = "I took my apixaban after breakfast"


# ---------- Behaviour: errors that carry content never reach the logs ----------

def test_document_lambda_logs_the_error_type_not_its_message(monkeypatch, capsys):
    def fail(record):
        raise ValueError(f"Could not read: {LETTER}")

    monkeypatch.setattr(document_handler, "process_sqs_record", fail)

    result = document_handler.lambda_handler({"Records": [{"messageId": "m-1234567"}]}, None)

    out = capsys.readouterr().out
    assert result == {"batchItemFailures": [{"itemIdentifier": "m-1234567"}]}
    assert '"request_id":"m-1234567"' in out and '"error_type":"ValueError"' in out
    assert "Apixaban" not in out and "Margaret" not in out and "tablet" not in out


def test_extraction_error_never_carries_letter_text(monkeypatch):
    bad = {"discharge_date": None, "medications": [{"name": LETTER, "source": {"snippet": LETTER}, "colour": LETTER}],
           "tasks": [], "appointments": [], "restrictions": [], "monitoring": [], "warning_signs": []}
    client = SimpleNamespace(converse=lambda **kw: {
        "stopReason": "tool_use", "usage": {},
        "output": {"message": {"content": [{"toolUse": {"input": bad}}]}},
    })
    monkeypatch.setattr(bedrock, "_bedrock", lambda: client)

    with pytest.raises(ValueError) as caught:
        bedrock.invoke_extraction_model("Synthetic text")

    assert "Apixaban" not in str(caught.value) and "Margaret" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.fixture
def failing_bridge(monkeypatch):
    async def agent_fails(*args, **kwargs):
        raise RuntimeError(f"Bedrock rejected: {MESSAGE} / {LETTER}")

    async def tool_fails(name, arguments):
        raise RuntimeError(f"MCP said: {LETTER}")

    monkeypatch.setattr(web_bridge, "chat", agent_fails)
    monkeypatch.setattr(web_bridge, "call_mcp_tool", tool_fails)
    monkeypatch.setattr(web_bridge, "get_recovery_state", lambda patient_id: {"first_name": "Margaret"})
    monkeypatch.setattr(web_bridge, "record_chat_activity", lambda patient_id, at: None)
    return TestClient(web_bridge.app)


def test_bridge_chat_failure_logs_no_content(failing_bridge, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        response = failing_bridge.post("/chat", json={"message": MESSAGE, "session_id": "s"})

    assert response.status_code == 502
    logged = caplog.text + capsys.readouterr().out
    assert "RuntimeError" in logged
    for secret in ("apixaban", "Apixaban", "breakfast", "Margaret", "tablet"):
        assert secret not in logged
    assert all(record.exc_info is None for record in caplog.records)


def test_bridge_today_failure_logs_no_content(failing_bridge, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        assert failing_bridge.get("/today").status_code == 502

    logged = caplog.text + capsys.readouterr().out
    assert "today_failed" in logged
    assert "Apixaban" not in logged and "Margaret" not in logged


# ---------- A full chat turn and a full upload: nothing from the letter in any log line ----------

# Words that appear in the message, the letter, the plan and the replies below.
SECRETS = ("Apixaban", "apixaban", "Paracetamol", "paracetamol", "Margaret", "Ellis", "tablet",
           "breakfast", "bath", "wound", "2.5 mg", "blood thinner")
BATH = "Do not have a bath or go swimming until the wound has healed."


def _assert_no_content(logged: str):
    lines = log_lines(logged)
    assert lines, "expected structured log lines"

    for secret in SECRETS:
        assert secret not in logged, f"{secret!r} reached a log line"

    for line in lines:
        assert set(line) <= ALLOWED_FIELDS | set(METRICS) | {"timestamp", "level", "service", "dropped_fields", "_aws"}

    return lines


@pytest.fixture
def full_bridge(monkeypatch, mcp_hop):
    """The real bridge, agent and MCP tool logging, with a plan and a model that are full of letter text."""

    medications = [
        {"occurrence_id": f"{med}#2026-10-23#1", "medication_id": med, "name": name, "dose": dose,
         "instructions": "Take the morning dose after breakfast.", "time_of_day_label": "morning",
         "occurrence_number": 1, "status": "pending",
         "source": {"snippet": LETTER, "page": 1}}
        for med, name, dose in [("apix", "Apixaban", "1 tablet"), ("para", "Paracetamol", "2 tablets")]
    ]
    saved = []

    def taken(context, occurrence_id):
        saved.append(occurrence_id)
        return {"ok": True, "data": {"occurrence_id": occurrence_id, "name": "Apixaban"}}

    monkeypatch.setattr(mcp_server, "get_today_tasks_for_context",
                        lambda context: {"ok": True, "data": {"date": "2026-10-23", "tasks": []}})
    monkeypatch.setattr(mcp_server, "get_medications_for_context",
                        lambda context: {"ok": True, "data": {"date": "2026-10-23", "medications": medications}})
    monkeypatch.setattr(mcp_server, "report_medication_taken_for_context", taken)
    monkeypatch.setattr(mcp_server, "get_recovery_plan_for_context",
                        lambda context: {"ok": True, "data": {"patient_name": "Margaret Ellis", "restrictions": [{"text": BATH}]}})
    monkeypatch.setattr(mcp_server, "search_discharge_instructions_for_context",
                        lambda context, query: {"ok": True, "data": {"matches": [
                            {"text": BATH, "page": 1, "chunk_id": "c1", "document_id": "doc", "score": 0.9}]}})

    turns = [
        {"role": "assistant", "content": [{"toolUse": {
            "toolUseId": "t1", "name": "search_discharge_instructions", "input": {"query": "bath wound"}}}]},
        {"role": "assistant", "content": [{"text": f"Margaret, your letter says: {BATH}"}]},
    ]

    def converse(**kwargs):
        message = turns.pop(0)
        stop = "tool_use" if any("toolUse" in block for block in message["content"]) else "end_turn"
        return {"output": {"message": message}, "stopReason": stop, "usage": {"inputTokens": 900, "outputTokens": 40}}

    async def tools():
        return SimpleNamespace(tools=[SimpleNamespace(
            name="search_discharge_instructions", description="Search the letter.",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})])

    monkeypatch.setattr(service, "call_mcp_tool", mcp_hop)
    monkeypatch.setattr(web_bridge, "call_mcp_tool", mcp_hop)
    monkeypatch.setattr(service, "get_mcp_tools", tools)
    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(web_bridge, "get_recovery_state",
                        lambda patient_id: {"first_name": "Margaret", "patient_name": "Margaret Ellis"})
    monkeypatch.setattr(web_bridge, "record_chat_activity", lambda patient_id, at: None)

    return SimpleNamespace(client=TestClient(web_bridge.app), saved=saved)


def test_full_chat_turns_log_no_content(full_bridge, caplog, capsys):
    with caplog.at_level(logging.DEBUG):
        # A report that is saved (a write), a report that is refused, and a letter question for the model.
        saved = full_bridge.client.post("/chat", json={"message": "I've taken my apixaban after breakfast", "session_id": "s-full"})
        refused = full_bridge.client.post("/chat", json={"message": "No, I haven't taken my paracetamol tablets", "session_id": "s-full-2"})
        asked = full_bridge.client.post("/chat", json={"message": "Margaret Ellis here, can I have a bath?", "session_id": "s-full-3"})

    assert saved.status_code == refused.status_code == asked.status_code == 200
    assert full_bridge.saved == ["apix#2026-10-23#1"]
    assert "bath" in asked.json()["response"]

    lines = _assert_no_content(caplog.text + capsys.readouterr().out)
    events = {line["event"] for line in lines}

    assert {"request_start", "request_end", "agent_turn", "tool_call"} <= events
    assert any(line["event"] == "tool_call" and line["kind"] == "write" and line["status"] == "ok" for line in lines)
    assert any(line["event"] == "agent_turn" and line.get("kind") == "model" for line in lines)
    assert "s-full" not in json.dumps(lines)


def test_refused_write_is_logged_with_a_reason_code_only(full_bridge, capsys):
    full_bridge.client.post("/chat", json={"message": "No, I haven't taken my paracetamol tablets", "session_id": "s-no"})

    lines = _assert_no_content(capsys.readouterr().out)
    blocked = [line for line in lines if line["event"] == "write_blocked"]

    assert full_bridge.saved == []
    assert blocked and all(line["blocked_writes"] == 1 and line["reason"] for line in blocked)


def test_full_upload_logs_no_content(monkeypatch, caplog, capsys):
    from app.ingestion import document_service, pipeline

    extracted = {
        "discharge_date": "2026-10-16",
        "medications": [{"name": "Apixaban", "strength": "2.5 mg", "dose": "1 tablet",
                         "frequency": "twice a day", "time_of_day": ["morning", "evening"],
                         "instructions": "Take the morning dose after breakfast.",
                         "source": {"snippet": LETTER, "page": 1}}],
        "tasks": [], "appointments": [], "monitoring": [], "warning_signs": [],
        "restrictions": [{"text": BATH, "source": {"snippet": BATH, "page": 1}}],
    }
    pages = [{"page": 1, "text": f"Patient: Margaret Ellis\n{LETTER}\n{BATH}"}]
    saved = []

    monkeypatch.setattr(document_service, "get_recovery_state", lambda patient_id: None)
    monkeypatch.setattr(document_service, "download_document", lambda key: b"%PDF-synthetic")
    monkeypatch.setattr(document_service, "save_recovery_state", saved.append)
    monkeypatch.setattr(document_service, "index_document_pages", lambda **kwargs: 3)
    monkeypatch.setattr(pipeline, "extract_document_pages", lambda **kwargs: pages)
    monkeypatch.setattr(pipeline, "validate_discharge_document", lambda text: None)
    monkeypatch.setattr(pipeline, "invoke_extraction_model", lambda text: extracted)

    body = json.dumps({"Records": [{
        "eventTime": "2026-10-11T16:28:02.000Z",
        "s3": {"object": {"key": "patients/demo_patient_001/documents/ui_44cf2b4c767a0f0e.pdf"}},
    }]})

    with caplog.at_level(logging.DEBUG):
        result = document_handler.lambda_handler({"Records": [{"messageId": "msg-0123456789", "body": body}]}, None)

    assert result == {"batchItemFailures": []}
    assert saved and saved[-1].ingestion_status == "ready"
    assert saved[-1].medications[0].name == "Apixaban"

    lines = _assert_no_content(caplog.text + capsys.readouterr().out)
    stages = [line["stage"] for line in lines if "stage" in line]

    assert stages == ["received", "downloaded", "extracted", "checked", "saved", "indexed", "ready"]
    assert {line["request_id"] for line in lines} == {"msg-0123456789"}
    # The patient is logged as a hash only, never as the id itself.
    received = next(line for line in lines if line.get("stage") == "received")
    assert received["patient_id_hash"] == hash_patient("demo_patient_001")
    assert all("patient_id" not in line for line in lines)
    assert "demo_patient_001" not in json.dumps(lines)
    ready = lines[-1]
    assert ready["event"] == "ingest_ready" and ready["document_id"] == "ui_44cf2b4c767a0f0e"
    assert ready["item_count"] == 2 and isinstance(ready["needs_confirmation_count"], int)
    assert ready["upload_to_ready_ms"] >= 0 and ready["_aws"]["CloudWatchMetrics"][0]["Metrics"][0]["Name"] == "upload_to_ready_ms"


# ---------- Source scan: what every print / log call is allowed to use ----------

# Names that hold patient content. A log may only use them inside these calls.
CONTENT_NAMES = {
    "text", "message", "messages", "snippet", "passage", "response", "response_text", "reply",
    "description", "name", "first_name", "patient_name", "extracted", "state", "letter",
    "document_text", "body", "item", "occurrence", "dose", "medication", "medications", "task",
    "tasks", "cleaned_message", "pages", "page_text", "chunk", "exc", "error", "err", "e",
    "arguments", "result", "structured_result", "pending_checkin", "source",
}
SAFE_WRAPPERS = {"safe_error", "len", "type"}
LOG_METHODS = {"debug", "info", "warning", "error", "critical", "exception", "log"}


def _log_calls(tree):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"print", "log", "log_event"}:
            yield node
        elif isinstance(func, ast.Attribute) and func.attr in LOG_METHODS and isinstance(func.value, ast.Name) \
                and func.value.id in {"logger", "logging", "log"}:
            yield node


def _content_names_used(expr):
    """Names in expr, ignoring anything passed through safe_error / len / type."""

    found = set()

    def visit(node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in SAFE_WRAPPERS:
            return
        if isinstance(node, ast.Name) and node.id in CONTENT_NAMES:
            found.add(node.id)
        if isinstance(node, ast.Attribute) and node.attr in CONTENT_NAMES:
            found.add(node.attr)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(expr)
    return found


def _sources():
    for root in ("app", "lambdas"):
        for path in sorted(Path(root).rglob("*.py")):
            yield path, ast.parse(path.read_text())


def test_no_log_line_uses_patient_content():
    problems = []

    for path, tree in _sources():
        for call in _log_calls(tree):
            used = set()
            # error= takes the exception itself; the log module writes only its type.
            for arg in list(call.args) + [kw.value for kw in call.keywords if kw.arg != "error"]:
                used |= _content_names_used(arg)
            if used:
                problems.append(f"{path}:{call.lineno} logs {sorted(used)}")

    assert problems == [], "Log lines must hold ids, counts and error types only:\n" + "\n".join(problems)


def test_no_logger_exception_tracebacks():
    """A traceback prints the exception message, which can quote letter text."""

    found = [
        f"{path}:{call.lineno}"
        for path, tree in _sources()
        for call in _log_calls(tree)
        if isinstance(call.func, ast.Attribute) and call.func.attr == "exception"
    ]

    assert found == []


def test_structured_log_calls_use_only_allowed_field_names():
    """A field that is not on the allowlist is dropped at run time; this catches it before then."""

    problems = []

    for path, tree in _sources():
        if path == Path("app/observability/log.py"):
            continue
        for call in _log_calls(tree):
            if not (isinstance(call.func, ast.Name) and call.func.id in {"log", "log_event"}):
                continue
            unknown = {kw.arg for kw in call.keywords if kw.arg} - ALLOWED_FIELDS - set(METRICS) - {"level", "error", "service"}
            if unknown:
                problems.append(f"{path}:{call.lineno} logs unknown fields {sorted(unknown)}")

    assert problems == []


def test_only_the_log_module_writes_log_lines():
    """No print() and no logging calls in the app: every line goes through app/observability/log.py."""

    found = [
        f"{path}:{call.lineno}"
        for path, tree in _sources()
        for call in _log_calls(tree)
        if not (isinstance(call.func, ast.Name) and call.func.id in {"log", "log_event"})
    ]

    assert found == []
