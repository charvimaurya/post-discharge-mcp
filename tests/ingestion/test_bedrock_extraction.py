"""Test truncation failures and canonical tool-output validation without AWS calls."""

from copy import deepcopy
from unittest.mock import Mock

import pytest
from jsonschema.exceptions import ValidationError

from app.ingestion import bedrock


def response(extracted, stop_reason="tool_use"):
    return {
        "stopReason": stop_reason,
        "usage": {"outputTokens": 100},
        "output": {"message": {"content": [{"toolUse": {
            "name": "record_recovery_extraction", "input": extracted,
        }}]}},
    }


@pytest.fixture
def client(monkeypatch):
    mock = Mock()
    monkeypatch.setattr(bedrock, "_bedrock", lambda: mock)
    monkeypatch.setattr(bedrock.config, "get_extraction_model_id", lambda: "test-model")
    return mock


def empty_extraction():
    return {"discharge_date": None, **{key: [] for key in (
        "medications", "tasks", "appointments", "restrictions", "monitoring", "warning_signs"
    )}}


def test_truncation_never_returns_even_valid_tool_input(client, capsys):
    client.converse.return_value = response(empty_extraction(), "max_tokens")
    with pytest.raises(RuntimeError, match="extraction was truncated"):
        bedrock.invoke_extraction_model("Synthetic text")
    log = capsys.readouterr().out
    assert '"event":"extraction_model"' in log and '"reason":"max_tokens"' in log
    assert '"tokens_out":100' in log


def test_truncation_checked_before_accessing_output(client):
    client.converse.return_value = {"stopReason": "max_tokens"}
    with pytest.raises(RuntimeError, match="output token limit"):
        bedrock.invoke_extraction_model("Synthetic text")


def test_valid_tool_use_returns_original_unmodified_data(client):
    extracted = empty_extraction()
    extracted["medications"] = [{"name": "Amoxicillin", "strength": "500 mg", "dose": None,
                                "source": {"snippet": "Amoxicillin 500 mg", "page": 1}}]
    before = deepcopy(extracted)
    client.converse.return_value = response(extracted)
    assert bedrock.invoke_extraction_model("Amoxicillin 500 mg") is extracted
    assert extracted == before
    request = client.converse.call_args.kwargs
    assert request["inferenceConfig"] == {"temperature": 0, "maxTokens": 5000}
    assert request["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"] == bedrock.load_extraction_schema()


def test_medication_clock_times_rejected_not_removed(client):
    extracted = empty_extraction()
    extracted["medications"] = [{"name": "Example", "clock_times": ["08:00"],
                                "source": {"snippet": "Example"}}]
    before = deepcopy(extracted)
    client.converse.return_value = response(extracted)
    with pytest.raises(ValueError, match="does not match the discharge schema") as caught:
        bedrock.invoke_extraction_model("Synthetic text")
    # The field and the rule are named; the extracted values are not (logs must not hold letter text),
    # and the original error, which quotes the values, is not chained on.
    assert "clock_times" in str(caught.value)
    assert "08:00" not in str(caught.value) and "Example" not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert extracted == before


def test_task_clock_times_allowed(client):
    extracted = empty_extraction()
    extracted["tasks"] = [{"description": "Walk at 08:00", "kind": "walk", "clock_times": ["08:00"],
                          "source": {"snippet": "Walk at 08:00", "page": 1}}]
    client.converse.return_value = response(extracted)
    assert bedrock.invoke_extraction_model("Walk at 08:00") == extracted


def test_missing_warning_action_rejected(client):
    extracted = empty_extraction()
    extracted["warning_signs"] = [{"text": "Chest pain", "source": {"snippet": "Chest pain"}}]
    client.converse.return_value = response(extracted)
    with pytest.raises(ValueError, match="action"):
        bedrock.invoke_extraction_model("Synthetic text")


def test_no_tool_output_is_failure(client):
    client.converse.return_value = {"stopReason": "end_turn", "output": {"message": {"content": [{"text": "No extraction"}]}}}
    with pytest.raises(RuntimeError, match="did not return structured tool output"):
        bedrock.invoke_extraction_model("Synthetic text")


def test_canonical_clock_times_fields():
    schema = bedrock.load_extraction_schema()
    medication = schema["properties"]["medications"]["items"]
    assert "clock_times" not in medication["properties"]
    assert medication["additionalProperties"] is False
    assert "clock_times" in schema["properties"]["tasks"]["items"]["properties"]
