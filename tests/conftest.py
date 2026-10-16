"""
Shared test setup.

The test suite runs on the demo clock (CLOCK_MODE=demo) so tests that set
DEMO_FIXED_NOW keep their fixed time. Real-clock tests set CLOCK_MODE=real
themselves and freeze app.clock.system_now_utc.
"""

import json
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def demo_clock_by_default(monkeypatch):
    monkeypatch.setenv("CLOCK_MODE", "demo")


@pytest.fixture(autouse=True)
def empty_caches():
    """No test sees a letter search, embedding or tool list cached by another."""

    from app.mcp import client
    from app.rag import service as rag_service

    rag_service.clear_search_caches()
    client._tool_list_cache.clear()
    yield
    rag_service.clear_search_caches()
    client._tool_list_cache.clear()


@pytest.fixture(autouse=True)
def empty_chat_limits():
    """Every test starts with no chat messages counted against the demo limits."""

    from app import web_bridge

    web_bridge.CHAT_SESSION_LIMIT.clear()
    web_bridge.CHAT_IP_LIMIT.clear()
    yield
    web_bridge.CHAT_SESSION_LIMIT.clear()
    web_bridge.CHAT_IP_LIMIT.clear()


def log_lines(text: str) -> list[dict]:
    """The structured log lines in captured stdout, oldest first."""

    lines = []

    for raw in text.splitlines():
        if raw.startswith("{"):
            try:
                lines.append(json.loads(raw))
            except ValueError:
                pass

    return lines


@pytest.fixture
def mcp_hop(monkeypatch):
    """
    The bridge-to-MCP hop without a network: the real client headers go through the
    real MCP authentication middleware to the real, logged tool functions.

    Patch app.mcp.server.<tool>_for_context to choose what a tool returns.
    """

    from app.auth import mcp_auth
    from app.mcp import client, server
    from app.mcp.http_auth import MCPAuthenticationMiddleware

    # No tool may reach DynamoDB or S3 from a test: every tool answers with an empty
    # result unless the test replaces it.
    for name in dir(server):
        if name.endswith("_for_context"):
            monkeypatch.setattr(server, name, lambda *args, **kwargs: {"ok": True, "data": {}})

    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token")
    monkeypatch.setattr(mcp_auth, "get_expected_mcp_token", lambda: "test-token")
    monkeypatch.setattr("app.mcp.http_auth.get_expected_mcp_token", lambda: "test-token")

    async def call_tool(name, arguments):
        seen = {}

        async def tool_app(scope, receive, send):
            seen["result"] = await getattr(server, name)(**arguments)

        headers = [(key.lower().encode(), value.encode()) for key, value in client._get_mcp_headers().items()]
        await MCPAuthenticationMiddleware(tool_app)({"type": "http", "path": "/mcp", "headers": headers}, None, None)

        return SimpleNamespace(structured_content=seen["result"], is_error=False, content=[])

    return call_tool
