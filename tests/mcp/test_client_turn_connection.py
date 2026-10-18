"""One MCP connection per chat turn, and the tools/list cache. No network: the session is faked."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.agent import service
from app.mcp import client


class FakeConnections:
    """Counts the connections opened and closed, and answers tool calls."""

    def __init__(self, fail_on: str | None = None):
        self.opened = 0
        self.closed = 0
        self.calls: list[tuple[int, str]] = []
        self.fail_on = fail_on
        self.lists = 0

    @asynccontextmanager
    async def open(self):
        self.opened += 1
        number = self.opened
        connections = self

        class Session:
            async def call_tool(self, name, arguments):
                connections.calls.append((number, name))
                await asyncio.sleep(0)
                if name == connections.fail_on:
                    raise ConnectionError("dropped")
                return SimpleNamespace(name=name, connection=number)

            async def list_tools(self):
                connections.lists += 1
                return SimpleNamespace(tools=["t"])

        try:
            yield Session()
        finally:
            self.closed += 1


@pytest.fixture
def connections(monkeypatch):
    fake = FakeConnections()
    monkeypatch.setattr(client, "_open_session", fake.open)
    monkeypatch.setenv("MCP_URL", "http://mcp.test/mcp")
    client._tool_list_cache.clear()
    yield fake
    client._tool_list_cache.clear()


def run(coroutine):
    return asyncio.run(coroutine)


def test_without_a_turn_each_call_opens_its_own_connection(connections):
    async def calls():
        await client.call_mcp_tool("get_today_tasks", {})
        await client.call_mcp_tool("get_medications", {})

    run(calls())

    assert (connections.opened, connections.closed) == (2, 2)


def test_inside_a_turn_every_call_shares_one_connection_closed_at_the_end(connections):
    async def turn():
        async with client.mcp_turn():
            await asyncio.gather(
                client.call_mcp_tool("get_today_tasks", {}),
                client.call_mcp_tool("get_medications", {}),
            )
            await client.call_mcp_tool("search_discharge_instructions", {"query": "driving"})
            assert connections.closed == 0

    run(turn())

    assert (connections.opened, connections.closed) == (1, 1)
    assert {number for number, _ in connections.calls} == {1}


def test_a_turn_that_calls_no_tool_opens_nothing(connections):
    async def turn():
        async with client.mcp_turn():
            pass

    run(turn())

    assert connections.opened == 0


def test_failed_connection_open_propagates_nested_transport_error_without_writes(monkeypatch):
    import httpx

    @asynccontextmanager
    async def unavailable():
        raise ExceptionGroup("transport", [httpx.ConnectError("unavailable")])
        yield  # pragma: no cover

    monkeypatch.setattr(client, "_open_session", unavailable)

    async def call():
        async with client.mcp_turn():
            await client.call_mcp_tool("get_today_tasks", {})

    with pytest.raises(ExceptionGroup) as caught:
        run(call())
    assert isinstance(caught.value.exceptions[0], httpx.ConnectError)


def test_a_failed_call_is_raised_and_the_next_call_gets_a_fresh_connection(connections):
    connections.fail_on = "report_task_completed"

    async def turn():
        async with client.mcp_turn():
            await client.call_mcp_tool("get_today_tasks", {})
            with pytest.raises(ConnectionError):
                await client.call_mcp_tool("report_task_completed", {"occurrence_id": "x"})
            await client.call_mcp_tool("get_medications", {})

    run(turn())

    # The failed write ran once only, and the call after it used a new connection.
    assert [name for _, name in connections.calls].count("report_task_completed") == 1
    assert connections.calls[-1] == (2, "get_medications")
    assert connections.opened == connections.closed == 2


def test_nested_turns_reuse_the_outer_connection(connections):
    async def turn():
        async with client.mcp_turn():
            await client.call_mcp_tool("get_today_tasks", {})
            async with client.mcp_turn():
                await client.call_mcp_tool("get_medications", {})
            assert connections.closed == 0

    run(turn())

    assert (connections.opened, connections.closed) == (1, 1)


def test_tool_list_is_fetched_once_then_reused_until_it_expires(connections, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(client.time, "monotonic", lambda: clock[0])

    first = run(client.get_mcp_tools())
    second = run(client.get_mcp_tools())
    assert first is second
    assert connections.lists == 1

    clock[0] += client.TOOL_LIST_SECONDS + 1
    run(client.get_mcp_tools())
    assert connections.lists == 2


def test_tool_list_is_kept_per_mcp_server(connections, monkeypatch):
    run(client.get_mcp_tools())
    monkeypatch.setenv("MCP_URL", "http://other.test/mcp")
    run(client.get_mcp_tools())

    assert connections.lists == 2


def test_todays_two_reads_run_at_the_same_time_and_are_traced_in_order(monkeypatch):
    started: list[str] = []
    both_started = asyncio.Event()

    async def call_tool(name, arguments):
        started.append(name)
        if len(started) == 2:
            both_started.set()
        # Neither read finishes until both have started: this only passes if they overlap.
        await asyncio.wait_for(both_started.wait(), timeout=2)
        field = "tasks" if name == "get_today_tasks" else "medications"
        return SimpleNamespace(structured_content={"ok": True, "data": {field: []}}, is_error=False, content=[])

    monkeypatch.setattr(service, "call_mcp_tool", call_tool)
    trace: list[dict] = []

    today = asyncio.run(service._load_today(trace))

    assert today == {"tasks": [], "medications": []}
    assert [step["tool"] for step in trace] == ["get_today_tasks", "get_medications"]
