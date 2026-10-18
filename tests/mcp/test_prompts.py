"""Check public MCP prompt registration and rendered guidance without AWS calls."""

import asyncio

import pytest

from app.mcp.server import mcp


def prompt_text(name, arguments=None):
    result = asyncio.run(mcp.get_prompt(name, arguments))
    assert result.messages
    for message in result.messages:
        assert message.role == "user"
        assert message.content.type == "text"
        assert message.content.text.strip()
    return "\n".join(message.content.text for message in result.messages)


def test_prompts_list_exposes_both_prompts_and_their_arguments():
    prompts = {prompt.name: prompt for prompt in asyncio.run(mcp.list_prompts())}
    assert set(prompts) == {"ask_my_letter", "morning_checkin"}
    arguments = prompts["ask_my_letter"].arguments
    assert len(arguments) == 1
    assert arguments[0].name == "question"
    assert arguments[0].required is True
    assert not prompts["morning_checkin"].arguments


def test_letter_prompt_searches_first_and_requires_page_evidence():
    question = "What does my letter say about walking?"
    text = prompt_text("ask_my_letter", {"question": question})
    assert question in text
    assert "Before answering, call search_discharge_instructions FIRST" in text
    assert "patient's actual question below as the query" in text
    assert "only from relevant returned passages" in text
    assert "cite page numbers when present" in text
    assert "does not perform a search" in text
    assert "couldn't verify that from your discharge letter" in text
    assert "Do not invent medical instructions, medication changes" in text
    assert "won't guess" in text
    assert "search fails" in text


@pytest.mark.parametrize("arguments", [None, {}, {"question": None}, {"question": 42}, {"question": []}])
def test_letter_prompt_requires_a_string_question(arguments):
    with pytest.raises(ValueError):
        asyncio.run(mcp.get_prompt("ask_my_letter", arguments))


def test_morning_prompt_reads_both_tools_and_keeps_checkin_read_only():
    text = prompt_text("morning_checkin")
    assert "calling both get_today_tasks and get_medications" in text
    assert "what is done and what is next" in text
    assert "one short spoken next step" in text
    assert "needs confirmation" in text
    assert "If data is missing or either call fails" in text
    assert "actual current results, not example tasks" in text
    assert "Do not claim an item is done unless its returned status confirms it" in text
    assert "read-only: do not call" in text


def test_morning_prompt_rejects_arguments():
    with pytest.raises(ValueError):
        asyncio.run(mcp.get_prompt("morning_checkin", {"question": "unexpected"}))


def test_prompt_registration_preserves_existing_tools_and_adds_week_summary():
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == {
        "get_recovery_plan",
        "get_today_tasks",
        "get_medications",
        "search_discharge_instructions",
        "report_task_completed",
        "report_medication_taken",
        "undo_report",
        "get_week_summary",
        "get_recovery_day_details",
    }
