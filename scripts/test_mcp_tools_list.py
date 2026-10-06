import asyncio
import sys
from pathlib import Path

# Support direct execution from scripts/ without requiring package installation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.mcp.server import mcp


async def main():

    tools = await mcp.list_tools()

    for tool in tools:
        print()
        print("NAME:")
        print(tool.name)

        print("DESCRIPTION:")
        print(tool.description)

        print("INPUT SCHEMA:")
        print(tool.input_schema)

        print("ANNOTATIONS:")
        print(
            tool.annotations.model_dump(
                by_alias=True,
                exclude_none=True,
            )
            if tool.annotations
            else None
        )


asyncio.run(main())