"""Safety checks for the explicitly test-only host launcher."""
import asyncio

from botocore.client import BaseClient
import pytest

from tests.mcp.isolated_host import PATIENT, build_app
from app.mcp import http_auth, server


def test_host_forces_isolated_identity_and_blocks_aws(monkeypatch):
    _, store = build_app(monkeypatch, "local-test-token")
    assert http_auth.get_expected_mcp_token() == "local-test-token"
    context = http_auth.PatientContext(user_id="unused", patient_id="demo_patient_001", session_id="unused")
    assert context.patient_id == PATIENT
    with pytest.raises(AssertionError):
        store.get_item(Key={"patient_id": "demo_patient_001"})
    with pytest.raises(RuntimeError, match="AWS is prohibited"):
        BaseClient._make_api_call(None, "PutItem", {})
    with pytest.raises(RuntimeError, match="disabled"):
        server.report_medication_taken_for_context(context, "unused")
    assert len(asyncio.run(server.mcp.list_tools())) == 9
    assert len(asyncio.run(server.mcp.list_prompts())) == 2


@pytest.mark.parametrize("with_week,completed", [(False, 0), (True, 5)])
def test_week_query_is_read_only_with_and_without_mock_seed(monkeypatch, with_week, completed):
    from copy import deepcopy
    from app.auth.patient_scope import PatientContext
    from app.mcp.context import set_current_patient_context, reset_current_patient_context
    _, store = build_app(monkeypatch, "local-test-token", with_week=with_week)
    before = deepcopy((store.plan, store.events))
    token = set_current_patient_context(PatientContext("test", PATIENT, "isolated"))
    try:
        first = asyncio.run(server.get_week_summary())
        second = asyncio.run(server.get_week_summary())
    finally:
        reset_current_patient_context(token)
    assert first == second
    assert first["ok"] is True
    assert first["data"]["week"]["completed_days"] == completed
    assert len(first["data"]["today"]["tasks"]) == 3
    assert (store.plan, store.events) == before
