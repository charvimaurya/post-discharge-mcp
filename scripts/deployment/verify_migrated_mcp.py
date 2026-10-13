"""Check deployed MCP reads/search without displaying patient data or bearer tokens."""

import asyncio
import json

import boto3
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client


async def main():
    token = boto3.client("secretsmanager", region_name="eu-west-2").get_secret_value(SecretId="afterward/mcp/auth-token")["SecretString"]
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:3000"}
    async with create_mcp_http_client(headers=headers) as http, streamable_http_client("https://dakpc9juquqks.cloudfront.net/mcp", http_client=http) as streams:
        read, write = streams[:2]
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"MCP connected; {len(tools.tools)} tools available", flush=True)
            for name, args in [("get_recovery_plan", {}), ("get_today_tasks", {}), ("get_medications", {}), ("search_discharge_instructions", {"query": "What does my letter say about driving?"})]:
                result = await session.call_tool(name, args)
                data = result.structured_content
                if not data:
                    data = json.loads(next(c.text for c in result.content if hasattr(c, "text")))
                status = "ok" if data.get("ok") is True else data.get("error", {}).get("code", data.get("status", "unknown"))
                print(f"{name}: status={status}, protocol_error={result.is_error}", flush=True)
                if result.is_error or data.get("ok") is False or status == "error":
                    raise RuntimeError(f"{name} failed")


if __name__ == "__main__":
    asyncio.run(main())
