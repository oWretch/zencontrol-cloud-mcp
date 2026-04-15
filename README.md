# zencontrol-mcp

MCP server for ZenControl DALI-2 lighting control.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

## Overview

**zencontrol-mcp** enables AI assistants — such as Claude, Cursor, and other
MCP-compatible clients — to discover and control
[ZenControl](https://zencontrol.com/) DALI-2 lighting systems through natural
language.

Built on the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP)
with [FastMCP](https://github.com/jlowin/fastmcp), the server supports two
transports:

- **stdio** — for local, single-user setups (Claude Desktop, Cursor, etc.)
- **StreamableHTTP** — for hosted / multi-user deployments

## Features

| Tool | Description |
|------|-------------|
| `list_sites` | Discover accessible ZenControl sites |
| `get_site_details` | Explore site hierarchy (floors, zones, gateways, tenancies) |
| `list_groups` | List lighting groups by scope (site, floor, map, or gateway) |
| `list_devices` | List devices and their ECGs by scope |
| `control_light` | On/off, dim, set level (0–100 %), recall scenes, identify |
| `set_colour` | Colour temperature (Kelvin) or RGBWAF control |

## Prerequisites

- **Python 3.11+**
- **ZenControl Cloud account** with API credentials (`client_id` and
  `client_secret`) — request them from
  [ZenControl Support](https://support.zencontrol.com/hc/en-us/requests/new)
- **[uv](https://docs.astral.sh/uv/)** package manager (recommended) or `pip`

## Quick Start

1. **Set your credentials:**

   ```bash
   export ZENCONTROL_CLIENT_ID=your_client_id
   export ZENCONTROL_CLIENT_SECRET=your_client_secret
   ```

2. **Run with `uvx`:**

   ```bash
   uvx zencontrol-mcp
   ```

   On first launch a browser window will open so you can log in to ZenControl.
   After that, tokens are cached and refreshed automatically.

## Configuration

### Claude Desktop (stdio mode)

Add the following to your Claude Desktop configuration file:

```json
{
  "mcpServers": {
    "zencontrol": {
      "command": "uvx",
      "args": ["zencontrol-mcp"],
      "env": {
        "ZENCONTROL_CLIENT_ID": "your_client_id",
        "ZENCONTROL_CLIENT_SECRET": "your_client_secret"
      }
    }
  }
}
```

### HTTP mode (hosted)

Start the server on a network port:

```bash
uvx zencontrol-mcp --transport streamable-http --port 9000
```

Then point your MCP client at the HTTP endpoint:

```json
{
  "mcpServers": {
    "zencontrol": {
      "url": "http://localhost:9000/mcp"
    }
  }
}
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ZENCONTROL_CLIENT_ID` | Yes | — | OAuth client ID |
| `ZENCONTROL_CLIENT_SECRET` | Yes | — | OAuth client secret |
| `ZENCONTROL_REDIRECT_URI` | No | `http://localhost:9000/callback` | OAuth redirect URI |
| `ZENCONTROL_PORT` | No | `9000` | HTTP server port |

## Authentication

The server uses **OAuth 2.0 Authorization Code** flow to authenticate with the
ZenControl Cloud API.

1. On first run the server opens your default browser so you can log in.
2. Tokens are stored **encrypted** in a platform-appropriate location (via
   [`platformdirs`](https://github.com/tox-dev/platformdirs)).
3. Tokens are **refreshed automatically** when they expire — you should rarely
   need to re-authenticate.

## Usage Examples

Typical interactions with an AI assistant:

```text
User: "What sites do I have access to?"
→ Calls list_sites

User: "Show me the structure of the Main Office site"
→ Calls get_site_details

User: "Turn on all lights in the Lobby group"
→ Calls control_light(target_type="group", target_id="...", action="on")

User: "Set the office lights to 50% brightness"
→ Calls control_light(target_type="group", target_id="...", action="set_level", level=50)

User: "Change the lobby to warm white (3000K)"
→ Calls set_colour(target_type="group", target_id="...", mode="temperature", kelvin=3000)
```

## Architecture

```mermaid
graph LR
    Client["MCP Client<br/>(Claude, Cursor, …)"]
    Server["zencontrol-mcp<br/>FastMCP Server"]
    API["ZenControl<br/>Cloud API"]
    Tokens["Encrypted<br/>Token Store"]

    Client -- "stdio / StreamableHTTP" --> Server
    Server -- "REST + Live API" --> API
    Server -- "read / write" --> Tokens
```

## Development

```bash
git clone https://github.com/oWretch/zencontrol-mcp.git
cd zencontrol-mcp
uv sync

# Lint & format
uv run ruff check src/
uv run ruff format --check src/

# Run tests
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

## License

This project is licensed under the [MIT License](LICENSE).
