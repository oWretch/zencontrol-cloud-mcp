"""Async HTTP client for the ZenControl Cloud API."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from zencontrol_mcp.auth.token_store import TokenStore

logger = logging.getLogger(__name__)


class ZenControlClient:
    """Async HTTP client for the ZenControl Cloud API.

    Handles authentication, automatic token refresh, rate limiting,
    and retry logic with exponential backoff.

    Operates in two modes:
    - **stdio mode**: Uses a ``TokenStore`` for locally-managed OAuth tokens.
    - **HTTP/proxy mode**: Uses an async ``token_factory`` callable to obtain
      tokens from the upstream request context.
    """

    BASE_URL = "https://api.zencontrol.com"

    def __init__(
        self,
        token_store: TokenStore | None = None,
        token_factory: Callable[[], Awaitable[str]] | None = None,
        base_url: str = BASE_URL,
        max_retries: int = 3,
        rate_limit_rps: float = 10.0,
    ) -> None:
        if token_store is None and token_factory is None:
            msg = "Either token_store or token_factory must be provided"
            raise ValueError(msg)

        self._token_store = token_store
        self._token_factory = token_factory
        self._base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._min_request_interval = 1.0 / rate_limit_rps

        self._cached_token: str | None = None
        self._last_request_time: float = 0.0

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=30.0,
                read=60.0,
                write=30.0,
                pool=30.0,
            ),
        )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        """Get a valid access token from the configured source."""
        if self._cached_token is not None:
            return self._cached_token

        if self._token_factory is not None:
            token = await self._token_factory()
        elif self._token_store is not None:
            token = await self._token_store.get_access_token()
        else:
            msg = "No token source configured"
            raise RuntimeError(msg)

        self._cached_token = token
        return token

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def _apply_rate_limit(self) -> None:
        """Enforce minimum spacing between requests (token-bucket)."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    # ------------------------------------------------------------------
    # Request / retry
    # ------------------------------------------------------------------

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request with retry logic.

        * 401 → clear cached token, retry once.
        * 429 → exponential backoff with ``Retry-After`` + jitter.
        * 5xx → exponential backoff + jitter.
        """
        url = f"{self._base_url}{path}"
        extra_headers: dict[str, str] = kwargs.pop("headers", {})
        response: httpx.Response | None = None

        for attempt in range(self.max_retries + 1):
            token = await self._get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                **extra_headers,
            }

            await self._apply_rate_limit()

            logger.debug(
                "API %s %s (attempt %d/%d)",
                method,
                url,
                attempt + 1,
                self.max_retries + 1,
            )
            response = await self._client.request(
                method,
                url,
                headers=headers,
                **kwargs,
            )

            if response.status_code == 401 and attempt == 0:
                logger.debug("Received 401, refreshing token and retrying")
                self._cached_token = None
                continue

            if response.status_code == 429:
                retry_after = float(
                    response.headers.get("Retry-After", str(2**attempt))
                )
                jitter = random.uniform(0, 1)  # noqa: S311
                wait = retry_after + jitter
                logger.warning("Rate limited (429), waiting %.1fs", wait)
                await asyncio.sleep(wait)
                continue

            if response.status_code >= 500:
                wait = 2**attempt + random.uniform(0, 1)  # noqa: S311
                logger.warning(
                    "Server error (%d), waiting %.1fs",
                    response.status_code,
                    wait,
                )
                await asyncio.sleep(wait)
                continue

            return response

        # Retries exhausted — return the last response for the caller to handle
        assert response is not None  # noqa: S101
        return response

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an authenticated request to the ZenControl API.

        Parameters
        ----------
        method:
            HTTP method (GET, POST, …).
        path:
            URL path relative to the base URL (e.g. ``/v2/sites``).
        **kwargs:
            Forwarded to :pymethod:`httpx.AsyncClient.request`.
        """
        return await self._request_with_retry(method, path, **kwargs)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Convenience method for GET requests."""
        return await self.request("GET", path, params=params)

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Convenience method for POST requests."""
        return await self.request("POST", path, json=json)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> ZenControlClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.close()
