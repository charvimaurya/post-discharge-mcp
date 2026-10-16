"""Check prompt discovery and rendering over the MCP protocol without AWS calls."""

import asyncio
from contextlib import asynccontextmanager

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from app.mcp.server import mcp


@asynccontextmanager
async def prompt_client():
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as group:
            server = mcp._lowlevel_server
            group.start_soon(
                server.run, *server_streams, server.create_initialization_options()
            )
            async with ClientSession(*client_streams) as client:
                await client.initialize()
                yield client
            group.cancel_scope.cancel()


def test_prompts_list_exposes_both_prompts_and_arguments():
    async def check():
        async with prompt_client() as client:
            result = await client.list_prompts()
            prompts = {prompt.name: prompt for prompt in result.prompts}
            assert {"ask_my_letter", "morning_checkin"} <= prompts.keys()
            arguments = prompts["ask_my_letter"].arguments
            assert arguments is not None
            assert [(arg.name, arg.required) for arg in arguments] == [("question", True)]
            assert not prompts["morning_checkin"].arguments

    asyncio.run(check())


def test_ask_my_letter_requires_search_evidence_and_no_guessing():
    async def check():
        async with prompt_client() as client:
            result = await client.get_prompt(
                "ask_my_letter", arguments={"question": "What does my letter say about food?"}
            )
            text = "\n".join(message.content.text for message in result.messages)
            assert "Call search_discharge_instructions first" in text
            assert "only from the returned passages" in text
            assert "page number" in text
            assert "If nothing is found" in text
            assert "I will not guess" in text
            assert "What does my letter say about food?" in text

    asyncio.run(check())


def test_morning_checkin_reads_tasks_and_medications_before_spoken_step():
    async def check():
        async with prompt_client() as client:
            result = await client.get_prompt("morning_checkin")
            text = "\n".join(message.content.text for message in result.messages)
            assert "Call get_today_tasks and get_medications first" in text
            assert "one short spoken step" in text
            assert "what is done and what is next" in text
            assert "Do not assume an item is done" in text

    asyncio.run(check())
