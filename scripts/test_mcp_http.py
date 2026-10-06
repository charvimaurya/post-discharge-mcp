"""
Exercise the AfterWard MCP tools over HTTP.

Target is controlled by environment variables so the same script
works against both local uvicorn and the deployed ALB:

  Local:
    MCP_URL defaults to http://127.0.0.1:8000/mcp
    MCP_TEST_TOKEN defaults to afterward-local-dev-token

  Deployed:
    export MCP_URL=http://afterward-mcp-alb-426611083.eu-west-2.elb.amazonaws.com/mcp
    export MCP_TEST_TOKEN=<token from Secrets Manager>
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


MCP_URL = os.environ["MCP_URL"]
MCP_TEST_TOKEN = os.environ["MCP_TEST_TOKEN"]


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
            task_id = pending_task["id"]

            # 4. Mark one pending task complete
            print(
                f"\nMARKING TASK COMPLETE: {task_id}"
            )

            write_1 = await client.call_tool(
                "report_task_completed",
                {"task_id": task_id},
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
                f"\nREPEATING SAME TASK COMPLETION: {task_id}"
            )

            write_2 = await client.call_tool(
                "report_task_completed",
                {"task_id": task_id},
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
            {"task_id": "this_task_does_not_exist"},
        )

        print(json.dumps(tool_data(invalid_result), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
