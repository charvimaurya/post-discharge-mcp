"""
Start the local web bridge that the Next.js API routes call.

LOCAL ONLY: binds to 127.0.0.1. MCP_URL and MCP_AUTH_TOKEN are read
from the environment / .env by this process and never sent onward.

Usage:

    python scripts/run_web_bridge.py
    python scripts/run_web_bridge.py --port 8002

Then set AGENT_API_URL=http://127.0.0.1:8002 for `npm run dev` in web/.
"""

import argparse
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT))

    uvicorn.run("app.web_bridge:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
