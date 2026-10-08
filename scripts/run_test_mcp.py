"""
Start a LOCAL AfterWard MCP server with a fixed test clock.

LOCAL TESTING ONLY. The deployed ECS service never runs this and
always uses the real clock.

The golden agent test needs "today" to be on or after the
synthetic patient's discharge date; otherwise the before-discharge
guards (correctly) return no tasks or medications. This script sets
DEMO_FIXED_NOW for the server process it starts, and nothing else:
it does not edit .env, ECS, or any application code.

Usage:

    python scripts/run_test_mcp.py
    python scripts/run_test_mcp.py --now 2026-10-23T07:50:00+01:00 --port 8001

Then, in another terminal:

    python scripts/test_agent.py --local

Note: the server still uses the real DynamoDB tables from .env, so
writes made during a test run are real events dated on the test
day. Run `python scripts/reset_demo_patient.py --confirm` afterwards
to clear them.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TEST_NOW = "2026-10-23T07:50:00+01:00"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a local MCP server with a fixed test clock.",
    )
    parser.add_argument(
        "--now",
        default=DEFAULT_TEST_NOW,
        help=f"ISO 8601 time to pin the clock to (default {DEFAULT_TEST_NOW}).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default 127.0.0.1, local only).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port (default 8000).",
    )
    args = parser.parse_args()

    # Fail early on a malformed time instead of inside the server.
    datetime.fromisoformat(args.now.replace("Z", "+00:00"))

    # Set only for the server process started below.
    env = dict(os.environ, DEMO_FIXED_NOW=args.now)

    print(f"Local test MCP: http://{args.host}:{args.port}/mcp")
    print(f"Test clock:     DEMO_FIXED_NOW={args.now}")
    print("Stop with Ctrl+C.\n", flush=True)

    os.chdir(PROJECT_ROOT)
    os.execvpe(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.mcp.http_server:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        env,
    )


if __name__ == "__main__":
    main()
