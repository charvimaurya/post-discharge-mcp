"""
Golden Phase 13 test runner.

This script tests the conversational agent directly,
without needing the web UI.

It checks:
- what the user said
- what AfterWard replied
- which MCP tool was called
- whether a source was returned

MCP target (the server the agent's tools call):

    python scripts/test_agent.py --local
        → local test server at http://127.0.0.1:8000/mcp
          (start it with: python scripts/run_test_mcp.py)

    python scripts/test_agent.py --mcp-url <url>
        → any explicit MCP URL

    python scripts/test_agent.py
        → MCP_URL from the environment / .env (the deployed server)

The deployed server uses the real clock, so before the synthetic
patient's discharge date it correctly has no tasks or medications.
Use --local with run_test_mcp.py for the full golden run.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Support direct execution from scripts/ without requiring package installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.service import chat
from app.agent.session import clear_session
from app.mcp.client import call_mcp_tool

LOCAL_TEST_MCP_URL = "http://127.0.0.1:8000/mcp"


# Use one fixed session for the test run.
SESSION_ID = "phase13-golden-test"


# These are the main Phase 13 demo prompts.
TEST_MESSAGES = [
    "What do I need to do today?",
    "I've taken my morning paracetamol.",
    "Alexa, I'm back from my 7:30 am walk.",
    "What's left?",
    "What did my paperwork say about driving?",
    "How long do I take the blood thinner for?",
    "I took my medicine.",
    "Thanks, Alexa. I'm just getting ready.",
]


def _select_target() -> str:
    """Point the agent's MCP client at the requested server."""

    parser = argparse.ArgumentParser(
        description="Run the Phase 13 golden prompts through the agent.",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--local",
        action="store_true",
        help=f"Use the local test MCP server ({LOCAL_TEST_MCP_URL}).",
    )
    target.add_argument(
        "--mcp-url",
        help="Use this MCP URL.",
    )
    args = parser.parse_args()

    if args.local:
        os.environ["MCP_URL"] = LOCAL_TEST_MCP_URL
    elif args.mcp_url:
        os.environ["MCP_URL"] = args.mcp_url

    if not os.environ.get("MCP_URL"):
        parser.error("MCP_URL is not set; pass --local or --mcp-url.")

    return os.environ["MCP_URL"]


async def _server_date() -> str:
    """Ask the MCP server which day it considers today (read-only)."""

    result = await call_mcp_tool("get_today_tasks", {})

    for block in getattr(result, "content", None) or []:
        try:
            return json.loads(block.text)["data"]["date"]
        except (AttributeError, KeyError, TypeError, ValueError):
            continue

    return "unknown"


async def main():
    """
    Run each test message through the Phase 13 agent.
    """

    mcp_url = _select_target()

    print(f"MCP target:  {mcp_url}")
    print(f"Server date: {await _server_date()}")
    print(
        "Note: write prompts record real Event History entries. "
        "Reset with: python scripts/reset_demo_patient.py --confirm"
    )

    # Start with a clean conversation.
    clear_session(SESSION_ID)

    for message in TEST_MESSAGES:

        print("\n" + "=" * 70)

        print("USER:")
        print(message)

        # Call the agent directly.
        #
        # NOTE:
        # Depending on how your chat() function is currently written,
        # you may also need to pass patient_context here.
        result = await chat(
            message=message,
            session_id=SESSION_ID,
            patient_context=None,
        )

        print("\nAFTERWARD:")
        print(result["response"])

        print("\nTOOL TRACE:")
        print(
            json.dumps(
                result["tool_trace"],
                indent=2,
            )
        )

        print("\nSOURCE:")
        print(
            json.dumps(
                result.get("source"),
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())