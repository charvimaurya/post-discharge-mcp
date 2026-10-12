r"""
Start the local web bridge that the Next.js API routes call.

LOCAL ONLY: binds to 127.0.0.1. MCP_URL and MCP_AUTH_TOKEN are read
from the environment / .env by this process and never sent onward.

Usage:

    python scripts/run_web_bridge.py
    python scripts/run_web_bridge.py --port 8002

Then set AGENT_API_URL=http://127.0.0.1:8002 for `npm run dev` in web/.

Local reminder loop (a stand-in for the EventBridge schedule):

    LOCAL_REMINDER_LOOP=1 CLOCK_MODE=demo DEMO_FIXED_NOW=2026-10-23T07:00:00+01:00 \
        python scripts/run_web_bridge.py

With LOCAL_REMINDER_LOOP=1 the bridge calls the same reminder handler
as the deployed Lambda (lambdas/reminder_checker/handler.py) every
REMINDER_LOOP_SECONDS (default 15). In CLOCK_MODE=demo the fixed time is
passed as demo_now. Each run prints one line: created,
already_reminded, nothing_due or error. A created reminder is written
to the live RecoveryState table, as the Lambda would.
"""

import argparse
import logging
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT))

    # Show the app's own INFO lines (such as the reminder loop) next to
    # uvicorn's; other libraries, like boto3, stay at WARNING.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s:     %(message)s")
    logging.getLogger("app").setLevel(logging.INFO)

    uvicorn.run("app.web_bridge:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
