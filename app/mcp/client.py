"""
Server-side MCP client used by the Phase 13 agent.

The browser NEVER receives the MCP bearer token.

Flow:

    browser
        ↓
    POST /api/chat
        ↓
    Python backend
        ↓
    this MCP client
        ↓
    deployed AfterWard MCP server
"""

import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client


def _get_mcp_headers() -> dict[str, str]:
    """
    Build the HTTP headers required by our secured MCP server.

    MCP_AUTH_TOKEN is only available server-side.
    """

    token = os.environ["MCP_AUTH_TOKEN"]

    origin = os.environ.get(
        "MCP_CLIENT_ORIGIN",
        "http://localhost:3000",
    )

    return {
        "Authorization": f"Bearer {token}",
        "Origin": origin,
    }


async def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
):
    """
    Connect to the deployed MCP server and invoke one tool.

    A new MCP session is created for now because this keeps
    the implementation simple and reliable for the hackathon.

    Later, connection pooling could reduce latency.
    """

    mcp_url = os.environ["MCP_URL"]

    async with create_mcp_http_client(
        headers=_get_mcp_headers(),
    ) as http_client, streamable_http_client(
        mcp_url,
        http_client=http_client,
    ) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            # MCP clients must initialize before calling tools.
            await session.initialize()

            return await session.call_tool(
                tool_name,
                arguments,
            )


async def get_mcp_tools():
    """
    Return the MCP tools advertised by tools/list.

    This lets the agent use the MCP server itself as the
    source of truth for tool names, descriptions and schemas.
    """

    mcp_url = os.environ["MCP_URL"]

    async with create_mcp_http_client(
        headers=_get_mcp_headers(),
    ) as http_client, streamable_http_client(
        mcp_url,
        http_client=http_client,
    ) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            return await session.list_tools()