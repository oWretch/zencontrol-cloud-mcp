"""Tests for ZenControlAPI — URL construction, response parsing, and commands."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from zencontrol_mcp.api.client import ZenControlClient
from zencontrol_mcp.api.rest import ZenControlAPI


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    """ZenControlClient + ZenControlAPI backed by a real (mocked) httpx transport."""
    factory = AsyncMock(return_value="test-token")
    client = ZenControlClient(token_factory=factory, cache_ttl=0)
    return ZenControlAPI(client)


async def _cleanup(api_client: ZenControlAPI) -> None:
    await api_client.client.close()


SITE_PAYLOAD = {
    "siteId": "3b5b2c02-0e43-423f-9719-758ab3fcb456",
    "tag": "hq",
    "name": "HQ Office",
}

GROUP_PAYLOAD = {
    "groupId": {
        "gatewayId": {"gtin": 565343546, "serial": "AABBCCDD"},
        "groupNumber": 5,
    },
    "label": {"value": "Office 3.02", "state": "OK", "error": None},
    "type": {"value": "STANDARD", "state": "OK", "error": None},
    "status": {"value": "ACTIVE", "state": "OK", "error": None},
}

GROUP_WITH_PERMISSIONS = {
    **GROUP_PAYLOAD,
    "permissions": {
        "group": {
            "lighting": {"read": True, "write": True},
        }
    },
}

GROUP_VIEW_ONLY = {
    **GROUP_PAYLOAD,
    "permissions": {
        "group": {
            "lighting": {"read": True},
        }
    },
}


# ---------------------------------------------------------------------------
# list_sites
# ---------------------------------------------------------------------------


class TestListSites:
    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_validated_site_models(self, api_client):
        respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json={"sites": [SITE_PAYLOAD]})
        )

        sites = await api_client.list_sites()
        assert len(sites) == 1
        assert sites[0].tag == "hq"
        assert sites[0].site_id == "3b5b2c02-0e43-423f-9719-758ab3fcb456"
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_permission_group_param_passed(self, api_client):
        route = respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json={"sites": [SITE_PAYLOAD]})
        )

        await api_client.list_sites(permission_group="ALL")

        request = route.calls.last.request
        assert b"permissionGroup=ALL" in request.url.query
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_permission_group_param_by_default(self, api_client):
        route = respx.get("https://api.zencontrol.com/v2/sites").mock(
            return_value=httpx.Response(200, json={"sites": [SITE_PAYLOAD]})
        )

        await api_client.list_sites()

        request = route.calls.last.request
        assert b"permissionGroup" not in request.url.query
        await _cleanup(api_client)


# ---------------------------------------------------------------------------
# list_groups — URL construction for each scope type
# ---------------------------------------------------------------------------


class TestListGroupsUrlConstruction:
    @pytest.mark.asyncio
    @respx.mock
    async def test_site_scope(self, api_client):
        route = respx.get("https://api.zencontrol.com/v2/sites/site-abc/groups").mock(
            return_value=httpx.Response(200, json={"groups": [GROUP_PAYLOAD]})
        )

        groups = await api_client.list_groups("site", "site-abc")

        assert len(groups) == 1
        assert route.called
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_floor_scope(self, api_client):
        route = respx.get("https://api.zencontrol.com/v2/floors/floor-xyz/groups").mock(
            return_value=httpx.Response(200, json={"groups": []})
        )

        await api_client.list_groups("floor", "floor-xyz")
        assert route.called
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_gateway_scope(self, api_client):
        route = respx.get(
            "https://api.zencontrol.com/v2/gateways/gtin-serial/groups"
        ).mock(return_value=httpx.Response(200, json={"groups": []}))

        await api_client.list_groups("gateway", "gtin-serial")
        assert route.called
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_permission_group_all_param_included(self, api_client):
        route = respx.get("https://api.zencontrol.com/v2/sites/site-abc/groups").mock(
            return_value=httpx.Response(200, json={"groups": [GROUP_WITH_PERMISSIONS]})
        )

        groups = await api_client.list_groups(
            "site", "site-abc", permission_group="ALL"
        )

        request = route.calls.last.request
        assert b"permissionGroup=ALL" in request.url.query
        assert groups[0].permissions is not None
        assert groups[0].permissions.group is not None
        assert groups[0].permissions.group.lighting is not None
        assert groups[0].permissions.group.lighting.write is True
        await _cleanup(api_client)

    @pytest.mark.asyncio
    async def test_invalid_scope_type_raises(self, api_client):
        with pytest.raises(ValueError, match="Unknown scope type"):
            await api_client.list_groups("invalid", "some-id")
        await _cleanup(api_client)


# ---------------------------------------------------------------------------
# Permission model parsing
# ---------------------------------------------------------------------------


class TestPermissionModels:
    @pytest.mark.asyncio
    @respx.mock
    async def test_write_permission_parsed(self, api_client):
        respx.get("https://api.zencontrol.com/v2/sites/s/groups").mock(
            return_value=httpx.Response(200, json={"groups": [GROUP_WITH_PERMISSIONS]})
        )

        groups = await api_client.list_groups("site", "s", permission_group="ALL")
        perm = groups[0].permissions
        assert perm is not None
        assert perm.group.lighting.write is True
        assert perm.group.lighting.read is True
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_view_only_permission_parsed(self, api_client):
        respx.get("https://api.zencontrol.com/v2/sites/s/groups").mock(
            return_value=httpx.Response(200, json={"groups": [GROUP_VIEW_ONLY]})
        )

        groups = await api_client.list_groups("site", "s", permission_group="ALL")
        perm = groups[0].permissions
        assert perm.group.lighting.read is True
        assert perm.group.lighting.write is None  # absent = not granted
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_permissions_when_param_not_passed(self, api_client):
        respx.get("https://api.zencontrol.com/v2/sites/s/groups").mock(
            return_value=httpx.Response(200, json={"groups": [GROUP_PAYLOAD]})
        )

        groups = await api_client.list_groups("site", "s")
        assert groups[0].permissions is None
        await _cleanup(api_client)


# ---------------------------------------------------------------------------
# send_command — body serialisation
# ---------------------------------------------------------------------------


class TestSendCommand:
    @pytest.mark.asyncio
    @respx.mock
    async def test_off_command_body(self, api_client):
        from zencontrol_mcp.models.schemas import DaliCommand, DaliCommandType

        route = respx.post(
            "https://api.zencontrol.com/v1/groups/gtin-serial-5/command"
        ).mock(return_value=httpx.Response(200, json={}))

        cmd = DaliCommand(type=DaliCommandType.OFF)
        await api_client.send_command("group", "gtin-serial-5", cmd)

        request = route.calls.last.request
        body = request.read()
        import json

        parsed = json.loads(body)
        assert parsed["type"] == "off"
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_set_level_command_body(self, api_client):
        from zencontrol_mcp.models.schemas import DaliCommand, DaliCommandType

        route = respx.post("https://api.zencontrol.com/v1/groups/g-id/command").mock(
            return_value=httpx.Response(200, json={})
        )

        cmd = DaliCommand(type=DaliCommandType.SET_LEVEL, level=200)
        await api_client.send_command("group", "g-id", cmd)

        import json

        body = json.loads(route.calls.last.request.read())
        assert body["type"] == "setLevel"
        assert body["level"] == 200
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_colour_temperature_body_uses_alias(self, api_client):
        from zencontrol_mcp.models.schemas import DaliCommand, DaliCommandType

        route = respx.post("https://api.zencontrol.com/v1/sites/s-id/command").mock(
            return_value=httpx.Response(200, json={})
        )

        cmd = DaliCommand(type=DaliCommandType.COLOUR_TEMPERATURE, temperature=370)
        await api_client.send_command("site", "s-id", cmd)

        import json

        body = json.loads(route.calls.last.request.read())
        assert body["type"] == "colourTemperature"
        assert body["temperature"] == 370
        await _cleanup(api_client)

    @pytest.mark.asyncio
    async def test_invalid_target_type_raises(self, api_client):
        from zencontrol_mcp.models.schemas import DaliCommand, DaliCommandType

        cmd = DaliCommand(type=DaliCommandType.OFF)
        with pytest.raises(ValueError, match="Unknown command target type"):
            await api_client.send_command("invalid_target", "some-id", cmd)
        await _cleanup(api_client)


# ---------------------------------------------------------------------------
# list_device_locations — URL construction
# ---------------------------------------------------------------------------


class TestListDeviceLocations:
    @pytest.mark.asyncio
    @respx.mock
    async def test_site_scope_url(self, api_client):
        route = respx.get(
            "https://api.zencontrol.com/v2/sites/s-id/device-locations"
        ).mock(return_value=httpx.Response(200, json={"deviceLocations": []}))

        await api_client.list_device_locations("site", "s-id")
        assert route.called
        await _cleanup(api_client)

    @pytest.mark.asyncio
    @respx.mock
    async def test_permission_group_passed(self, api_client):
        route = respx.get(
            "https://api.zencontrol.com/v2/sites/s-id/device-locations"
        ).mock(return_value=httpx.Response(200, json={"deviceLocations": []}))

        await api_client.list_device_locations("site", "s-id", permission_group="ALL")

        request = route.calls.last.request
        assert b"permissionGroup=ALL" in request.url.query
        await _cleanup(api_client)
