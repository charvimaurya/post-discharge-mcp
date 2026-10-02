from dataclasses import asdict

import pytest

from app.ingestion.bedrock import EXTRACTION_SCHEMA
from app.ingestion.normalizer import normalize_recovery_plan
from app.ingestion.validator import validate_recovery_plan


ITEMS = {
    "medications": {"name": "Amoxicillin", "dose": "500 mg", "frequency": "daily"},
    "tasks": {"description": "Walk"},
    "appointments": {"with": "GP", "status": "booked"},
    "monitoring": {"what": "Temperature"},
    "restrictions": {"text": "Do not drive"},
    "warning_signs": {"text": "Chest pain: call [?999?]"},
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
        "snippet": snippet, "source_type": "document",
    }
    assert item["source"]["document_id"] == "model-invented-id"


@pytest.mark.parametrize("category", ITEMS)
@pytest.mark.parametrize("source", [None, {"page": None, "snippet": None}])
def test_missing_evidence_is_not_invented(category, source):
    item = {**ITEMS[category], "source": source}
    state = normalize_recovery_plan({category: [item]}, "patient", "document")
    saved_source = asdict(state)[category][0]["source"]
    assert saved_source["document_id"] == "document"
    assert saved_source["page"] is None
    assert saved_source["snippet"] is None


def test_older_text_and_warning_dicts_are_preserved():
    state = normalize_recovery_plan({
        "restrictions": [" Do not drive ", ""],
        "warning_signs": ["Call 999", {"sign": "Chest pain", "action": "Call 999"}],
    }, "patient", "document")
    assert len(state.restrictions) == 1
    assert state.restrictions[0]["text"] == "Do not drive"
    assert state.warning_signs[0]["text"] == "Call 999"
    assert state.warning_signs[1]["sign"] == "Chest pain"
    assert state.warning_signs[1]["action"] == "Call 999"
    assert state.warning_signs[0]["source"]["snippet"] is None


@pytest.mark.parametrize("category", ITEMS)
def test_schema_requires_source_on_every_item(category):
    schema = EXTRACTION_SCHEMA["properties"][category]["items"]
    assert "source" in schema["required"]
    assert schema["properties"]["source"]["required"] == ["page", "snippet"]
