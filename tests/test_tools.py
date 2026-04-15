"""Tests for MCP tool functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


from zencontrol_mcp.models.schemas import DaliCommandType
from zencontrol_mcp.tools.control import _ACTION_MAP, _pct_to_dali


# ---------------------------------------------------------------------------
# Helper to build a mock context with a mock API
# ---------------------------------------------------------------------------


def _make_mock_context(api_mock=None):
    """Build a mock MCP Context with api in lifespan_context."""
    if api_mock is None:
        api_mock = MagicMock()
        api_mock.send_command = AsyncMock(return_value=None)
        api_mock.list_sites = AsyncMock(return_value=[])
        api_mock.list_groups = AsyncMock(return_value=[])
        api_mock.list_devices = AsyncMock(return_value=[])
    ctx = MagicMock()
    ctx.lifespan_context = {"api": api_mock}
    return ctx, api_mock


async def _get_tool_fn(mcp, name: str):
    """Extract a registered tool function from a FastMCP instance."""
    tool = await mcp._get_tool(name)
    assert tool is not None, f"Tool '{name}' not found"
    return tool.fn


# ---------------------------------------------------------------------------
# Level conversion: _pct_to_dali
# ---------------------------------------------------------------------------


class TestPctToDali:
    def test_zero_percent(self):
        assert _pct_to_dali(0) == 0

    def test_fifty_percent(self):
        assert _pct_to_dali(50) == 127

    def test_hundred_percent(self):
        assert _pct_to_dali(100) == 254

    def test_one_percent(self):
        # 1 * 254 / 100 = 2.54 → rounds to 3
        assert _pct_to_dali(1) == 3

    def test_seventy_five_percent(self):
        # 75 * 254 / 100 = 190.5 → rounds to 190
        assert _pct_to_dali(75) == 190


# ---------------------------------------------------------------------------
# Action → DaliCommandType mapping
# ---------------------------------------------------------------------------


class TestActionMap:
    def test_off_maps_to_off(self):
        assert _ACTION_MAP["off"] == DaliCommandType.OFF

    def test_on_maps_to_recall_max(self):
        assert _ACTION_MAP["on"] == DaliCommandType.RECALL_MAX

    def test_set_level_maps_correctly(self):
        assert _ACTION_MAP["set_level"] == DaliCommandType.SET_LEVEL

    def test_recall_scene_maps_correctly(self):
        assert _ACTION_MAP["recall_scene"] == DaliCommandType.GO_TO_SCENE

    def test_dim_up_maps_correctly(self):
        assert _ACTION_MAP["dim_up"] == DaliCommandType.DIM_UP

    def test_dim_down_maps_correctly(self):
        assert _ACTION_MAP["dim_down"] == DaliCommandType.DIM_DOWN

    def test_identify_maps_correctly(self):
        assert _ACTION_MAP["identify"] == DaliCommandType.IDENTIFY


# ---------------------------------------------------------------------------
# control_light tool
# ---------------------------------------------------------------------------


class TestControlLight:
    """Test the control_light tool function by importing and calling it directly."""

    async def _call_control_light(self, ctx, **kwargs):
        """Import and call the control_light tool registered on a temporary FastMCP."""
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.control import register

        mcp = FastMCP("test")
        register(mcp)
        tool_fn = await _get_tool_fn(mcp, "control_light")
        return await tool_fn(ctx=ctx, **kwargs)

    async def test_set_level_sends_correct_dali_level(self):
        ctx, api = _make_mock_context()
        result = await self._call_control_light(
            ctx,
            target_type="group",
            target_id="565343546-AABBCCDD-5",
            action="set_level",
            level=50,
        )
        assert "Successfully" in result
        api.send_command.assert_called_once()
        cmd = api.send_command.call_args[0][2]
        assert cmd.level == 127  # 50% → DALI 127

    async def test_set_level_zero(self):
        ctx, api = _make_mock_context()
        await self._call_control_light(
            ctx,
            target_type="device",
            target_id="1-A-2-B",
            action="set_level",
            level=0,
        )
        cmd = api.send_command.call_args[0][2]
        assert cmd.level == 0

    async def test_set_level_hundred(self):
        ctx, api = _make_mock_context()
        await self._call_control_light(
            ctx,
            target_type="device",
            target_id="1-A-2-B",
            action="set_level",
            level=100,
        )
        cmd = api.send_command.call_args[0][2]
        assert cmd.level == 254

    async def test_set_level_without_level_returns_error(self):
        ctx, api = _make_mock_context()
        result = await self._call_control_light(
            ctx,
            target_type="group",
            target_id="1-A-5",
            action="set_level",
            level=None,
        )
        assert "required" in result.lower()
        api.send_command.assert_not_called()

    async def test_recall_scene_without_scene_returns_error(self):
        ctx, api = _make_mock_context()
        result = await self._call_control_light(
            ctx,
            target_type="group",
            target_id="1-A-5",
            action="recall_scene",
            scene=None,
        )
        assert "required" in result.lower()
        api.send_command.assert_not_called()

    async def test_recall_scene_sends_scene_number(self):
        ctx, api = _make_mock_context()
        result = await self._call_control_light(
            ctx,
            target_type="group",
            target_id="1-A-5",
            action="recall_scene",
            scene=7,
        )
        assert "Successfully" in result
        cmd = api.send_command.call_args[0][2]
        assert cmd.scene == 7
        assert cmd.type == DaliCommandType.GO_TO_SCENE

    async def test_off_action(self):
        ctx, api = _make_mock_context()
        result = await self._call_control_light(
            ctx,
            target_type="zone",
            target_id="site-zone",
            action="off",
        )
        assert "Successfully" in result
        cmd = api.send_command.call_args[0][2]
        assert cmd.type == DaliCommandType.OFF

    async def test_on_action(self):
        ctx, api = _make_mock_context()
        result = await self._call_control_light(
            ctx,
            target_type="zone",
            target_id="site-zone",
            action="on",
        )
        assert "Successfully" in result
        cmd = api.send_command.call_args[0][2]
        assert cmd.type == DaliCommandType.RECALL_MAX

    async def test_unknown_action(self):
        ctx, api = _make_mock_context()
        result = await self._call_control_light(
            ctx,
            target_type="group",
            target_id="1-A-5",
            action="explode",
        )
        assert "Unknown action" in result
        api.send_command.assert_not_called()

    async def test_invalid_level_range(self):
        ctx, api = _make_mock_context()
        result = await self._call_control_light(
            ctx,
            target_type="group",
            target_id="1-A-5",
            action="set_level",
            level=150,
        )
        assert "between 0 and 100" in result
        api.send_command.assert_not_called()


# ---------------------------------------------------------------------------
# set_colour tool
# ---------------------------------------------------------------------------


class TestSetColour:
    async def _call_set_colour(self, ctx, **kwargs):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.control import register

        mcp = FastMCP("test")
        register(mcp)
        tool_fn = await _get_tool_fn(mcp, "set_colour")
        return await tool_fn(ctx=ctx, **kwargs)

    async def test_kelvin_to_mirek_conversion(self):
        """4000K → 1000000/4000 = 250 mirek."""
        ctx, api = _make_mock_context()
        result = await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="temperature",
            kelvin=4000,
        )
        assert "Successfully" in result
        cmd = api.send_command.call_args[0][2]
        assert cmd.temperature == 250
        assert cmd.type == DaliCommandType.COLOUR_TEMPERATURE

    async def test_kelvin_2700(self):
        """2700K → 1000000/2700 ≈ 370 mirek."""
        ctx, api = _make_mock_context()
        await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="temperature",
            kelvin=2700,
        )
        cmd = api.send_command.call_args[0][2]
        assert cmd.temperature == round(1_000_000 / 2700)

    async def test_kelvin_6500(self):
        """6500K → 1000000/6500 ≈ 154 mirek."""
        ctx, api = _make_mock_context()
        await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="temperature",
            kelvin=6500,
        )
        cmd = api.send_command.call_args[0][2]
        assert cmd.temperature == round(1_000_000 / 6500)

    async def test_temperature_mode_requires_kelvin(self):
        ctx, api = _make_mock_context()
        result = await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="temperature",
        )
        assert "kelvin" in result.lower()
        api.send_command.assert_not_called()

    async def test_rgbwaf_none_becomes_255(self):
        """Unset channels should use 255 as no-change sentinel."""
        ctx, api = _make_mock_context()
        result = await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="rgbwaf",
            red=100,
            green=150,
            blue=200,
        )
        assert "Successfully" in result
        cmd = api.send_command.call_args[0][2]
        assert cmd.rgbwaf == [100, 150, 200, 255, 255, 255]
        assert cmd.control == 255

    async def test_rgbwaf_all_specified(self):
        ctx, api = _make_mock_context()
        await self._call_set_colour(
            ctx,
            target_type="ecg",
            target_id="1-A-2-B-0",
            mode="rgbwaf",
            red=10,
            green=20,
            blue=30,
            white=40,
            amber=50,
            freecolour=60,
        )
        cmd = api.send_command.call_args[0][2]
        assert cmd.rgbwaf == [10, 20, 30, 40, 50, 60]

    async def test_rgbwaf_with_level(self):
        """Level should be converted to DALI and included."""
        ctx, api = _make_mock_context()
        await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="rgbwaf",
            red=100,
            level=50,
        )
        cmd = api.send_command.call_args[0][2]
        assert cmd.level == 127  # 50% → 127

    async def test_temperature_with_level(self):
        ctx, api = _make_mock_context()
        await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="temperature",
            kelvin=4000,
            level=75,
        )
        cmd = api.send_command.call_args[0][2]
        assert cmd.level == 190  # 75% → round(75*254/100)

    async def test_invalid_mode(self):
        ctx, api = _make_mock_context()
        result = await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="hsv",
        )
        assert "temperature" in result or "rgbwaf" in result
        api.send_command.assert_not_called()

    async def test_invalid_level_range(self):
        ctx, api = _make_mock_context()
        result = await self._call_set_colour(
            ctx,
            target_type="group",
            target_id="1-A-5",
            mode="temperature",
            kelvin=4000,
            level=200,
        )
        assert "between 0 and 100" in result
        api.send_command.assert_not_called()


# ---------------------------------------------------------------------------
# list_sites tool
# ---------------------------------------------------------------------------


class TestListSites:
    async def _call_list_sites(self, ctx):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.sites import register

        mcp = FastMCP("test")
        register(mcp)
        tool_fn = await _get_tool_fn(mcp, "list_sites")
        return await tool_fn(ctx=ctx)

    async def test_list_sites_empty(self):
        ctx, api = _make_mock_context()
        api.list_sites = AsyncMock(return_value=[])
        result = await self._call_list_sites(ctx)
        assert "No sites found" in result

    async def test_list_sites_with_data(self, sample_site):
        from zencontrol_mcp.models.schemas import Site

        site = Site.model_validate(sample_site)
        ctx, api = _make_mock_context()
        api.list_sites = AsyncMock(return_value=[site])
        result = await self._call_list_sites(ctx)
        assert "HQ Office" in result
        assert "3b5b2c02-0e43-423f-9719-758ab3fcb456" in result
        assert "hq" in result
        assert "Brisbane" in result


# ---------------------------------------------------------------------------
# list_groups tool
# ---------------------------------------------------------------------------


class TestListGroups:
    async def _call_list_groups(self, ctx, **kwargs):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.devices import register

        mcp = FastMCP("test")
        register(mcp)
        tool_fn = await _get_tool_fn(mcp, "list_groups")
        return await tool_fn(ctx=ctx, **kwargs)

    async def test_list_groups_empty(self):
        ctx, api = _make_mock_context()
        api.list_groups = AsyncMock(return_value=[])
        result = await self._call_list_groups(
            ctx, scope_type="site", scope_id="some-id"
        )
        assert "No groups found" in result

    async def test_list_groups_with_data(self, sample_group):
        from zencontrol_mcp.models.schemas import Group

        group = Group.model_validate(sample_group)
        ctx, api = _make_mock_context()
        api.list_groups = AsyncMock(return_value=[group])
        result = await self._call_list_groups(
            ctx, scope_type="site", scope_id="some-id"
        )
        assert "Office 3.02" in result
        assert "565343546-AABBCCDD-5" in result
