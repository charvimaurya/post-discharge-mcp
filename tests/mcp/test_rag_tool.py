"""Test the MCP RAG wrapper locally and optionally against live AWS services."""

import pytest

from app.mcp.context import (
    get_demo_patient_context,
)

from app.mcp.tools.rag import (
    search_discharge_instructions_for_context,
)


@pytest.mark.integration
def test_driving_question_returns_evidence():

    context = get_demo_patient_context()

    result = (
        search_discharge_instructions_for_context(
            context,
            "What did my paperwork say about driving?",
        )
    )

    assert result["ok"] is True

    data = result["data"]

    assert data


def test_search_uses_context_patient(monkeypatch):
    from app.auth.patient_scope import PatientContext
    from app.mcp.tools import rag
    from unittest.mock import Mock

    search = Mock(return_value=[{"text": "Do not drive", "page": 1}])
    monkeypatch.setattr(rag, "search_discharge_instructions", search)
    result = search_discharge_instructions_for_context(
        PatientContext("user", "context_patient", "session"), " driving? "
    )
    search.assert_called_once_with(query="driving?", patient_id="context_patient")
    assert result["ok"] is True
    assert result["data"][0]["text"] == "Do not drive"


def test_empty_query_does_not_search(monkeypatch):
    from app.mcp.tools import rag
    from unittest.mock import Mock
    search = Mock()
    monkeypatch.setattr(rag, "search_discharge_instructions", search)
    result = search_discharge_instructions_for_context(get_demo_patient_context(), "  ")
    assert result["error"]["code"] == "EMPTY_SEARCH_QUERY"
    search.assert_not_called()


def test_no_matches(monkeypatch):
    from app.mcp.tools import rag
    monkeypatch.setattr(rag, "search_discharge_instructions", lambda **kwargs: [])
    result = search_discharge_instructions_for_context(get_demo_patient_context(), "driving?")
    assert result["error"]["code"] == "INSUFFICIENT_EVIDENCE"
