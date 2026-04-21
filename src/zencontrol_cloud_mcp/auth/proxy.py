"""OAuth resource-server provider for ZenControl in HTTP/StreamableHTTP transport mode.

This module implements the server side of the OAuth 2.0 resource-server pattern
for multi-user HTTP deployments.  The MCP server itself never handles user
credentials — authentication is delegated entirely to ZenControl's OAuth server.

Authentication flow
-------------------
1. **Discovery**: The MCP client calls ``/.well-known/oauth-protected-resource``
   on this server.  The response advertises ZenControl's authorization server
   (``https://login.zencontrol.com/oauth/authorize``) as the place to obtain
   tokens.

2. **Token acquisition** (outside this server): The MCP client directs the user
   to ZenControl's authorization server, which handles login and issues an
   opaque access token.  This server is not involved and never sees the user's
   ZenControl password or OAuth client secret.

3. **API calls**: The MCP client sends requests to this server with an
   ``Authorization: Bearer <token>`` header.

4. **Token validation** (:class:`ZenControlTokenVerifier`): For each request,
   this server validates the bearer token by calling the ZenControl REST API
   (``GET /v2/sites``).  A 200 response means the token is valid; a 401 means
   it is not.  ZenControl issues opaque (non-JWT) tokens, so there is no local
   signature verification — a live API call is the only validation method.

Note: TLS (HTTPS) is required for production deployments.  Without it, bearer
tokens are transmitted in cleartext.  Set ``ZENCONTROL_PUBLIC_URL`` to the
public HTTPS URL of this server.
"""

from __future__ import annotations

import logging

import httpx
from fastmcp.server.auth import AccessToken, RemoteAuthProvider, TokenVerifier

from zencontrol_cloud_mcp.auth.oauth import AUTHORIZE_URL

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
