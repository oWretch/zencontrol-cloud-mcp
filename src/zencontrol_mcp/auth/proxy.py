"""OAuthProxy provider for ZenControl in HTTP/StreamableHTTP transport mode.

Uses FastMCP's :class:`RemoteAuthProvider` to delegate authentication to
the ZenControl authorization server while validating opaque access tokens
by calling the ZenControl API.
"""

from __future__ import annotations

import logging

import httpx
from fastmcp.server.auth import AccessToken, RemoteAuthProvider, TokenVerifier

from zencontrol_mcp.auth.oauth import AUTHORIZE_URL

logger = logging.getLogger(__name__)


class ZenControlTokenVerifier(TokenVerifier):
    """Validates opaque ZenControl access tokens by calling the API.

    ZenControl issues opaque (non-JWT) tokens, so we validate them by
    making a lightweight API call and checking for a 401 response.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a ZenControl access token by calling the sites endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.zencontrol.com/v2/sites",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 401:
                    logger.debug("Token verification failed: 401 Unauthorized")
                    return None

                resp.raise_for_status()
                return AccessToken(
                    token=token,
                    client_id="zencontrol",
                    scopes=[],
                )
        except httpx.HTTPStatusError:
            logger.warning("Token verification request failed", exc_info=True)
            return None
        except httpx.HTTPError:
            logger.warning("Token verification network error", exc_info=True)
            return None


def create_remote_auth_provider(
    base_url: str = "http://localhost:9000",
) -> RemoteAuthProvider:
    """Create a :class:`RemoteAuthProvider` configured for ZenControl.

    Parameters
    ----------
    base_url:
        The public base URL of this MCP server (used for metadata endpoints).
    """
    verifier = ZenControlTokenVerifier()
    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[AUTHORIZE_URL],
        base_url=base_url,
        resource_name="ZenControl Lighting",
    )
