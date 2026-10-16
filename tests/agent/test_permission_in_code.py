"""'Can I drive?' answered from her plan's restrictions, word for word, with no model; anything else goes to the model."""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import service
from app.agent.session import clear_session

DRIVE = "Do not drive until your consultant has reviewed you at your 6-week appointment and told you it is safe."
BATH = "Do not have a bath or go swimming until the wound has healed. Showering is fine if the dressing stays dry."
KNEEL = "Do not kneel on the operated knee."
REVIEW = "Consultant review: Monday 23 November 2026, 9:15 am, Orthopaedic Clinic."
PLAN = {
    "restrictions": [{"text": t, "source": {"snippet": t, "page": 1}} for t in (DRIVE, KNEEL, BATH)],
    "appointments": [{"title": "Consultant review", "date": "2026-11-23", "source": {"snippet": REVIEW, "page": 2}}],
}
MODEL_ANSWER = "Model answer."


@pytest.fixture
def agent(monkeypatch):
    run = SimpleNamespace(model_calls=0)

    async def call_tool(name, arguments):
        data = {"get_today_tasks": {"date": "2026-10-23", "tasks": []},
                "get_medications": {"date": "2026-10-23", "medications": []},
                "get_recovery_plan": PLAN}[name]
        return SimpleNamespace(structured_content={"ok": True, "data": data}, is_error=False, content=[])

    def converse(**kwargs):
        run.model_calls += 1
        return {"output": {"message": {"role": "assistant", "content": [{"text": MODEL_ANSWER}]}}, "stopReason": "end_turn"}

    async def no_tools():
        return {"tools": []}

    monkeypatch.setenv("DEMO_FIXED_NOW", "2026-10-23T09:30:00+01:00")
    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    monkeypatch.setattr(service.bedrock, "converse", converse)
    monkeypatch.setattr(service, "build_bedrock_tool_config", no_tools)
    monkeypatch.setattr(service, "get_agent_model_id", lambda: "test-model")

    def say(message):
        clear_session("s-permission")
        return asyncio.run(service.chat(message, "s-permission", first_name="Margaret"))

    run.say = say
    return run


def test_a_driving_question_is_answered_from_the_letter_without_the_model(agent):
    result = agent.say("when can I plan to go for a drive")

    assert result["response"] == f"Your letter says: {DRIVE} Your consultant review is on Monday 23 November."
    assert result["source"]["highlight"] == DRIVE and result["source"]["page"] == 1
    assert agent.model_calls == 0


def test_a_shower_question_quotes_the_line_that_covers_it_and_never_adds_yes(agent):
    result = agent.say("can I have a shower")

    assert result["response"] == f"Your letter says: {BATH}"
    assert "yes" not in result["response"].lower() and agent.model_calls == 0


@pytest.mark.parametrize("message", [
    "can I go to the gym",               # nothing in her plan about it
    "can I drive and have a bath",       # two things at once
    "can I drive to the shops tomorrow",  # asks more than the restriction says
])
def test_anything_else_goes_to_the_model(agent, message):
    result = agent.say(message)

    assert agent.model_calls >= 1 and result["response"] == MODEL_ANSWER
