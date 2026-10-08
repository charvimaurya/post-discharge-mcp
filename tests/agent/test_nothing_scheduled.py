"""The agent's reply when a completion is reported but nothing is scheduled."""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import service


def _tool_use(name, tool_id="t1", arguments=None):
    return {
        "role": "assistant",
        "content": [{"toolUse": {"toolUseId": tool_id, "name": name, "input": arguments or {}}}],
    }


def _text(text):
    return {"role": "assistant", "content": [{"text": text}]}


def _run(monkeypatch, message, model_messages, tool_payloads):
    """Run chat() with scripted model turns and MCP results."""

    turns = iter(model_messages)

    def converse(**kwargs):
        message = next(turns)
        stop = "tool_use" if any("toolUse" in b for b in message["content"]) else "end_turn"
        return {"output": {"message": message}, "stopReason": stop}

    async def call_tool(name, arguments):
        return SimpleNamespace(structured_content=tool_payloads[name], is_error=False, content=[])

    async def tools():
        return {"tools": []}

    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service, "build_bedrock_tool_config", tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")

    return asyncio.run(service.chat(message, f"test-{message}"))


@pytest.mark.parametrize("message,read_tool,field,expected", [
    ("I've taken my morning paracetamol.", "get_medications", "medications",
     "There's no matching dose scheduled for today."),
    ("I'm back from my walk.", "get_today_tasks", "tasks",
     "There's no matching task scheduled for today."),
])
def test_completion_with_empty_schedule_gets_fixed_reply(monkeypatch, message, read_tool, field, expected):
    result = _run(
        monkeypatch,
        message,
        # The model apologises; the fixed reply must replace it, with no write nudge.
        [_tool_use(read_tool), _text("Sorry, I can't find that on your list.")],
        {read_tool: {"ok": True, "data": {field: []}}},
    )
    assert result["response"] == expected
    assert [t["tool"] for t in result["tool_trace"]] == [read_tool]


def test_evidence_tag_is_stripped_and_drives_the_source(monkeypatch):
    chunk = {
        "chunk_id": "doc_p1_c9", "document_id": "doc", "page": 2,
        "text": "MEDICINES\n1.\nDrug X 5 mg. Take once a day. Continue as directed.",
    }
    result = _run(
        monkeypatch,
        "How long do I take it for?",
        [
            _tool_use("search_discharge_instructions", arguments={"query": "how long"}),
            _text("The letter says continue as directed, so no end date is stated."
                  " [[evidence: doc_p1_c9 | Continue as directed.]]"),
        ],
        {"search_discharge_instructions": {"ok": True, "data": [chunk]}},
    )
    assert result["response"] == "The letter says continue as directed, so no end date is stated."
    assert result["source"]["chunk_id"] == "doc_p1_c9"
    assert "Continue as directed." in result["source"]["highlighted_line"]
