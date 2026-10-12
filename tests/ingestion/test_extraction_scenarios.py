"""Check canonical extraction examples through mocked Converse and the real local pipeline.

These fixtures test preservation and request wiring, not the model's ability to
interpret source text. No Bedrock, DynamoDB, or Lambda calls are made.
"""

from copy import deepcopy
from unittest.mock import patch

import pytest

from app.ingestion import bedrock, pipeline


SCENARIOS = [
    ("medications", "Amoxicillin 500 mg", {"name": "Amoxicillin", "strength": "500 mg", "dose": None}),
    ("medications", "Paracetamol up to four times daily as needed", {"name": "Paracetamol", "as_needed": True, "max_per_day": 4}),
    ("tasks", "Walk every morning", {"description": "Walk every morning", "kind": "walk", "time_of_day": ["morning"], "clock_times": []}),
    ("appointments", "Review on 10 October 2026; review also listed as 12 October 2026.", {"title": "Review", "date": "2026-10-10", "conflicting_dates": ["2026-10-12"]}),
    ("appointments", "GP review within 7 days, by 25 Sep 2026; patient to arrange.", {"title": "GP review", "date": None, "conflicting_dates": []}),
    ("warning_signs", "Call 999 immediately if you experience severe breathlessness.", {"text": "severe breathlessness", "action": "Call 999 immediately", "urgency": "emergency"}),
]


@pytest.mark.parametrize("category,snippet,fields", SCENARIOS)
def test_canonical_examples_through_local_pipeline(category, snippet, fields):
    extracted = {name: [] for name in ("medications", "tasks", "appointments", "restrictions", "monitoring", "warning_signs")}
    extracted["discharge_date"] = None
    item = {**deepcopy(fields), "source": {"snippet": snippet, "page": 1, "document_id": "untrusted-model-id"}}
    extracted[category] = [item]
    with patch.object(bedrock, "_bedrock") as factory, patch.object(bedrock.config, "get_extraction_model_id", return_value="offline-test-model"):
        client = factory.return_value
        client.converse.return_value = {
            "output": {"message": {"content": [{"toolUse": {"name": "record_recovery_extraction", "input": extracted}}]}},
            "stopReason": "tool_use", "usage": {"outputTokens": 100},
        }
        state = pipeline.process_text(f"[Page 1]\nHospital discharge letter\nRecovery instructions\n{snippet}", "patient", "request-document")
        client.converse.assert_called_once()
        request = client.converse.call_args.kwargs
        assert request["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"] == bedrock.load_extraction_schema()
        assert request["toolConfig"]["toolChoice"]["tool"]["name"] == "record_recovery_extraction"
        assert request["inferenceConfig"] == {"temperature": 0, "maxTokens": 5000}
        assert snippet in request["messages"][0]["content"][0]["text"]
    result = getattr(state, category)[0]
    for field, value in fields.items():
        assert getattr(result, field) == value
    assert result.source.snippet == snippet
    assert result.source.page == 1
    assert result.source.document_id == "request-document"
    assert result.id
    assert state.ingestion_status == "ready"
    if category == "medications":
        assert result.dose is None
        assert result.times_per_day is None
        assert result.needs_confirmation is False
    if category == "tasks":
        assert result.clock_times == []
    if category == "appointments":
        assert len(state.appointments) == 1
        assert result.needs_confirmation is bool(fields["conflicting_dates"])
    assert extracted[category][0] == item
