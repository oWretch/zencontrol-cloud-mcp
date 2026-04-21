"""Shared OAuth 2.0 flow logic for ZenControl authentication."""

from __future__ import annotations

import hashlib
import logging
import secrets
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://login.zencontrol.com/oauth/authorize"
TOKEN_URL = "https://login.zencontrol.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://localhost:9000/callback"
API_BASE_URL = "https://api.zencontrol.com"


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str | None = None,
) -> str:
    """Build the OAuth authorization URL with the required query parameters."""
    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if code_challenge is not None:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> dict:
    """Exchange an authorization code for access and refresh tokens."""
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    if code_verifier is not None:
        payload["code_verifier"] = code_verifier

    logger.debug("Exchanging authorization code for tokens")
    async with httpx.AsyncClient() as client:
        response = await client.post(TOKEN_URL, data=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"Token exchange failed (HTTP {response.status_code}): {response.text}"
            )
        return response.json()


async def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    """Refresh an expired access token using a refresh token."""
    payload: dict[str, str] = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    logger.debug("Refreshing access token")
    async with httpx.AsyncClient() as client:
        response = await client.post(TOKEN_URL, data=payload)
        if response.status_code != 200:
            raise RuntimeError(
                f"Token refresh failed (HTTP {response.status_code}): {response.text}"
            )
        return response.json()


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge pair.

    The code_verifier is a random URL-safe base64 string (43–128 characters).
    The code_challenge is the SHA-256 hash of the verifier, base64url-encoded
    without padding.
    """
    code_verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    # base64url encoding without padding
    import base64

    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge
