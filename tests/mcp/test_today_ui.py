"""The MCP Apps Today card: served as a ui:// resource and linked from get_today_tasks."""

import asyncio
import re

from app.mcp import server


URI = "ui://afterward/today.html"
MIME = "text/html;profile=mcp-app"


def test_today_card_is_listed_with_the_mcp_app_mime_type():
    resources = asyncio.run(server.mcp.list_resources())
    listed = {str(r.uri): r for r in resources}

    assert URI in listed
    assert listed[URI].mime_type == MIME


def test_today_card_reads_back_as_a_self_contained_page():
    contents = list(asyncio.run(server.mcp.read_resource(URI)))

    assert len(contents) == 1
    assert contents[0].mime_type == MIME
    html = contents[0].content
    assert "Waiting for today's plan" in html
    assert 'ui/initialize' in html
    assert 'ui/notifications/tool-result' in html
    # Sandboxed hosts block outside requests, so the page loads nothing from elsewhere.
    assert not re.search(r"(?:src|href)\s*=\s*[\"']https?://", html)
    assert "connect-src 'none'" in html
    assert "innerHTML" not in html


def test_today_and_week_tools_carry_the_ui_link():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}

    meta = tools["get_today_tasks"].model_dump(by_alias=True, exclude_none=True).get("_meta")
    assert meta == {"ui": {"resourceUri": URI}}

    others = [name for name, tool in tools.items()
              if name != "get_today_tasks" and (tool.meta or {}).get("ui")]
    assert others == ["get_week_summary"]


def test_get_today_tasks_still_returns_exactly_what_it_did(mcp_hop, monkeypatch):
    sentinel = {"ok": True, "data": {"date": "2026-10-23", "tasks": [{"occurrence_id": "task_walk#2026-10-23#1"}]}}
    monkeypatch.setattr(server, "get_today_tasks_for_context", lambda context: sentinel)

    result = asyncio.run(mcp_hop("get_today_tasks", {}))

    assert result.structured_content == sentinel
