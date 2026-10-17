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

import asyncio
import os
import time
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from typing import Any, AsyncGenerator

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from app.observability.log import get_request_id
from app.auth.mcp_token import get_mcp_auth_token

# How long the tools/list answer is reused. The tool list only changes when the MCP
# server is redeployed, so this just bounds how long a new tool takes to appear.
TOOL_LIST_SECONDS = 600


def _get_mcp_headers() -> dict[str, str]:
    """
    Build the HTTP headers required by our secured MCP server.

    Resolve the token server-side: local configuration or Secrets Manager.
    """

    token = get_mcp_auth_token()

    origin = os.environ.get(
        "MCP_CLIENT_ORIGIN",
        "http://localhost:3000",
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": origin,
    }

    # The same id the bridge logged, so a tool's log line can be matched to the chat turn.
    request_id = get_request_id()
    if request_id:
        headers["X-Request-ID"] = request_id

    return headers


@asynccontextmanager
async def _open_session() -> AsyncGenerator[ClientSession, None]:
    """One initialised MCP session over a new HTTP connection."""

    async with create_mcp_http_client(
        headers=_get_mcp_headers(),
    ) as http_client, streamable_http_client(
        os.environ["MCP_URL"],
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

            yield session


class _TurnConnection:
    """
    One MCP session shared by every tool call in a chat turn.

    Opened by the first call, not before, so a turn that needs no tool opens
    nothing. The session's connection is held open by a task of its own,
    because it must be opened and closed in the same task while the turn's
    calls (some of them run side by side) come from other tasks. That task
    copies the turn's context, so the X-Request-ID header is the turn's.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._session: ClientSession | None = None
        self._holder: asyncio.Task | None = None
        self._release: asyncio.Event | None = None

    async def session(self) -> ClientSession:
        async with self._lock:
            if self._session is None:
                opened: asyncio.Future = asyncio.get_running_loop().create_future()
                self._release = asyncio.Event()
                self._holder = asyncio.create_task(self._hold(opened, self._release))
                self._session = await opened

            return self._session

    async def _hold(self, opened: asyncio.Future, release: asyncio.Event) -> None:
        try:
            async with _open_session() as session:
                opened.set_result(session)
                await release.wait()
        except BaseException as exc:
            # Opening failed: the waiting call raises it. Failing later: the next
            # call on this session fails too and resets it, so nothing is lost here.
            if not opened.done():
                opened.set_exception(exc)
            if isinstance(exc, asyncio.CancelledError):
                raise

    async def reset(self) -> None:
        """Close the session; the next call opens a fresh one (after a failed call)."""

        async with self._lock:
            await self._close_locked()

    async def close(self) -> None:
        async with self._lock:
            await self._close_locked()

    async def _close_locked(self) -> None:
        holder, release = self._holder, self._release
        self._session = self._holder = self._release = None

        if release is not None:
            release.set()

        if holder is not None:
            with suppress(Exception, asyncio.CancelledError):
                await holder


_turn_connection: ContextVar[_TurnConnection | None] = ContextVar("mcp_turn_connection", default=None)


@asynccontextmanager
async def mcp_turn() -> AsyncGenerator[None, None]:
    """
    Share one MCP connection across the tool calls made inside this block.

    A new connection costs a handshake plus the initialize round trips, on
    every call. Within one chat turn (or one /today read) the calls share
    one instead. The connection lives only as long as the block, so it never
    goes stale and always carries this request's id. Nested blocks reuse the
    outer connection.
    """

    if _turn_connection.get() is not None:
        yield
        return

    connection = _TurnConnection()
    token = _turn_connection.set(connection)

    try:
        yield
    finally:
        _turn_connection.reset(token)
        await connection.close()


async def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
):
    """
    Invoke one tool on the AfterWard MCP server.

    Inside mcp_turn() the call uses the turn's shared session; outside one,
    it opens and closes a session of its own, as before. A failed call drops
    the shared session so the next call starts on a fresh connection; the
    failure itself is raised, never retried here (a write must not run twice).
    """

    connection = _turn_connection.get()

    if connection is None:
        async with _open_session() as session:
            return await session.call_tool(tool_name, arguments)

    session = await connection.session()

    try:
        return await session.call_tool(tool_name, arguments)
    except Exception:
        await connection.reset()
        raise


# tools/list, kept per MCP URL: {url: (monotonic time fetched, result)}.
_tool_list_cache: dict[str, tuple[float, Any]] = {}


async def get_mcp_tools():
    """
    Return the MCP tools advertised by tools/list.

    This lets the agent use the MCP server itself as the
    source of truth for tool names, descriptions and schemas.
    The answer is reused for TOOL_LIST_SECONDS: it is the same on
    every turn until the MCP server is redeployed.
    """

    mcp_url = os.environ["MCP_URL"]
    cached = _tool_list_cache.get(mcp_url)

    if cached is not None and time.monotonic() - cached[0] < TOOL_LIST_SECONDS:
        return cached[1]

    connection = _turn_connection.get()

    if connection is None:
        async with _open_session() as session:
            result = await session.list_tools()
    else:
        result = await (await connection.session()).list_tools()

    _tool_list_cache[mcp_url] = (time.monotonic(), result)

    return result
