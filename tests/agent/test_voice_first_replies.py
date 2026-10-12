"""Voice-first replies: AfterWard never points at a screen, and "what's left" is said aloud."""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import service
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.safety import remove_screen_references


WHATS_LEFT_REPLY = (
    "After breakfast, your paracetamol and your blood thinner are next. "
    "Your knee exercises come after that."
)


@pytest.fixture
def scripted_chat(monkeypatch):
    """Run chat() with a scripted model and recorded MCP calls; no AWS."""

    run = SimpleNamespace(model_turns=[], tool_calls=[])

    def converse(**kwargs):
        message = run.model_turns.pop(0)
        stop = "tool_use" if any("toolUse" in b for b in message["content"]) else "end_turn"
        return {"output": {"message": message}, "stopReason": stop}

    async def call_tool(name, arguments):
        run.tool_calls.append(name)
        key = "tasks" if name == "get_today_tasks" else "medications"
        payload = {"ok": True, "data": {"date": "2026-10-23", key: []}}
        return SimpleNamespace(structured_content=payload, is_error=False, content=[])

    async def no_tools():
        return {"tools": []}

    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")

    def ask(message, *turns, session_id="voice-first"):
        run.model_turns = list(turns)
        return asyncio.run(service.chat(message, session_id))

    run.ask = ask
    return run


def _tool_use(name):
    return {"role": "assistant", "content": [{"toolUse": {"toolUseId": f"id-{name}", "name": name, "input": {}}}]}


def _text(text):
    return {"role": "assistant", "content": [{"text": text}]}


def test_prompt_no_longer_sends_the_patient_to_a_screen():
    assert "rest is on the screen" not in SYSTEM_PROMPT
    assert "the rest is on" not in SYSTEM_PROMPT.lower()


def test_prompt_asks_for_one_step_and_no_counts():
    assert "name ONLY\n    the next step" in SYSTEM_PROMPT
    assert "Never say how\n    many things are left" in SYSTEM_PROMPT
    assert "read them" not in SYSTEM_PROMPT
    assert "get_today_tasks AND get_medications" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Your walk is next. The rest is on your screen.", "Your walk is next."),
        ("Your walk is next. You can see the rest on screen!", "Your walk is next."),
        ("Your walk is next. Check the app for more.", "Your walk is next."),
        (WHATS_LEFT_REPLY, WHATS_LEFT_REPLY),
    ],
)
def test_screen_sentences_are_dropped(reply, expected):
    assert remove_screen_references(reply) == expected


def test_no_reply_contains_screen(scripted_chat):
    # A question the model answers ("what's left" is now answered in code).
    result = scripted_chat.ask(
        "Can you tell me about my morning?",
        _tool_use("get_today_tasks"),
        _tool_use("get_medications"),
        _text(
            "After breakfast, your paracetamol and your blood thinner are next. "
            "The rest is on your screen."
        ),
    )

    assert "screen" not in result["response"].lower()
    assert result["response"] == "After breakfast, your paracetamol and your blood thinner are next."


def test_model_reply_is_spoken_in_full(scripted_chat):
    result = scripted_chat.ask(
        "Can you tell me about my morning?",
        _tool_use("get_today_tasks"),
        _tool_use("get_medications"),
        _text(WHATS_LEFT_REPLY),
    )

    assert result["response"] == WHATS_LEFT_REPLY
    # Today's facts are read first, then the model's own reads.
    assert scripted_chat.tool_calls == ["get_today_tasks", "get_medications"] * 2


def test_fixed_replies_never_mention_a_screen():
    fixed = [service.AMBIGUOUS_MEDICATION_REPLY, *service.NOTHING_SCHEDULED_REPLIES.values()]

    assert fixed
    assert not any("screen" in reply.lower() for reply in fixed)
