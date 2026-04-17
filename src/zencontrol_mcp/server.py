"""ZenControl MCP Server — entry point for both stdio and HTTP transports.

Authentication
--------------

**stdio mode** (default — for local AI assistants such as Claude Desktop):

  The server manages the full OAuth 2.0 authorization-code + PKCE flow
  locally.  On first run it opens a browser to the ZenControl login page to
  obtain an access token, which is then encrypted and cached on disk.
  Subsequent calls refresh the token automatically.

  Required environment variables:
    ZENCONTROL_CLIENT_ID      — your ZenControl OAuth client ID
    ZENCONTROL_CLIENT_SECRET  — your ZenControl OAuth client secret

  Both values are per-user credentials obtained from ZenControl support.
  They are never transmitted to any party other than the ZenControl
  authorization server (https://login.zencontrol.com).

**streamable-http mode** (for hosted / multi-user deployments):

  The server acts as a pure OAuth 2.0 *resource server*.  It does **not**
  manage credentials or initiate any OAuth flow itself.  The expected flow is:

    1. The MCP client discovers the authorization server via the
       ``/.well-known/oauth-protected-resource`` metadata endpoint.
    2. The MCP client directs the user to ZenControl's authorization server
       (https://login.zencontrol.com/oauth/authorize) to obtain an access
       token using their own OAuth client credentials.
    3. The MCP client presents the token as ``Authorization: Bearer <token>``
       on each request to this server.
    4. This server validates the token by making a lightweight call to the
       ZenControl API and, if valid, executes the requested tool.

  ``ZENCONTROL_CLIENT_ID`` and ``ZENCONTROL_CLIENT_SECRET`` are **not**
  required or used in HTTP mode.

  Set ``ZENCONTROL_PUBLIC_URL`` to the public-facing HTTPS URL of this server
  (e.g. ``https://mcp.example.com``).  Bearer tokens are only protected in
  transit when HTTPS is used — plain HTTP is only acceptable for local
  testing.

Payload compatibility
---------------------

The ZenControl API can return some label fields as either wrapped sync objects
(``{"value": "Office"}``) or plain strings (``"Office"``). The server's
Pydantic models are intentionally tolerant of both shapes so site-hierarchy
tools (such as ``get_site_details``) remain stable across payload variations.
"""

from __future__ import annotations

import argparse
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastmcp import FastMCP

from zencontrol_mcp.api.client import ZenControlClient
from zencontrol_mcp.api.live import LiveClient
from zencontrol_mcp.api.rest import ZenControlAPI
from zencontrol_mcp.auth.proxy import create_remote_auth_provider
from zencontrol_mcp.auth.token_store import TokenStore
from zencontrol_mcp.resources import hierarchy as hierarchy_resources
from zencontrol_mcp.scope import ScopeConstraint
from zencontrol_mcp.tools import register_all_tools

logger = logging.getLogger(__name__)

_DEFAULT_REDIRECT_URI = "http://localhost:9000/callback"


def _load_config(transport: str) -> dict[str, str]:
    """Load configuration from environment variables.

    In **stdio** mode the server manages the full OAuth flow and requires
    ``ZENCONTROL_CLIENT_ID`` and ``ZENCONTROL_CLIENT_SECRET``.

    In **streamable-http** mode authentication is delegated entirely to
    ZenControl's OAuth server — client credentials are not needed or loaded
    by this server.
    """
    config: dict[str, str] = {
        "redirect_uri": os.environ.get(
            "ZENCONTROL_REDIRECT_URI", _DEFAULT_REDIRECT_URI
        ),
    }

    if transport == "stdio":
        client_id = os.environ.get("ZENCONTROL_CLIENT_ID", "")
        client_secret = os.environ.get("ZENCONTROL_CLIENT_SECRET", "")

        missing: list[str] = []
        if not client_id:
            missing.append("ZENCONTROL_CLIENT_ID")
        if not client_secret:
            missing.append("ZENCONTROL_CLIENT_SECRET")
        if missing:
            msg = (
                f"Required environment variable(s) not set: {', '.join(missing)}. "
                "Set them in a .env file in the working directory, your shell profile, "
                "or pass them when launching the server."
            )
            raise SystemExit(msg)

        config["client_id"] = client_id
        config["client_secret"] = client_secret

    return config


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Set up and tear down the API client."""
    transport: str = getattr(server, "_zencontrol_transport", "stdio")
    config = _load_config(transport)

    if transport == "stdio":
        token_store = TokenStore(
            client_id=config["client_id"],
            client_secret=config["client_secret"],
            redirect_uri=config["redirect_uri"],
        )
        client = ZenControlClient(token_store=token_store)
        live_client = LiveClient(token_factory=token_store.get_valid_token)
    else:
        from fastmcp.server.dependencies import get_access_token

        async def _token_factory() -> str:
            access_token = get_access_token()
            if access_token is None:
                raise RuntimeError("No authenticated user in HTTP mode")
            return access_token.token

        client = ZenControlClient(token_factory=_token_factory)
        live_client = LiveClient(token_factory=_token_factory)

    api = ZenControlAPI(client)

    # Validate credentials at startup — surfaces auth errors early.
    # In stdio mode this also warms up the token (triggers OAuth if needed).
    # In HTTP mode, we skip this because auth is per-request.
    if transport == "stdio":
        try:
            sites = await api.list_sites()
            logger.info("Credentials validated — %d site(s) accessible.", len(sites))
        except Exception as exc:
            raise SystemExit(
                f"Startup failed: could not validate ZenControl credentials: {exc}"
            ) from exc

    # Scope constraint — optionally locked to a site via env var.
    # Accepts UUID, tag (e.g. "brown-home"), or name.
    initial_site = os.environ.get("ZENCONTROL_SCOPE_SITE")
    scope = ScopeConstraint()
    if initial_site:
        try:
            site = await api.resolve_site_identifier(initial_site)
            scope.set_site(
                site.site_id or initial_site,
                tag=site.tag,
                name=site.name,
            )
            logger.info(
                "Scope initialised from env: %s (%s)",
                site.tag or site.name or site.site_id,
                site.site_id,
            )
        except ValueError as exc:
            # Bad config — unrecognisable site identifier; crash so the user knows.
            raise SystemExit(
                f"ZENCONTROL_SCOPE_SITE={initial_site!r} is not a valid site identifier: {exc}"
            ) from exc
        except Exception as exc:
            # Transient (network, timeout) — warn and start without scope constraint.
            logger.warning(
                "ZENCONTROL_SCOPE_SITE=%r could not be resolved: %s — "
                "starting without scope constraint.",
                initial_site,
                exc,
            )

    try:
        yield {
            "api": api,
            "live": live_client,
            "scope": scope,
            "multi_user": transport != "stdio",
        }
    finally:
        await client.close()


def create_server(
    transport: str = "stdio",
    port: int = 9000,
    host: str = "0.0.0.0",  # noqa: S104
) -> FastMCP:
    """Create a configured FastMCP server instance."""
    auth = None

    if transport == "streamable-http":
        public_url = os.environ.get("ZENCONTROL_PUBLIC_URL")
        if not public_url:
            # Normalise wildcard bind addresses to a usable localhost URL.
            _effective_host = "localhost" if host in ("0.0.0.0", "::", "") else host
            public_url = f"http://{_effective_host}:{port}"
        if not public_url.startswith("https://"):
            logger.warning(
                "ZENCONTROL_PUBLIC_URL is not HTTPS (%r). Bearer tokens will be "
                "transmitted in cleartext. Set ZENCONTROL_PUBLIC_URL to the "
                "public-facing HTTPS URL for any non-local deployment.",
                public_url,
            )
        auth = create_remote_auth_provider(base_url=public_url)

    mcp = FastMCP(
        name="ZenControl",
        instructions=(
            "You are connected to a ZenControl DALI-2 lighting system.\n"
            "You can list sites, discover devices and groups, and control lights.\n"
            "\n"
            "Site hierarchy is available as browsable resources:\n"
            "  zencontrol://sites — all accessible sites\n"
            "  zencontrol://sites/{tag}/groups — groups for a site (use tag or UUID)\n"
            "  zencontrol://sites/{tag}/zones — zones, floors, gateways, scenes, profiles\n"
            "\n"
            "Start by reading zencontrol://sites to see available sites. Use "
            "control_light to adjust brightness and set_colour for colour temperature "
            "or RGB control.\n"
            "\n"
            "Light levels are specified as percentages (0-100%). Scene numbers "
            "are 0-15. Groups are the most common way to control lights — they "
            "represent collections of lights that work together (e.g., "
            '"Office 3.02", "Lobby lights").'
        ),
        auth=auth,
        lifespan=_lifespan,
    )

    # Store transport mode for lifespan to use
    mcp._zencontrol_transport = transport  # type: ignore[attr-defined]

    register_all_tools(mcp)
    hierarchy_resources.register(mcp)

    return mcp


def main() -> None:
    """CLI entry point for the ZenControl MCP server."""
    parser = argparse.ArgumentParser(description="ZenControl MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("ZENCONTROL_PORT", "9000")),
        help="Port for HTTP transport (default: 9000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",  # noqa: S104
        help="Host for HTTP transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    load_dotenv()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    server = create_server(
        transport=args.transport,
        port=args.port,
        host=args.host,
    )

    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
