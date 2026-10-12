"""
Start a LOCAL AfterWard MCP server.

LOCAL TESTING ONLY. The deployed ECS service never runs this and
always uses the real clock.

The golden agent test needs "today" to be on or after the
synthetic patient's discharge date; otherwise the before-discharge
guards (correctly) return no tasks or medications.

Clock: with --now, the server runs on that fixed demo time
(CLOCK_MODE=demo, DEMO_FIXED_NOW=<now>) for this process only.
Without --now it follows CLOCK_MODE from the environment / .env,
which is the real time by default. It never edits .env, ECS or code.

Usage:

    python scripts/run_test_mcp.py --port 8001                                  # real time
    python scripts/run_test_mcp.py --now 2026-10-23T07:50:00+01:00 --port 8001  # demo time

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
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clock import DEFAULT_DEMO_NOW, parse_demo_now



def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a local MCP server (real time, or a fixed demo time with --now).",
    )
    parser.add_argument(
        "--now",
        default=None,
        help=(
            "Run on a fixed demo time, e.g. "
            f"{DEFAULT_DEMO_NOW}. Without it, CLOCK_MODE decides (real by default)."
        ),
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

    env = dict(os.environ)

    if args.now:
        # Fail early on a malformed time instead of inside the server.
        parse_demo_now(args.now)
        # Set only for the server process started below.
        env.update(CLOCK_MODE="demo", DEMO_FIXED_NOW=args.now)
        clock_text = f"demo time, DEMO_FIXED_NOW={args.now}"
    else:
        clock_text = f"CLOCK_MODE={env.get('CLOCK_MODE') or 'real'} (from the environment / .env)"

    print(f"Local test MCP: http://{args.host}:{args.port}/mcp")
    print(f"Clock:          {clock_text}")
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
