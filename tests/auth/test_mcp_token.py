"""Test MCP bearer token resolution for local and deployed configuration."""

import pytest

from app.auth import mcp_token


@pytest.fixture(autouse=True)
def clear_token_cache():
    mcp_token.get_mcp_auth_token.cache_clear()
    yield
    mcp_token.get_mcp_auth_token.cache_clear()


def test_local_token(monkeypatch):
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN", "local-token")
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN_SECRET_ARN", "arn:secret")
    monkeypatch.setattr(mcp_token.boto3, "client", lambda *a, **k: pytest.fail("should not call AWS"))
    assert mcp_token.get_mcp_auth_token() == "local-token"


def test_secret_arn_token(monkeypatch):
    calls = []

    class FakeSecrets:
        def get_secret_value(self, SecretId):
            calls.append(SecretId)
            return {"SecretString": "deployed-token\n"}

    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN", "")
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN_SECRET_ARN", "arn:secret")
    monkeypatch.setattr(mcp_token.boto3, "client", lambda service, region_name: FakeSecrets())
    assert mcp_token.get_mcp_auth_token() == "deployed-token"
    assert mcp_token.get_mcp_auth_token() == "deployed-token"
    assert calls == ["arn:secret"]


def test_empty_secret(monkeypatch):
    class FakeSecrets:
        def get_secret_value(self, SecretId):
            return {"SecretString": "  "}

    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN", "")
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN_SECRET_ARN", "arn:secret")
    monkeypatch.setattr(mcp_token.boto3, "client", lambda service, region_name: FakeSecrets())
    with pytest.raises(ValueError):
        mcp_token.get_mcp_auth_token()


def test_no_token_configured(monkeypatch):
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN", "")
    monkeypatch.setattr(mcp_token.config, "MCP_AUTH_TOKEN_SECRET_ARN", "")
    with pytest.raises(ValueError):
        mcp_token.get_mcp_auth_token()
