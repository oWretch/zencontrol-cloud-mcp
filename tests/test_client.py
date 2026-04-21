"""Tests for ZenControlClient — HTTP layer, caching, and retry behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from zencontrol_cloud_mcp.api.client import ZenControlClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def token_factory_a():
    """Async token factory that always returns token 'user-a-token'."""
    return AsyncMock(return_value="user-a-token")


@pytest.fixture
def token_factory_b():
    """Async token factory that always returns token 'user-b-token'."""
    return AsyncMock(return_value="user-b-token")


@pytest.fixture
def client_a(token_factory_a):
    """ZenControlClient in HTTP mode for user A, with 60s cache TTL."""
    return ZenControlClient(token_factory=token_factory_a, cache_ttl=60.0)


@pytest.fixture
def client_no_cache(token_factory_a):
    """ZenControlClient with caching disabled."""
    return ZenControlClient(token_factory=token_factory_a, cache_ttl=0)


SITES_RESPONSE = {"sites": [{"siteId": "abc-123", "tag": "hq", "name": "HQ"}]}


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------


class TestTokenManagement:
    @pytest.mark.asyncio
    @respx.mock
    async def test_http_mode_never_caches_token(self, token_factory_a):
        """In HTTP mode the token factory must be called for every request."""
        client = ZenControlClient(token_factory=token_factory_a, cache_ttl=0)
        respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json=SITES_RESPONSE)
        )
        await client.get("/v2/sites")
        await client.get("/v2/sites")
        assert token_factory_a.call_count == 2
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_stdio_mode_caches_token(self):
        """In stdio mode the token store should be called only once."""
        token_store = AsyncMock()
        token_store.get_valid_token = AsyncMock(return_value="stdio-token")
        client = ZenControlClient(token_store=token_store, cache_ttl=0)

        respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json=SITES_RESPONSE)
        )
        await client.get("/v2/sites")
        await client.get("/v2/sites")
        assert token_store.get_valid_token.call_count == 1
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_401_clears_cached_token_and_retries(self):
        """A 401 response in stdio mode clears the cached token and retries."""
        token_store = AsyncMock()
        token_store.get_valid_token = AsyncMock(side_effect=["expired-token", "fresh-token"])
        client = ZenControlClient(token_store=token_store, cache_ttl=0)

        route = respx.get("https://api.zencontrol.com/v2/sites")
        route.side_effect = [
            httpx.Response(401),
            httpx.Response(200, json=SITES_RESPONSE),
        ]

        response = await client.get("/v2/sites")
        assert response.status_code == 200
        assert token_store.get_valid_token.call_count == 2
        await client.close()


# ---------------------------------------------------------------------------
# Rate limiting / retry
# ---------------------------------------------------------------------------


class TestRetryBehaviour:
    @pytest.mark.asyncio
    @respx.mock
    async def test_429_triggers_retry(self, client_no_cache):
        """A 429 response should trigger a retry after backoff."""
        route = respx.get("https://api.zencontrol.com/v2/sites")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json=SITES_RESPONSE),
        ]

        response = await client_no_cache.get("/v2/sites")
        assert response.status_code == 200
        assert route.call_count == 2
        await client_no_cache.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_5xx_triggers_retry(self, client_no_cache):
        """A 5xx response should trigger a retry."""
        route = respx.get("https://api.zencontrol.com/v2/sites")
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=SITES_RESPONSE),
        ]

        response = await client_no_cache.get("/v2/sites")
        assert response.status_code == 200
        assert route.call_count == 2
        await client_no_cache.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_exhausted_returns_last_response(self, client_no_cache):
        """When all retries are exhausted the last response is returned."""
        client_no_cache.max_retries = 1
        respx.get("https://api.zencontrol.com/v2/sites").mock(return_value=httpx.Response(503))

        response = await client_no_cache.get("/v2/sites")
        assert response.status_code == 503
        await client_no_cache.close()


# ---------------------------------------------------------------------------
# Response cache — per-token isolation
# ---------------------------------------------------------------------------


class TestResponseCache:
    @pytest.mark.asyncio
    @respx.mock
    async def test_get_uses_cache_on_second_call(self, client_a, token_factory_a):
        """Second GET to the same URL should use the cache without an HTTP call."""
        route = respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json=SITES_RESPONSE)
        )

        r1 = await client_a.get("/v2/sites")
        r2 = await client_a.get("/v2/sites")

        assert r1.json() == SITES_RESPONSE
        assert r2.json() == SITES_RESPONSE
        assert route.call_count == 1  # only one real HTTP call
        await client_a.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_different_tokens_do_not_share_cache(self, token_factory_a):
        """Two users with different tokens must each get their own cache entry."""
        user_a_data = {"sites": [{"siteId": "site-a"}]}
        user_b_data = {"sites": [{"siteId": "site-b"}]}

        factory_a = AsyncMock(return_value="token-user-a")
        factory_b = AsyncMock(return_value="token-user-b")

        client_a = ZenControlClient(token_factory=factory_a, cache_ttl=60.0)
        client_b = ZenControlClient(token_factory=factory_b, cache_ttl=60.0)

        # Share the underlying httpx mock — each call can return different data
        # because in practice the server filters by user. We simulate this by
        # having the mock return different payloads for the two clients.
        respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json=user_a_data)
        )

        r_a = await client_a.get("/v2/sites")
        assert r_a.json() == user_a_data

        # Re-mock to return user_b's data
        respx.routes.clear()
        respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json=user_b_data)
        )

        r_b = await client_b.get("/v2/sites")
        assert r_b.json() == user_b_data

        # Fetch for user_a again — should hit cache, NOT return user_b's data
        r_a2 = await client_a.get("/v2/sites")
        assert r_a2.json() == user_a_data

        await client_a.close()
        await client_b.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_cache_expires_after_ttl(self, token_factory_a):
        """Cache entries older than cache_ttl should be ignored."""
        client = ZenControlClient(token_factory=token_factory_a, cache_ttl=0.05)

        route = respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json=SITES_RESPONSE)
        )

        await client.get("/v2/sites")
        assert route.call_count == 1

        # Wait for TTL to expire
        import asyncio

        await asyncio.sleep(0.1)

        await client.get("/v2/sites")
        assert route.call_count == 2
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_is_never_cached(self, client_a):
        """POST requests must never be served from or stored in the cache."""
        route = respx.post("https://api.zencontrol.com/v1/groups/abc/command").mock(
            return_value=httpx.Response(200, json={})
        )

        await client_a.post("/v1/groups/abc/command", json={"type": "off"})
        await client_a.post("/v1/groups/abc/command", json={"type": "off"})

        assert route.call_count == 2
        await client_a.close()

    @pytest.mark.asyncio
    async def test_different_params_get_separate_cache_entries(self, client_a):
        """Cache keys must differ when query params differ."""
        key1 = client_a._cache_key("token", "/v2/sites/abc/groups", None)
        key2 = client_a._cache_key("token", "/v2/sites/abc/groups", {"permissionGroup": "ALL"})
        assert key1 != key2
        await client_a.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_cache_disabled_when_ttl_zero(self, client_no_cache):
        """When cache_ttl=0, every GET makes a real HTTP call."""
        route = respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json=SITES_RESPONSE)
        )

        await client_no_cache.get("/v2/sites")
        await client_no_cache.get("/v2/sites")

        assert route.call_count == 2
        await client_no_cache.close()


# ---------------------------------------------------------------------------
# Auth header injection
# ---------------------------------------------------------------------------


class TestAuthHeaders:
    @pytest.mark.asyncio
    @respx.mock
    async def test_bearer_token_injected(self, token_factory_a):
        """Every request must include Authorization: Bearer <token>."""
        factory = AsyncMock(return_value="my-secret-token")
        client = ZenControlClient(token_factory=factory, cache_ttl=0)

        route = respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json=SITES_RESPONSE)
        )

        await client.get("/v2/sites")

        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer my-secret-token"
        await client.close()
