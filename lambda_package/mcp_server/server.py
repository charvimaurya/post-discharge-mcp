"""Expose MCP tools while keeping their implementations in the tools package."""

from mcp_server.tools.get_recovery_plan import get_recovery_plan

__all__ = ["get_recovery_plan"]
