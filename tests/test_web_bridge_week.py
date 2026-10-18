"""Weekly web bridge forwarding uses fake MCP results, never AWS patient data."""
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient as UnauthenticatedClient
from tests.bridge_client import BridgeClient
from app import web_bridge


def test_week_summary_calls_read_only_mcp_tool_without_caller_patient(monkeypatch):
    calls = []
    async def fake(name, arguments):
        calls.append((name, arguments))
        return SimpleNamespace(structured_content={"ok": True, "data": {
            "week": {"days": [], "completed_days": 0}, "timezone": "Europe/London",
            "as_of": "2026-10-23T07:00:00+01:00", "today": {"patient_id": "not-for-this-response"},
        }})
    monkeypatch.setattr(web_bridge, "call_mcp_tool", fake)
    response = BridgeClient(web_bridge.app).get('/week-summary?date=1900-01-01')
    assert response.status_code == 200
    assert calls == [('get_week_summary', {})]
    assert set(response.json()) == {'week', 'timezone', 'as_of'}
    assert response.headers['cache-control'] == 'no-store'
    assert 'not-for-this-response' not in response.text


@pytest.mark.parametrize('result', [None, {'ok': False}, {'ok': True, 'data': {}},
                                    {'ok': True, 'data': {'week': []}}])
def test_week_summary_failure_is_generic(monkeypatch, result):
    async def fake(*args):
        return SimpleNamespace(structured_content=result)
    monkeypatch.setattr(web_bridge, 'call_mcp_tool', fake)
    response = BridgeClient(web_bridge.app).get('/week-summary')
    assert response.status_code == 502
    assert response.json() == {'error': 'The weekly summary could not be checked.'}


def test_week_summary_exception_does_not_reveal_backend_details(monkeypatch):
    async def fake(*args):
        raise RuntimeError('private-backend-detail')
    monkeypatch.setattr(web_bridge, 'call_mcp_tool', fake)
    response = BridgeClient(web_bridge.app).get('/week-summary')
    assert response.status_code == 502
    assert 'private-backend-detail' not in response.text


def test_week_summary_requires_bridge_authentication(monkeypatch):
    async def must_not_call(*args):
        pytest.fail('Unauthenticated request reached MCP')
    monkeypatch.setattr(web_bridge, 'call_mcp_tool', must_not_call)
    assert UnauthenticatedClient(web_bridge.app).get('/week-summary').status_code == 401
