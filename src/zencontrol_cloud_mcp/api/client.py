"""Async HTTP client for the ZenControl Cloud API."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from zencontrol_cloud_mcp.auth.token_store import TokenStore

logger = logging.getLogger(__name__)


class ZenControlClient:
    """Async HTTP client for the ZenControl Cloud API.

    Handles authentication, automatic token refresh, rate limiting,
    and retry logic with exponential backoff.

    Operates in two modes:
    - **stdio mode**: Uses a ``TokenStore`` for locally-managed OAuth tokens.
      The resolved token is cached in memory between calls.
    - **HTTP/proxy mode**: Uses an async ``token_factory`` callable to obtain
      tokens from the upstream request context. The token is **never** cached
      because each concurrent request may belong to a different user.

    In both modes GET responses are cached per-token-hash to avoid redundant
    API calls. The cache is keyed by ``(sha256(token)[:16], method, path,
    params)`` so that different users always get their own isolated cache
    entries. POST requests are never cached.
    """

    BASE_URL = "https://api.zencontrol.com"

    def __init__(
        self,
        token_store: TokenStore | None = None,
        token_factory: Callable[[], Awaitable[str]] | None = None,
        base_url: str = BASE_URL,
        max_retries: int = 3,
        rate_limit_rps: float = 10.0,
        cache_ttl: float = 60.0,
    ) -> None:
        if token_store is None and token_factory is None:
            msg = "Either token_store or token_factory must be provided"
            raise ValueError(msg)

        self._token_store = token_store
        self._token_factory = token_factory
        self._base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._min_request_interval = 1.0 / rate_limit_rps
        self._cache_ttl = cache_ttl

        # Token cache — only populated in stdio mode (single user).
        self._cached_token: str | None = None
        self._last_request_time: float = 0.0

        # Per-token-hash GET response cache.
        # Key: (token_hash, url_path, frozen_params)
        # Value: (monotonic_timestamp, response_content_bytes)
        self._response_cache: dict[tuple, tuple[float, bytes]] = {}
        _MAX_CACHE_SIZE = 500

        self._MAX_CACHE_SIZE = _MAX_CACHE_SIZE

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
        """Get a valid access token from the configured source.

        In HTTP mode (``_token_factory`` set) the token is **never** cached
        because each concurrent request belongs to a different user — the
        factory performs a cheap ``contextvars`` lookup instead.

        In stdio mode (``_token_store`` set) the token is cached in memory
        after the first call to avoid redundant token refreshes.
        """
        if self._token_factory is not None:
            # HTTP mode: always call factory — no caching across users.
            return await self._token_factory()

        # stdio mode: cache the token to avoid repeated store I/O.
        if self._cached_token is not None:
            return self._cached_token

        token = await self._token_store.get_valid_token()  # type: ignore[union-attr]
        self._cached_token = token
        return token

    # ------------------------------------------------------------------
    # Response cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _token_hash(token: str) -> str:
        """Return a short, stable hash of a token for use as a cache key."""
        return hashlib.sha256(token.encode()).hexdigest()[:16]

    def _cache_key(self, token: str, path: str, params: dict[str, Any] | None) -> tuple:
        return (
            self._token_hash(token),
            path,
            tuple(sorted((params or {}).items())),
        )

    def _cache_get(self, key: tuple) -> bytes | None:
        """Return cached content bytes if present and not expired."""
        entry = self._response_cache.get(key)
        if entry is None:
            return None
        ts, content = entry
        if time.monotonic() - ts > self._cache_ttl:
            del self._response_cache[key]
            return None
        return content

    def _cache_put(self, key: tuple, content: bytes) -> None:
        """Store response content bytes, evicting oldest entry if at capacity."""
        if len(self._response_cache) >= self._MAX_CACHE_SIZE:
            oldest_key = min(self._response_cache, key=lambda k: self._response_cache[k][0])
            del self._response_cache[oldest_key]
        self._response_cache[key] = (time.monotonic(), content)

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
                retry_after = float(response.headers.get("Retry-After", str(2**attempt)))
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
        if response is None:
            raise RuntimeError("All retries exhausted without receiving a response")
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
        """Convenience method for GET requests with per-token response caching.

        Responses are cached for ``cache_ttl`` seconds, keyed by a hash of the
        current user's token so that different users never share cache entries.
        Set ``cache_ttl=0`` at construction time to disable caching (useful in
        tests).
        """
        if self._cache_ttl > 0:
            token = await self._get_token()
            key = self._cache_key(token, path, params)
            cached = self._cache_get(key)
            if cached is not None:
                logger.debug("Cache hit: GET %s", path)
                cached_response = httpx.Response(200, content=cached)
                cached_response.request = httpx.Request("GET", f"{self._base_url}{path}")
                return cached_response

        response = await self._request_with_retry("GET", path, params=params)

        if self._cache_ttl > 0 and response.is_success:
            # Re-fetch token in case it was refreshed during the request (401 retry).
            token = await self._get_token()
            key = self._cache_key(token, path, params)
            self._cache_put(key, response.content)

        return response

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Convenience method for POST requests (never cached)."""
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
