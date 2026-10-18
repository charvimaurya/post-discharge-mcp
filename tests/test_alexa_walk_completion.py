"""Offline model coverage and real handler/agent/persistence with in-memory storage.

Template matching verifies sample coverage, not Amazon's hosted NLU or speech recognition.
"""
from copy import deepcopy
import json
import re
from types import SimpleNamespace

import pytest

from app.agent import service
from app.agent.session import clear_session
from app.alexa import handlers
from app.auth.patient_scope import PatientContext
from app.database import recovery_state
from app.mcp.tools import actions, recovery
from tests.test_alexa import alexa, _intent  # Reuse the actual ASK HTTP request fixture.

DAY = "2026-10-23"
PATIENT = "isolated_alexa_walk"
PHRASES = [
    ("I just came back from my walk", "CameBackFromIntent", "my walk", "I just came back from my walk"),
    ("I finished my morning walk", "FinishedIntent", "my morning walk", "I've finished my morning walk"),
    ("I completed my walk", "CompletedIntent", "my walk", "I completed my walk"),
]


@pytest.mark.parametrize("phrase,intent,slot,message", PHRASES)
def test_model_templates_cover_phrase_and_capture_the_activity(phrase, intent, slot, message):
    with open("skill-package/interactionModels/custom/en-GB.json", encoding="utf-8") as file:
        model = json.load(file)["interactionModel"]["languageModel"]
    matches = []
    for definition in model["intents"]:
        for sample in definition["samples"]:
            if "{query}" not in sample:
                continue
            pattern = re.escape(sample).replace(re.escape("{query}"), "(?P<query>.+)")
            match = re.fullmatch(pattern, phrase, re.IGNORECASE)
            if match:
                matches.append((definition["name"], match["query"]))
    assert matches == [(intent, slot)]
    definition = next(item for item in model["intents"] if item["name"] == intent)
    assert definition["slots"] == [{"name": "query", "type": "AMAZON.SearchQuery"}]


@pytest.mark.parametrize("phrase,intent,slot,message", PHRASES)
def test_handler_reconstructs_completion_without_losing_the_activity(alexa, phrase, intent, slot, message):
    text, reprompt, ends = alexa.speech(alexa.send(_intent(intent, query=slot)))
    assert alexa.turns == [(message, "amzn1.echo-api.session.s-1")]
    assert text == f"Reply to: {message}" and reprompt and not ends


@pytest.mark.parametrize("intent", ["CameBackFromIntent", "CompletedIntent", "FinishedIntent"])
def test_missing_activity_asks_without_running_the_agent(alexa, intent):
    text, reprompt, _ = alexa.speech(alexa.send(_intent(intent)))
    assert text == "Which recovery activity did you finish?" and reprompt
    assert alexa.turns == []


@pytest.fixture
def persisted(alexa, monkeypatch):
    state = {"timezone": "Europe/London", "medications": [], "tasks": [
        {"id": "walk", "description": "Walking: a short walk", "times_per_day": 2,
         "clock_times": ["07:30", "15:00"], "time_of_day": []},
        {"id": "dressing", "description": "Change dressing", "times_per_day": 1},
    ]}
    events = []
    calls = []
    context = PatientContext("test", PATIENT, "isolated")
    monkeypatch.setenv("DEMO_FIXED_NOW", DAY + "T08:00:00+01:00")
    def read(patient):
        assert patient == PATIENT
        return deepcopy(state)
    def history(patient):
        assert patient == PATIENT
        return deepcopy(events)
    def append(**event):
        assert event["patient_id"] == PATIENT
        duplicate = any(row["idempotency_key"] == event["idempotency_key"] for row in events)
        if not duplicate:
            events.append(deepcopy(event))
        return {"created": not duplicate, "duplicate": duplicate, "event": event}
    for module in (recovery_state, recovery, actions):
        monkeypatch.setattr(module, "get_recovery_state", read)
    monkeypatch.setattr(recovery_state, "get_events", history)
    monkeypatch.setattr(recovery_state, "append_event", append)
    async def call(name, arguments):
        calls.append((name, arguments))
        if name == "get_today_tasks":
            result = recovery.get_today_tasks_for_context(context)
        elif name == "get_medications":
            result = recovery.get_medications_for_context(context)
        elif name == "report_task_completed":
            result = actions.report_task_completed_for_context(context, **arguments)
        else:
            raise AssertionError(f"Unexpected MCP call: {name}")
        return SimpleNamespace(structured_content=result, is_error=False, content=[])
    def no_model(**kwargs):
        raise AssertionError("A model must not choose an ambiguous task")
    async def run(message, session_id):
        clear_session(session_id)
        return await service.chat(message, session_id, timezone="Europe/London")
    monkeypatch.setattr(service, "call_mcp_tool", call)
    monkeypatch.setattr(service.bedrock, "converse", no_model)
    monkeypatch.setattr(handlers, "run_turn", run)
    return SimpleNamespace(alexa=alexa, state=state, events=events, calls=calls)


@pytest.mark.parametrize("phrase,intent,slot,message", PHRASES)
def test_alexa_report_persists_only_the_correct_walk(persisted, phrase, intent, slot, message):
    run = persisted
    before = deepcopy(run.state)
    text, reprompt, _ = run.alexa.speech(run.alexa.send(_intent(intent, query=slot)))
    assert len(run.events) == 1, text
    assert run.events[0]["event_type"] == "task_completed"
    assert run.events[0]["details"]["occurrence_id"] == f"walk#{DAY}#1"
    tasks = recovery_state.get_today_tasks(PATIENT, DAY)
    assert [(task["task_id"], task["status"]) for task in tasks] == [
        ("walk", "completed"), ("walk", "pending"), ("dressing", "pending")]
    assert run.state == before and reprompt
    # Repeating the report in the morning must not mark the afternoon walk.
    run.alexa.send(_intent(intent, query=slot))
    assert len(run.events) == 1


@pytest.mark.parametrize("named_morning", [False, True])
def test_ambiguous_walk_occurrences_ask_and_never_persist(persisted, monkeypatch, named_morning):
    run = persisted
    if named_morning:
        run.state["tasks"][0]["clock_times"] = ["07:30", "09:00"]
    else:
        monkeypatch.setenv("DEMO_FIXED_NOW", DAY + "T16:00:00+01:00")
    query = "my morning walk" if named_morning else "my walk"
    text, reprompt, _ = run.alexa.speech(run.alexa.send(_intent("FinishedIntent", query=query)))
    assert text.startswith("Was that "), text
    assert reprompt and run.events == []
    assert not any(name.startswith("report_") for name, _ in run.calls)


def test_two_matching_walk_tasks_ask_and_never_persist(persisted):
    run = persisted
    run.state["tasks"].append({"id": "walk_other", "description": "Walking: another short walk",
                               "times_per_day": 1, "clock_times": ["08:00"]})
    text, reprompt, _ = run.alexa.speech(run.alexa.send(_intent("CompletedIntent", query="my walk")))
    assert text.startswith("Was that "), text
    assert reprompt and run.events == []
    assert not any(name.startswith("report_") for name, _ in run.calls)


def test_unmatched_activity_asks_and_never_persists(persisted):
    run = persisted
    text, reprompt, _ = run.alexa.speech(run.alexa.send(_intent("CompletedIntent", query="my swim")))
    assert text.startswith("Which scheduled recovery activity"), text
    assert reprompt and run.events == []
    assert not any(name.startswith("report_") for name, _ in run.calls)
