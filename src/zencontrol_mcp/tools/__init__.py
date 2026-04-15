"""MCP tool definitions for ZenControl lighting control."""

from __future__ import annotations

from typing import TYPE_CHECKING

from zencontrol_mcp.tools.control import register as register_control_tools
from zencontrol_mcp.tools.devices import register as register_device_tools
from zencontrol_mcp.tools.extended import register as register_extended_tools
from zencontrol_mcp.tools.live import register as register_live_tools
from zencontrol_mcp.tools.sites import register as register_site_tools

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register all tools with the FastMCP server."""
    register_site_tools(mcp)
    register_device_tools(mcp)
    register_control_tools(mcp)
    register_extended_tools(mcp)
    register_live_tools(mcp)
