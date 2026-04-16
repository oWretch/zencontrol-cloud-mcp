"""ZenControl MCP Server — entry point for both stdio and HTTP transports."""

from __future__ import annotations

import argparse
import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

from fastmcp import FastMCP
from fastmcp.server.auth import TokenVerifier

from zencontrol_mcp.api.client import ZenControlClient
from zencontrol_mcp.api.live import LiveClient
from zencontrol_mcp.api.rest import ZenControlAPI
from zencontrol_mcp.auth.token_store import TokenStore
from zencontrol_mcp.scope import ScopeConstraint
from zencontrol_mcp.tools import register_all_tools

if TYPE_CHECKING:
    from fastmcp.server.auth import AccessToken

logger = logging.getLogger(__name__)

_DEFAULT_REDIRECT_URI = "http://localhost:9000/callback"


def _load_config() -> dict[str, str]:
    """Load required configuration from environment variables."""
    client_id = os.environ.get("ZENCONTROL_CLIENT_ID")
    client_secret = os.environ.get("ZENCONTROL_CLIENT_SECRET")

    missing: list[str] = []
    if not client_id:
        missing.append("ZENCONTROL_CLIENT_ID")
    if not client_secret:
        missing.append("ZENCONTROL_CLIENT_SECRET")
    if missing:
        msg = (
            f"Required environment variable(s) not set: {', '.join(missing)}. "
            "Set them in your shell profile or pass them when launching the server."
        )
        raise SystemExit(msg)

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": os.environ.get(
            "ZENCONTROL_REDIRECT_URI", _DEFAULT_REDIRECT_URI
        ),
    }


class ZenControlTokenVerifier(TokenVerifier):
    """Validates opaque ZenControl access tokens by calling the API.

    Used only in HTTP (streamable-http) transport mode where the MCP server
    receives pre-authenticated Bearer tokens from the client.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        from fastmcp.server.auth import AccessToken

        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.zencontrol.com/v2/sites",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 401:
                return None
            resp.raise_for_status()
            return AccessToken(token=token, client_id="zencontrol", scopes=[])


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Set up and tear down the API client."""
    config = _load_config()

    transport: str = getattr(server, "_zencontrol_transport", "stdio")

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

    # Scope constraint — optionally locked to a site via env var
    initial_site = os.environ.get("ZENCONTROL_SCOPE_SITE")
    scope = ScopeConstraint(site_id=initial_site)
    if initial_site:
        logger.info("Scope constraint initialised from env: site %s", initial_site)

    try:
        yield {"api": api, "live": live_client, "scope": scope}
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
        from fastmcp.server.auth import RemoteAuthProvider

        verifier = ZenControlTokenVerifier()
        auth = RemoteAuthProvider(
            token_verifier=verifier,
            authorization_servers=["https://login.zencontrol.com"],
            base_url=f"http://{host}:{port}",
        )

    mcp = FastMCP(
        name="ZenControl",
        instructions=(
            "You are connected to a ZenControl DALI-2 lighting system.\n"
            "You can list sites, discover devices and groups, and control lights.\n"
            "\n"
            "Start by calling list_sites to see available sites, then use "
            "get_site_details to explore the hierarchy. Use control_light to "
            "adjust brightness and set_colour for colour temperature or RGB "
            "control.\n"
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
