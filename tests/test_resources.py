"""Tests for MCP hierarchy resources."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from zencontrol_mcp.models.schemas import (
    Floor,
    IntField,
    Scene,
    StatusField,
    StringField,
)
from zencontrol_mcp.scope import ScopeConstraint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    site_id: str = "site-uuid-1",
    site_tag: str = "test-site",
    scope_site: str | None = None,
):
    """Build a mock MCP context for resource tests."""
    api = MagicMock()

    resolved_site = MagicMock()
    resolved_site.site_id = site_id
    resolved_site.tag = site_tag
    resolved_site.name = "Test Site"
    api.resolve_site_identifier = AsyncMock(return_value=resolved_site)

    scope = ScopeConstraint(site_id=scope_site)
    ctx = MagicMock()
    ctx.lifespan_context = {"api": api, "scope": scope}
    return ctx, api


async def _get_resource_fn(name: str):
    """Extract the original resource/template handler by name.

    FastMCP wraps resource functions with its dependency injection machinery.
    This helper unwraps to the original function with a ``ctx`` parameter so
    tests can call it directly.
    """
    from fastmcp import FastMCP

    from zencontrol_mcp.resources.hierarchy import register

    mcp = FastMCP("test")
    register(mcp)

    # Static resources: fn.__closure__[0] is the original function
    resources = await mcp.list_resources()
    for resource in resources:
        if resource.name == name:
            return resource.fn.__closure__[0].cell_contents

    # Template resources: fn.raw_function.__closure__[0] is the original
    templates = await mcp.list_resource_templates()
    for template in templates:
        if template.name == name:
            return template.fn.raw_function.__closure__[0].cell_contents

    raise AssertionError(f"Resource '{name}' not found")


# ---------------------------------------------------------------------------
# zencontrol://sites
# ---------------------------------------------------------------------------


class TestSitesResource:
    @pytest.mark.asyncio
    async def test_lists_sites(self):
        fn = await _get_resource_fn("ZenControl Sites")
        ctx, api = _make_context()

        site = MagicMock()
        site.name = "Brown Home"
        site.tag = "brown-home"
        site.site_id = "uuid-1"
        site.address = None
        api.list_sites = AsyncMock(return_value=[site])

        result = await fn(ctx=ctx)
        assert "Brown Home" in result
        assert "brown-home" in result
        assert "zencontrol://sites/brown-home" in result

    @pytest.mark.asyncio
    async def test_empty_site_list(self):
        fn = await _get_resource_fn("ZenControl Sites")
        ctx, api = _make_context()
        api.list_sites = AsyncMock(return_value=[])

        result = await fn(ctx=ctx)
        assert "No sites accessible" in result

    @pytest.mark.asyncio
    async def test_scope_filters_sites(self):
        fn = await _get_resource_fn("ZenControl Sites")
        ctx, api = _make_context(scope_site="uuid-1")

        site_a = MagicMock()
        site_a.name = "Site A"
        site_a.tag = "site-a"
        site_a.site_id = "uuid-1"
        site_a.address = None

        site_b = MagicMock()
        site_b.name = "Site B"
        site_b.tag = "site-b"
        site_b.site_id = "uuid-2"
        site_b.address = None

        api.list_sites = AsyncMock(return_value=[site_a, site_b])

        result = await fn(ctx=ctx)
        assert "Site A" in result
        assert "Site B" not in result

    @pytest.mark.asyncio
    async def test_api_error_handled(self):
        fn = await _get_resource_fn("ZenControl Sites")
        ctx, api = _make_context()
        api.list_sites = AsyncMock(side_effect=Exception("Network error"))

        result = await fn(ctx=ctx)
        assert "Error" in result
        assert "Network error" in result


# ---------------------------------------------------------------------------
# zencontrol://sites/{site_id} (detail)
# ---------------------------------------------------------------------------


class TestSiteDetailResource:
    @pytest.mark.asyncio
    async def test_shows_hierarchy(self):
        fn = await _get_resource_fn("ZenControl Site Detail")
        ctx, api = _make_context()

        site = MagicMock()
        site.name = "Test Site"
        site.site_id = "site-uuid-1"
        site.tag = "test-site"
        site.building_size = 500.0
        site.address = None
        site.geographic_location = None
        api.get_site = AsyncMock(return_value=site)

        api.list_floors = AsyncMock(return_value=[])
        api.list_tenancies = AsyncMock(return_value=[])
        api.list_zones = AsyncMock(return_value=[])
        api.list_gateways = AsyncMock(return_value=[])

        result = await fn(site_id="test-site", ctx=ctx)
        assert "Test Site" in result
        assert "site-uuid-1" in result
        assert "test-site" in result

    @pytest.mark.asyncio
    async def test_resolution_error_returned(self):
        fn = await _get_resource_fn("ZenControl Site Detail")
        ctx, api = _make_context()
        api.resolve_site_identifier = AsyncMock(
            side_effect=ValueError("No site found matching 'bad-tag'")
        )

        result = await fn(site_id="bad-tag", ctx=ctx)
        assert "No site found" in result

    @pytest.mark.asyncio
    async def test_scope_blocks_wrong_site(self):
        fn = await _get_resource_fn("ZenControl Site Detail")
        ctx, api = _make_context(site_id="other-uuid", scope_site="allowed-uuid")

        result = await fn(site_id="other-site", ctx=ctx)
        assert "outside" in result


# ---------------------------------------------------------------------------
# Site sub-resources (floors, zones, groups, gateways, scenes, profiles)
# ---------------------------------------------------------------------------


class TestSiteSubResources:
    @pytest.mark.asyncio
    async def test_floors_resource(self):
        fn = await _get_resource_fn("ZenControl Site Floors")
        ctx, api = _make_context()

        floor = Floor(floorId="floor-1", label=StringField(value="Ground Floor"))
        api.list_floors = AsyncMock(return_value=[floor])

        result = await fn(site_id="test-site", ctx=ctx)
        assert "Ground Floor" in result
        assert "floor-1" in result

    @pytest.mark.asyncio
    async def test_floors_empty(self):
        fn = await _get_resource_fn("ZenControl Site Floors")
        ctx, api = _make_context()
        api.list_floors = AsyncMock(return_value=[])

        result = await fn(site_id="test-site", ctx=ctx)
        assert "No floors" in result

    @pytest.mark.asyncio
    async def test_zones_resource(self):
        fn = await _get_resource_fn("ZenControl Site Zones")
        ctx, api = _make_context()

        zone = MagicMock()
        zone.zone_id = "zone-uuid-1"
        zone.label = StringField(value="Office Zone", state="OK", error=None)
        zone.status = StatusField(value="ACTIVE", state="OK", error=None)
        api.list_zones = AsyncMock(return_value=[zone])

        result = await fn(site_id="test-site", ctx=ctx)
        assert "Office Zone" in result
        assert "zone-uuid-1" in result

    @pytest.mark.asyncio
    async def test_groups_resource(self):
        fn = await _get_resource_fn("ZenControl Site Groups")
        ctx, api = _make_context()

        group = MagicMock()
        group.label = StringField(value="Reception", state="OK", error=None)
        group.group_id = MagicMock()
        group.group_id.gateway_id = MagicMock()
        group.group_id.gateway_id.gtin = 12345
        group.group_id.gateway_id.serial = "AABB"
        group.group_id.group_number = 3
        api.list_groups = AsyncMock(return_value=[group])

        result = await fn(site_id="test-site", ctx=ctx)
        assert "Reception" in result
        assert "12345-AABB-3" in result

    @pytest.mark.asyncio
    async def test_gateways_resource(self):
        fn = await _get_resource_fn("ZenControl Site Gateways")
        ctx, api = _make_context()

        gw = MagicMock()
        gw.label = StringField(value="Main GW", state="OK", error=None)
        gw.gateway_id = MagicMock()
        gw.gateway_id.gtin = 999
        gw.gateway_id.serial = "DEAD"
        gw.firmware_version = "2.1.0"
        api.list_gateways = AsyncMock(return_value=[gw])

        result = await fn(site_id="test-site", ctx=ctx)
        assert "Main GW" in result
        assert "999-DEAD" in result
        assert "2.1.0" in result

    @pytest.mark.asyncio
    async def test_scenes_resource(self):
        fn = await _get_resource_fn("ZenControl Site Scenes")
        ctx, api = _make_context()

        scene = Scene(label="Night Mode", sceneNumber=4)
        api.list_scenes = AsyncMock(return_value=[scene])

        result = await fn(site_id="test-site", ctx=ctx)
        assert "Night Mode" in result
        assert "4" in result

    @pytest.mark.asyncio
    async def test_profiles_resource(self):
        fn = await _get_resource_fn("ZenControl Site Profiles")
        ctx, api = _make_context()

        profile = MagicMock()
        profile.label = StringField(value="Work Hours", state="OK", error=None)
        profile.profile_number = IntField(value=1, state="OK", error=None)
        profile.status = StatusField(value="ACTIVE", state="OK", error=None)
        api.list_profiles = AsyncMock(return_value=[profile])

        result = await fn(site_id="test-site", ctx=ctx)
        assert "Work Hours" in result
        assert "1" in result

    @pytest.mark.asyncio
    async def test_api_error_in_sub_resource(self):
        fn = await _get_resource_fn("ZenControl Site Floors")
        ctx, api = _make_context()
        api.list_floors = AsyncMock(side_effect=Exception("Timeout"))

        result = await fn(site_id="test-site", ctx=ctx)
        assert "Error" in result
        assert "Timeout" in result
