"""Test that extraction schemas and normalization preserve document, page, and snippet evidence."""

from dataclasses import asdict

import pytest

from app.ingestion.bedrock import EXTRACTION_SCHEMA
from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan


ITEMS = {
    "medications": {"name": "Amoxicillin", "strength": "500 mg", "times_per_day": 1},
    "tasks": {"description": "Walk"},
    "appointments": {"title": "GP"},
    "monitoring": {"what": "Temperature"},
    "restrictions": {"text": "Do not drive"},
    "warning_signs": {"text": "Chest pain", "action": "call [?999?]"},
}


@pytest.mark.parametrize("category", ITEMS)
def test_source_survives_normalization_validation_and_serialization(category):
    snippet = "Exact supporting text [?uncertain?]"
    item = {**ITEMS[category], "source": {
        "page": 2, "snippet": snippet, "document_id": "model-invented-id",
    }}
    state = normalize_recovery_plan({category: [item]}, "patient", "request-document")
    state = validate_recovery_plan(state)
    saved = asdict(state)[category][0]
    assert saved["source"] == {
        "document_id": "request-document", "page": 2,
        "snippet": snippet, "read_from_image": False,
    }
    assert item["source"]["document_id"] == "model-invented-id"


@pytest.mark.parametrize("category", ITEMS)
@pytest.mark.parametrize("source", [None, {"page": None, "snippet": None}])
def test_missing_evidence_is_not_invented(category, source):
    item = {**ITEMS[category], "source": source}
    state = normalize_recovery_plan({category: [item]}, "patient", "document")
    saved_source = asdict(state)[category][0]["source"]
    assert saved_source is None


def test_restrictions_and_warning_actions_are_preserved():
    state = normalize_recovery_plan({
        "restrictions": [{"text": " Do not drive ", "topic": "driving"}],
        "warning_signs": [{"text": "Chest pain", "action": "Call 999", "urgency": "emergency"}],
    }, "patient", "document")
    assert state.restrictions[0].text == "Do not drive"
    assert state.restrictions[0].topic == "driving"
    assert state.warning_signs[0].text == "Chest pain"
    assert state.warning_signs[0].action == "Call 999"
    assert state.warning_signs[0].urgency == "emergency"
    assert state.warning_signs[0].source is None


@pytest.mark.parametrize("category", ITEMS)
def test_schema_requires_source_on_every_item(category):
    schema = EXTRACTION_SCHEMA["properties"][category]["items"]
    assert "source" in schema["required"]
    source = schema["properties"]["source"]
    assert "snippet" in source["required"]
    assert source["properties"]["snippet"]["type"] == "string"
    # Canonical schema permits an unknown page; known pages are retained above.
    assert {"type": "integer"} in source["properties"]["page"]["anyOf"]
    assert {"type": "null"} in source["properties"]["page"]["anyOf"]
