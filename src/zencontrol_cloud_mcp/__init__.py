"""ZenControl MCP Server — DALI-2 lighting control via Model Context Protocol."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("zencontrol-cloud-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0"
