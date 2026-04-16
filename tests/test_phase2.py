"""Tests for Phase 2 extended MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from zencontrol_mcp.models.schemas import (
    DaliCommandType,
    DaliId,
    DeviceId,
    DeviceLocation,
    Gateway,
    IntField,
    Profile,
    Scene,
    StatusField,
    StringField,
)
from zencontrol_mcp.scope import ScopeConstraint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_context(api_mock=None, site_id: str = "site-1"):
    """Build a mock MCP Context with api in lifespan_context."""
    if api_mock is None:
        api_mock = MagicMock()
        api_mock.send_command = AsyncMock(return_value=None)
        resolved_site = MagicMock()
        resolved_site.site_id = site_id
        api_mock.resolve_site_identifier = AsyncMock(return_value=resolved_site)
    ctx = MagicMock()
    ctx.lifespan_context = {"api": api_mock, "scope": ScopeConstraint()}
    return ctx, api_mock


async def _get_tool_fn(mcp, name: str):
    """Extract a registered tool function from a FastMCP instance."""
    tool = await mcp._get_tool(name)
    assert tool is not None, f"Tool '{name}' not found"
    return tool.fn


def _register_extended():
    from fastmcp import FastMCP

    from zencontrol_mcp.tools.extended import register

    mcp = FastMCP("test")
    register(mcp)
    return mcp


# ---------------------------------------------------------------------------
# list_gateways
# ---------------------------------------------------------------------------


class TestListGateways:
    async def _call(self, ctx, **kwargs):
        mcp = _register_extended()
        fn = await _get_tool_fn(mcp, "list_gateways")
        return await fn(ctx=ctx, **kwargs)

    async def test_empty(self):
        ctx, api = _make_mock_context()
        api.list_gateways = AsyncMock(return_value=[])
        result = await self._call(ctx, scope_type="site", scope_id="abc")
        assert "No gateways found" in result

    async def test_formatted_output(self):
        gw = Gateway(
            gateway_id=DaliId(gtin=565343546, serial="AABBCCDD"),
            label=StringField(value="Main Gateway"),
            firmware_version="2.1.0",
            mac_address="AA:BB:CC:DD:EE:FF",
        )
        ctx, api = _make_mock_context()
        api.list_gateways = AsyncMock(return_value=[gw])
        result = await self._call(ctx, scope_type="site", scope_id="abc")
        assert "Main Gateway" in result
        assert "565343546-AABBCCDD" in result
        assert "2.1.0" in result
        assert "AA:BB:CC:DD:EE:FF" in result


# ---------------------------------------------------------------------------
# list_device_locations
# ---------------------------------------------------------------------------


class TestListDeviceLocations:
    async def _call(self, ctx, **kwargs):
        mcp = _register_extended()
        fn = await _get_tool_fn(mcp, "list_device_locations")
        return await fn(ctx=ctx, **kwargs)

    async def test_empty(self):
        ctx, api = _make_mock_context()
        api.list_device_locations = AsyncMock(return_value=[])
        result = await self._call(ctx, scope_type="site", scope_id="abc")
        assert "No device locations found" in result

    async def test_formatted_output(self):
        loc = DeviceLocation(
            device_location_id="loc-1",
            label=StringField(value="Hallway Fixture"),
            status=StatusField(value="ACTIVE"),
            device_id=DeviceId(
                gateway_id=DaliId(gtin=565343546, serial="AABBCCDD"),
                bus_unit_id=DaliId(gtin=12345678, serial="11223344"),
            ),
        )
        ctx, api = _make_mock_context()
        api.list_device_locations = AsyncMock(return_value=[loc])
        result = await self._call(ctx, scope_type="site", scope_id="abc")
        assert "Hallway Fixture" in result
        assert "loc-1" in result
        assert "ACTIVE" in result
        assert "565343546-AABBCCDD-12345678-11223344" in result


# ---------------------------------------------------------------------------
# list_scenes
# ---------------------------------------------------------------------------


class TestListScenes:
    async def _call(self, ctx, **kwargs):
        mcp = _register_extended()
        fn = await _get_tool_fn(mcp, "list_scenes")
        return await fn(ctx=ctx, **kwargs)

    async def test_empty(self):
        ctx, api = _make_mock_context()
        api.list_scenes = AsyncMock(return_value=[])
        result = await self._call(ctx, site_id="abc")
        assert "No scenes found" in result

    async def test_formatted_output(self):
        scenes = [
            Scene(label="Meeting Room", scene_number=3),
            Scene(label="Lobby", scene_number=7),
        ]
        ctx, api = _make_mock_context()
        api.list_scenes = AsyncMock(return_value=scenes)
        result = await self._call(ctx, site_id="abc")
        assert "Meeting Room" in result
        assert "scene number: 3" in result
        assert "Lobby" in result
        assert "scene number: 7" in result
        assert "2 scene(s)" in result


# ---------------------------------------------------------------------------
# list_profiles
# ---------------------------------------------------------------------------


class TestListProfiles:
    async def _call(self, ctx, **kwargs):
        mcp = _register_extended()
        fn = await _get_tool_fn(mcp, "list_profiles")
        return await fn(ctx=ctx, **kwargs)

    async def test_empty(self):
        ctx, api = _make_mock_context()
        api.list_profiles = AsyncMock(return_value=[])
        result = await self._call(ctx, site_id="abc")
        assert "No profiles found" in result

    async def test_formatted_output(self):
        profiles = [
            Profile(
                label=StringField(value="Work hours"),
                profile_number=IntField(value=1),
                status=StatusField(value="ACTIVE"),
            ),
        ]
        ctx, api = _make_mock_context()
        api.list_profiles = AsyncMock(return_value=profiles)
        result = await self._call(ctx, site_id="abc")
        assert "Work hours" in result
        assert "number: 1" in result
        assert "ACTIVE" in result


# ---------------------------------------------------------------------------
# set_profile
# ---------------------------------------------------------------------------


class TestSetProfile:
    async def _call(self, ctx, **kwargs):
        mcp = _register_extended()
        fn = await _get_tool_fn(mcp, "set_profile")
        return await fn(ctx=ctx, **kwargs)

    async def test_sends_correct_command(self):
        ctx, api = _make_mock_context()
        result = await self._call(
            ctx,
            target_type="group",
            target_id="1-A-5",
            profile_number=42,
        )
        assert "Successfully" in result
        api.send_command.assert_called_once()
        cmd = api.send_command.call_args[0][2]
        assert cmd.type == DaliCommandType.GO_TO_PROFILE
        assert cmd.profile_number == 42

    async def test_profile_number_zero(self):
        ctx, api = _make_mock_context()
        result = await self._call(
            ctx,
            target_type="site",
            target_id="some-id",
            profile_number=0,
        )
        assert "Successfully" in result
        cmd = api.send_command.call_args[0][2]
        assert cmd.profile_number == 0

    async def test_profile_number_max(self):
        ctx, api = _make_mock_context()
        result = await self._call(
            ctx,
            target_type="site",
            target_id="some-id",
            profile_number=65535,
        )
        assert "Successfully" in result
        cmd = api.send_command.call_args[0][2]
        assert cmd.profile_number == 65535

    async def test_profile_number_too_high(self):
        ctx, api = _make_mock_context()
        result = await self._call(
            ctx,
            target_type="site",
            target_id="some-id",
            profile_number=65536,
        )
        assert "between 0 and 65535" in result
        api.send_command.assert_not_called()

    async def test_profile_number_negative(self):
        ctx, api = _make_mock_context()
        result = await self._call(
            ctx,
            target_type="site",
            target_id="some-id",
            profile_number=-1,
        )
        assert "between 0 and 65535" in result
        api.send_command.assert_not_called()
