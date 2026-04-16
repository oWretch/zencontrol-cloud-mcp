"""Tests for Live API client and MCP tools."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zencontrol_mcp.api.live import LiveAPIError, LiveClient
from zencontrol_mcp.scope import ScopeConstraint
from zencontrol_mcp.tools.live import _validate_duration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_live_context(live_client: LiveClient, site_id: str = "site-1"):
    """Build a mock MCP Context with a LiveClient in lifespan_context."""
    api_mock = MagicMock()
    resolved_site = MagicMock()
    resolved_site.site_id = site_id
    api_mock.resolve_site_identifier = AsyncMock(return_value=resolved_site)
    ctx = MagicMock()
    ctx.lifespan_context = {
        "api": api_mock,
        "live": live_client,
        "scope": ScopeConstraint(),
    }
    return ctx


async def _get_tool_fn(mcp, name: str):
    """Extract a registered tool function from a FastMCP instance."""
    tool = await mcp._get_tool(name)
    assert tool is not None, f"Tool '{name}' not found"
    return tool.fn


def _make_ws_message(msg_type: str, msg_id: int = 1, **extra) -> str:
    """Build a JSON Live API message."""
    msg: dict = {"version": "1.0", "type": msg_type, "id": msg_id, **extra}
    return json.dumps(msg)


# ---------------------------------------------------------------------------
# Duration validation
# ---------------------------------------------------------------------------


class TestValidateDuration:
    def test_valid_durations(self):
        assert _validate_duration(1) is None
        assert _validate_duration(5) is None
        assert _validate_duration(30) is None

    def test_zero_duration(self):
        assert _validate_duration(0) is not None

    def test_negative_duration(self):
        assert _validate_duration(-1) is not None

    def test_over_max_duration(self):
        assert _validate_duration(31) is not None


# ---------------------------------------------------------------------------
# LiveClient.subscribe_once
# ---------------------------------------------------------------------------


class TestLiveClientSubscribeOnce:
    @staticmethod
    def _make_recv(messages: list[str]):
        """Create an async recv function that returns messages then blocks."""
        idx = 0

        async def _recv():
            nonlocal idx
            if idx < len(messages):
                msg = messages[idx]
                idx += 1
                return msg
            # Block forever (simulates no more data); timeout will break out
            await asyncio.sleep(100)
            return ""  # pragma: no cover

        return _recv

    async def test_sends_correct_subscribe_message(self):
        token_factory = AsyncMock(return_value="test-token")
        client = LiveClient(token_factory=token_factory)

        mock_ws = AsyncMock()
        mock_ws.recv = self._make_recv(
            [
                _make_ws_message("START"),
                _make_ws_message("END"),
            ]
        )
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch("zencontrol_mcp.api.live.websockets.connect", return_value=mock_ws):
            await client.subscribe_once(
                method="event.group.arc-level",
                content={"siteId": "site-123"},
                duration=0.1,
            )

        sent_calls = mock_ws.send.call_args_list
        assert len(sent_calls) >= 1
        subscribe_msg = json.loads(sent_calls[0][0][0])
        assert subscribe_msg["type"] == "SUBSCRIBE"
        assert subscribe_msg["method"] == "event.group.arc-level"
        assert subscribe_msg["content"] == {"siteId": "site-123"}
        assert subscribe_msg["version"] == "1.0"
        assert subscribe_msg["id"] == 1

    async def test_collects_events(self):
        token_factory = AsyncMock(return_value="test-token")
        client = LiveClient(token_factory=token_factory)

        event_content = {
            "gatewayId": {"gtin": 123, "serial": "ABC"},
            "groups": [{"id": {"groupNumber": 5}, "value": 200}],
        }

        mock_ws = AsyncMock()
        mock_ws.recv = self._make_recv(
            [
                _make_ws_message("START"),
                _make_ws_message("EVENT", content=event_content),
                _make_ws_message("END"),
            ]
        )
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch("zencontrol_mcp.api.live.websockets.connect", return_value=mock_ws):
            events = await client.subscribe_once(
                method="event.group.arc-level",
                content={"siteId": "site-123"},
                duration=0.1,
            )

        assert len(events) == 1
        assert events[0] == event_content

    async def test_uses_token_in_url(self):
        token_factory = AsyncMock(return_value="my-secret-token")
        client = LiveClient(token_factory=token_factory)

        mock_ws = AsyncMock()
        mock_ws.recv = self._make_recv(
            [
                _make_ws_message("START"),
                _make_ws_message("END"),
            ]
        )
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "zencontrol_mcp.api.live.websockets.connect", return_value=mock_ws
        ) as mock_connect:
            await client.subscribe_once(
                method="event.ecg.arc-level",
                content={"siteId": "s"},
                duration=0.1,
            )

        call_url = mock_connect.call_args[0][0]
        assert "accessToken=my-secret-token" in call_url

    async def test_raises_on_error_during_start(self):
        token_factory = AsyncMock(return_value="test-token")
        client = LiveClient(token_factory=token_factory)

        error_msg = _make_ws_message(
            "ERROR",
            error={"code": "FORBIDDEN", "message": "Forbidden"},
        )

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=error_msg)
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch("zencontrol_mcp.api.live.websockets.connect", return_value=mock_ws):
            with pytest.raises(LiveAPIError, match="Forbidden") as exc_info:
                await client.subscribe_once(
                    method="event.ecg.arc-level",
                    content={"siteId": "s"},
                    duration=0.1,
                )
        assert exc_info.value.code == "FORBIDDEN"
        assert exc_info.value.is_access_error

    async def test_raises_on_error_during_event_collection(self):
        token_factory = AsyncMock(return_value="test-token")
        client = LiveClient(token_factory=token_factory)

        stream_error_msg = _make_ws_message(
            "ERROR",
            error={"code": "STREAM_ERROR", "message": "Stream interrupted"},
        )

        mock_ws = AsyncMock()
        mock_ws.recv = self._make_recv([_make_ws_message("START"), stream_error_msg])
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch("zencontrol_mcp.api.live.websockets.connect", return_value=mock_ws):
            with pytest.raises(LiveAPIError, match="Stream interrupted") as exc_info:
                await client.subscribe_once(
                    method="event.group.arc-level",
                    content={"siteId": "s"},
                    duration=30.0,
                )
        assert exc_info.value.code == "STREAM_ERROR"
        assert not exc_info.value.is_access_error

    async def test_stops_on_end_message(self):
        token_factory = AsyncMock(return_value="test-token")
        client = LiveClient(token_factory=token_factory)

        event_content = {"gatewayId": {"gtin": 1, "serial": "A"}, "groups": []}

        mock_ws = AsyncMock()
        mock_ws.recv = self._make_recv(
            [
                _make_ws_message("START"),
                _make_ws_message("EVENT", content=event_content),
                _make_ws_message("END"),
                _make_ws_message("END"),
            ]
        )
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch("zencontrol_mcp.api.live.websockets.connect", return_value=mock_ws):
            events = await client.subscribe_once(
                method="event.group.arc-level",
                content={"siteId": "s"},
                duration=30.0,
            )

        assert len(events) == 1

    async def test_sends_unsubscribe(self):
        token_factory = AsyncMock(return_value="test-token")
        client = LiveClient(token_factory=token_factory)

        mock_ws = AsyncMock()
        mock_ws.recv = self._make_recv(
            [
                _make_ws_message("START"),
                _make_ws_message("END"),
            ]
        )
        mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch("zencontrol_mcp.api.live.websockets.connect", return_value=mock_ws):
            await client.subscribe_once(
                method="event.ecg.arc-level",
                content={"siteId": "s"},
                duration=0.1,
            )

        sent_calls = mock_ws.send.call_args_list
        assert len(sent_calls) == 2
        unsub_msg = json.loads(sent_calls[1][0][0])
        assert unsub_msg["type"] == "UNSUBSCRIBE"
        assert unsub_msg["id"] == 1


# ---------------------------------------------------------------------------
# get_live_light_levels tool
# ---------------------------------------------------------------------------


class TestGetLiveLightLevels:
    async def _call(self, ctx, **kwargs):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.live import register

        mcp = FastMCP("test")
        register(mcp)
        tool_fn = await _get_tool_fn(mcp, "get_live_light_levels")
        return await tool_fn(ctx=ctx, **kwargs)

    async def test_formats_group_levels(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(
            return_value=[
                {
                    "gatewayId": {"gtin": 565343546, "serial": "AABBCCDD"},
                    "groups": [
                        {"id": {"groupNumber": 5}, "value": 254},
                        {"id": {"groupNumber": 10}, "value": 127},
                    ],
                }
            ]
        )
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", target="groups")
        assert "565343546-AABBCCDD group 5: 100%" in result
        assert "565343546-AABBCCDD group 10: 50%" in result

    async def test_formats_ecg_levels(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(
            return_value=[
                {
                    "gatewayId": {"gtin": 100, "serial": "XYZ"},
                    "ecgs": [
                        {
                            "id": {
                                "busUnitGtin": 200,
                                "busUnitSerial": "DEF",
                                "logicalIndex": 0,
                            },
                            "value": 0,
                        }
                    ],
                }
            ]
        )
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", target="ecgs")
        assert "100-XYZ ecg 200-DEF-0: 0%" in result

    async def test_no_events(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(return_value=[])
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1")
        assert "No groups light-level events" in result

    async def test_invalid_duration(self):
        live = MagicMock(spec=LiveClient)
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", duration=0)
        assert "between 1 and 30" in result
        live.subscribe_once.assert_not_called()

    async def test_invalid_target(self):
        live = MagicMock(spec=LiveClient)
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", target="zones")
        assert "groups" in result and "ecgs" in result
        live.subscribe_once.assert_not_called()


# ---------------------------------------------------------------------------
# get_sensor_readings tool
# ---------------------------------------------------------------------------


class TestGetSensorReadings:
    async def _call(self, ctx, **kwargs):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.live import register

        mcp = FastMCP("test")
        register(mcp)
        tool_fn = await _get_tool_fn(mcp, "get_sensor_readings")
        return await tool_fn(ctx=ctx, **kwargs)

    async def test_light_sensor_readings(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(
            return_value=[
                {
                    "gatewayId": {"gtin": 100, "serial": "GW1"},
                    "lightSensors": [
                        {
                            "id": {
                                "busUnitGtin": 200,
                                "busUnitSerial": "S1",
                                "logicalIndex": 0,
                                "instanceNumber": 1,
                            },
                            "value": 450,
                            "isCalibrated": True,
                        }
                    ],
                }
            ]
        )
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", sensor_type="light")
        assert "450 lx" in result
        assert "calibrated: True" in result

    async def test_occupancy_sensor_movement(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(
            return_value=[
                {
                    "gatewayId": {"gtin": 100, "serial": "GW1"},
                    "occupancySensors": [
                        {
                            "id": {
                                "busUnitGtin": 300,
                                "busUnitSerial": "OC1",
                                "logicalIndex": 0,
                                "instanceNumber": 1,
                            },
                            "value": 1,
                        }
                    ],
                }
            ]
        )
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", sensor_type="occupancy")
        assert "movement detected" in result

    async def test_occupancy_sensor_no_movement(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(
            return_value=[
                {
                    "gatewayId": {"gtin": 100, "serial": "GW1"},
                    "occupancySensors": [
                        {
                            "id": {
                                "busUnitGtin": 300,
                                "busUnitSerial": "OC1",
                                "logicalIndex": 0,
                                "instanceNumber": 1,
                            },
                            "value": 0,
                        }
                    ],
                }
            ]
        )
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", sensor_type="occupancy")
        assert "no movement" in result

    async def test_invalid_sensor_type(self):
        live = MagicMock(spec=LiveClient)
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", sensor_type="temperature")
        assert "light" in result and "occupancy" in result
        live.subscribe_once.assert_not_called()

    async def test_invalid_duration(self):
        live = MagicMock(spec=LiveClient)
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", duration=31)
        assert "between 1 and 30" in result
        live.subscribe_once.assert_not_called()


# ---------------------------------------------------------------------------
# get_system_variables tool
# ---------------------------------------------------------------------------


class TestGetSystemVariables:
    async def _call(self, ctx, **kwargs):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.live import register

        mcp = FastMCP("test")
        register(mcp)
        tool_fn = await _get_tool_fn(mcp, "get_system_variables")
        return await tool_fn(ctx=ctx, **kwargs)

    async def test_formats_system_variables(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(
            return_value=[
                {
                    "gatewayId": {"gtin": 100, "serial": "GW1"},
                    "systemVariables": [
                        {"id": {"index": 3}, "signedValue": 5, "magnitude": 127},
                        {"id": {"index": 7}, "signedValue": -2, "magnitude": 129},
                    ],
                }
            ]
        )
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1")
        # 5 * 10^(127-127) = 5 * 1 = 5
        assert "variable 3: 5" in result
        # -2 * 10^(129-127) = -2 * 100 = -200
        assert "variable 7: -200" in result

    async def test_no_events(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(return_value=[])
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1")
        assert "No system variable events" in result

    async def test_invalid_duration(self):
        live = MagicMock(spec=LiveClient)
        ctx = _make_live_context(live)

        result = await self._call(ctx, site_id="site-1", duration=-5)
        assert "between 1 and 30" in result
        live.subscribe_once.assert_not_called()


# ---------------------------------------------------------------------------
# LiveAPIError handling in tools
# ---------------------------------------------------------------------------


class TestLiveAPIErrorHandling:
    """Test that live tools surface LiveAPIError correctly."""

    @staticmethod
    async def _call_tool(tool_name: str, ctx, **kwargs):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.live import register

        mcp = FastMCP("test")
        register(mcp)
        tool_fn = await _get_tool_fn(mcp, tool_name)
        return await tool_fn(ctx=ctx, **kwargs)

    @pytest.mark.asyncio
    async def test_access_error_surfaces_helpful_message(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(
            side_effect=LiveAPIError("UNAUTHORIZED: no access", code="UNAUTHORIZED")
        )
        ctx = _make_live_context(live)

        result = await self._call_tool("get_live_light_levels", ctx, site_id="site-1")
        assert "access denied" in result.lower()
        assert "ZenControl support" in result

    @pytest.mark.asyncio
    async def test_stream_error_surfaces_message(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(
            side_effect=LiveAPIError("STREAM_ERROR: bad thing", code="STREAM_ERROR")
        )
        ctx = _make_live_context(live)

        result = await self._call_tool("get_sensor_readings", ctx, site_id="site-1")
        assert "Live API error" in result
        assert "bad thing" in result

    @pytest.mark.asyncio
    async def test_site_tag_resolves_for_live_tool(self):
        live = MagicMock(spec=LiveClient)
        live.subscribe_once = AsyncMock(return_value=[])

        api_mock = MagicMock()
        resolved = MagicMock()
        resolved.site_id = "real-uuid-123"
        api_mock.resolve_site_identifier = AsyncMock(return_value=resolved)

        ctx = MagicMock()
        ctx.lifespan_context = {
            "api": api_mock,
            "live": live,
            "scope": ScopeConstraint(),
        }

        await self._call_tool("get_system_variables", ctx, site_id="my-site-tag")
        api_mock.resolve_site_identifier.assert_called_once_with("my-site-tag")
        live.subscribe_once.assert_called_once()
        call_kwargs = live.subscribe_once.call_args
        assert call_kwargs.kwargs["content"]["siteId"] == "real-uuid-123"
