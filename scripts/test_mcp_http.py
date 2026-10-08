"""
Exercise the AfterWard MCP tools over HTTP.

Both environment variables are required:

  MCP_URL          Full URL including /mcp path, e.g.
                   https://dakpc9juquqks.cloudfront.net/mcp
  MCP_TEST_TOKEN   Bearer token (from Secrets Manager or local dev)

Example:
  MCP_URL=https://dakpc9juquqks.cloudfront.net/mcp \\
  MCP_TEST_TOKEN=<token> \\
  python scripts/test_mcp_http.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Support direct execution from scripts/ without requiring package installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from mcp import Client
from mcp.client.streamable_http import streamable_http_client

# Loads .env, so MCP_URL and MCP_AUTH_TOKEN work without exporting.
from app import config
from app.clock import get_current_date


MCP_URL = os.environ["MCP_URL"]

# An explicit MCP_TEST_TOKEN wins; otherwise use the .env token.
MCP_TEST_TOKEN = (
    os.environ.get("MCP_TEST_TOKEN")
    or config.MCP_AUTH_TOKEN
)


def tool_data(result) -> dict:
    """
    Extract the dict our tools return.

    Tools return plain Python dicts, which the SDK serialises as JSON
    text in result.content[0].text.  structured_content is only
    populated for tools that declare structured_output=True.
    """
    if not result.content:
        return {"_raw": "(empty content list)", "_is_error": result.is_error}

    item = result.content[0]
    text = getattr(item, "text", None)

    if not text:
        # Unexpected content type (e.g. image) or empty text — show raw
        return {"_raw": repr(item), "_is_error": result.is_error}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text, "_is_error": result.is_error}


async def main():

    print(f"Connecting to: {MCP_URL}")

    http = httpx.AsyncClient(
        headers={
            "Authorization": f"Bearer {MCP_TEST_TOKEN}",
            "Origin": "http://localhost:3000",
        },
    )

    # The SDK hides HTTP status codes behind a generic MCPError, so check auth first.
    probe = await http.post(
        MCP_URL,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "preflight", "version": "1"},
            },
        },
    )
    if probe.status_code != 200:
        sys.exit(
            f"Server at {MCP_URL} returned HTTP {probe.status_code}: {probe.text[:200]}\n"
            "401 means MCP_TEST_TOKEN does not match this server "
            "(local uses afterward-local-dev-token; deployed uses the Secrets Manager token)."
        )

    # Pass the context manager itself to Client — it enters it internally.
    transport = streamable_http_client(
        MCP_URL,
        http_client=http,
    )

    async with Client(transport) as client:

        print("Connected to AfterWard MCP")

        # 1. List tools
        # list_tools() returns ListToolsResult; the actual list is .tools
        listing = await client.list_tools()

        print("\nTOOLS:")
        for tool in listing.tools:
            print("-", tool.name)

        # 2. Recovery plan
        plan = await client.call_tool(
            "get_recovery_plan",
            {},
        )

        print("\nRECOVERY PLAN:")
        print(json.dumps(tool_data(plan), indent=2))

        # 3. Today's tasks (before any write)
        tasks_result = await client.call_tool(
            "get_today_tasks",
            {},
        )

        tasks_data = tool_data(tasks_result)

        print("\nTODAY'S TASKS (before write):")
        print(json.dumps(tasks_data, indent=2))

        # The tool returns:
        # { "ok": true, "data": { "date": "...", "tasks": [...] } }
        tasks = tasks_data["data"]["tasks"]

        # The server's "today" (honours DEMO_FIXED_NOW if set there).
        today = tasks_data["data"].get("date") or get_current_date()

        pending_task = next(
            (
                task for task in tasks
                if task.get("status") != "completed"
            ),
            None,
        )

        if not pending_task:
            print(
                "\n(No pending tasks — skipping write tests)"
            )
        else:
            occurrence_id = pending_task["occurrence_id"]

            # 4. Mark one pending task occurrence complete
            print(
                f"\nMARKING TASK COMPLETE: {occurrence_id}"
            )

            write_1 = await client.call_tool(
                "report_task_completed",
                {"occurrence_id": occurrence_id},
            )

            print(
                "\nREPORT TASK COMPLETED (first call):"
            )
            print(json.dumps(tool_data(write_1), indent=2))

            # 5. Read tasks again — task should be completed
            tasks_after_1 = await client.call_tool(
                "get_today_tasks",
                {},
            )

            print(
                "\nTODAY'S TASKS (after first write):"
            )
            print(json.dumps(tool_data(tasks_after_1), indent=2))

            # 6. Repeat the exact same call — must be idempotent
            print(
                f"\nREPEATING SAME TASK COMPLETION: {occurrence_id}"
            )

            write_2 = await client.call_tool(
                "report_task_completed",
                {"occurrence_id": occurrence_id},
            )

            print(
                "\nREPORT TASK COMPLETED"
                " (second call — idempotent):"
            )
            print(json.dumps(tool_data(write_2), indent=2))

            # 7. Read tasks again — nothing extra should change
            tasks_after_2 = await client.call_tool(
                "get_today_tasks",
                {},
            )

            print(
                "\nTODAY'S TASKS (after repeated write):"
            )
            print(json.dumps(tool_data(tasks_after_2), indent=2))

        # 8. RAG search
        search_result = await client.call_tool(
            "search_discharge_instructions",
            {
                "query": (
                    "What did my paperwork "
                    "say about driving?"
                ),
            },
        )

        print("\nDRIVING SEARCH:")
        print(json.dumps(tool_data(search_result), indent=2))

        # 9. Medications
        meds_result = await client.call_tool(
            "get_medications",
            {},
        )

        print("\nMEDICATIONS:")
        print(json.dumps(tool_data(meds_result), indent=2))

        # 10. Invalid task ID — expect structured error, no 500
        print("\nINVALID TASK TEST:")

        invalid_result = await client.call_tool(
            "report_task_completed",
            {"occurrence_id": f"this_task_does_not_exist#{today}#1"},
        )

        print(json.dumps(tool_data(invalid_result), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
