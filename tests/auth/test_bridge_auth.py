"""Auth boundary tests use the raw client, without the behavior-test helper."""
import asyncio

import pytest
from starlette.testclient import TestClient

from app import web_bridge
from app.auth import bridge_auth, mcp_token
from tests.bridge_client import BRIDGE_TEST_KEY


@pytest.mark.parametrize("path,method", [
    ("/today", "get"), ("/chat", "post"),
    ("/documents/validate", "post"), ("/documents/uploaded", "post"),
    ("/reminders/check", "post"), ("/unknown", "get"),
])
def test_every_nonhealth_route_requires_key(path, method, monkeypatch):
    monkeypatch.setattr(web_bridge, "delete_events", lambda *a: pytest.fail("unauthorized side effect"))
    monkeypatch.setattr(web_bridge, "record_chat_activity", lambda *a: pytest.fail("unauthorized side effect"))
    client = TestClient(web_bridge.app)
    assert getattr(client, method)(path).status_code == 401
    assert getattr(client, method)(path, headers={"X-Bridge-Key": "wrong"}).status_code == 401


def test_valid_key_allows_request_and_is_never_returned_or_logged(monkeypatch, capsys):
    monkeypatch.setattr(web_bridge, "delete_events", lambda patient: 3)
    response = TestClient(web_bridge.app).post("/documents/uploaded", headers={"X-Bridge-Key": BRIDGE_TEST_KEY})
    assert response.status_code == 200 and response.json() == {"deleted": 3}
    assert BRIDGE_TEST_KEY not in response.text + capsys.readouterr().out


@pytest.mark.parametrize("key", [None, "", "   ", "short"])
def test_production_fails_closed_but_health_is_public(monkeypatch, key):
    monkeypatch.setenv("CLOCK_MODE", "production")
    if key is None:
        monkeypatch.delenv("BRIDGE_KEY", raising=False)
    else:
        monkeypatch.setenv("BRIDGE_KEY", key)
    client = TestClient(web_bridge.app)
    assert client.get("/today", headers={"X-Bridge-Key": BRIDGE_TEST_KEY}).status_code == 503
    assert client.get("/bridge/health").json() == {"status": "ok"}
    assert client.head("/bridge/health").status_code == 200
    assert client.get("/bridge/health/extra").status_code == 503


def test_local_missing_key_also_fails_closed(monkeypatch):
    monkeypatch.delenv("BRIDGE_KEY", raising=False)
    assert TestClient(web_bridge.app).get("/today").status_code == 503


def test_uses_constant_time_comparison_and_rejects_duplicate_headers(monkeypatch):
    calls = []
    original = bridge_auth.hmac.compare_digest
    def compare(a, b):
        calls.append(True)
        return original(a, b)
    monkeypatch.setattr(bridge_auth.hmac, "compare_digest", compare)
    client = TestClient(web_bridge.app)
    assert client.get("/today", headers={"X-Bridge-Key": "wrong"}).status_code == 401
    assert calls == [True]
    response = client.get("/today", headers=[("X-Bridge-Key", BRIDGE_TEST_KEY), ("X-Bridge-Key", BRIDGE_TEST_KEY)])
    assert response.status_code == 401


@pytest.mark.parametrize("cloud", [False, True])
def test_cloud_or_production_never_starts_local_reminder_loop(monkeypatch, cloud):
    monkeypatch.setenv("LOCAL_REMINDER_LOOP", "1")
    monkeypatch.setenv("CLOCK_MODE", "real" if cloud else "production")
    if cloud:
        monkeypatch.setenv("ECS_CONTAINER_METADATA_URI_V4", "http://metadata.invalid")
    async def run():
        async with web_bridge.lifespan(web_bridge.app):
            assert web_bridge.app.state.reminder_task is None
    asyncio.run(run())


def test_production_mcp_requires_secret_even_when_plain_token_exists(monkeypatch):
    monkeypatch.setenv("CLOCK_MODE", "production")
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN", "local-example")
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN_SECRET_ARN", "")
    mcp_token.get_mcp_auth_token.cache_clear()
    try:
        with pytest.raises(ValueError, match="require MCP_AUTH_TOKEN_SECRET_ARN"):
            mcp_token.get_mcp_auth_token()
    finally:
        mcp_token.get_mcp_auth_token.cache_clear()


def test_production_mcp_uses_secret_not_local_token(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setenv("CLOCK_MODE", "production")
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN", "local-example")
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN_SECRET_ARN", "arn:secret")
    monkeypatch.setattr(mcp_token.boto3, "client", lambda *a, **k: SimpleNamespace(get_secret_value=lambda **kw: {"SecretString": "cloud-test-value"}))
    mcp_token.get_mcp_auth_token.cache_clear()
    try:
        from app.mcp.client import _get_mcp_headers
        assert _get_mcp_headers()["Authorization"] == "Bearer cloud-test-value"
    finally:
        mcp_token.get_mcp_auth_token.cache_clear()
