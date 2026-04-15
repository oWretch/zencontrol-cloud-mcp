"""Typed async methods for ZenControl REST API endpoints.

Provides :class:`ZenControlAPI` which wraps :class:`ZenControlClient` with
higher-level, scope-aware methods that return validated Pydantic models.
"""

from __future__ import annotations

import logging
from typing import Any

from zencontrol_mcp.api.client import ZenControlClient
from zencontrol_mcp.models.schemas import (
    ControlSystem,
    DaliCommand,
    DaliCommandErrors,
    Device,
    DeviceLocation,
    Ecg,
    Floor,
    Gateway,
    Group,
    Map,
    Site,
    Tenancy,
    Zone,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Scope → URL segment mappings
# ------------------------------------------------------------------

SCOPE_PATH_MAP: dict[str, str] = {
    "site": "sites",
    "floor": "floors",
    "map": "maps",
    "tenancy": "tenancies",
    "control_system": "control-systems",
    "gateway": "gateways",
    "zone": "zones",
}

COMMAND_TARGET_MAP: dict[str, str] = {
    "site": "sites",
    "tenancy": "tenancies",
    "floor": "floors",
    "map": "maps",
    "zone": "zones",
    "control_system": "control-systems",
    "gateway": "gateways",
    "device_location": "device-locations",
    "device": "devices",
    "ecg": "ecgs",
    "ecd": "ecds",
    "group": "groups",
}

# Maps the URL resource segment to the JSON response wrapper key.
_RESPONSE_KEY: dict[str, str] = {
    "sites": "sites",
    "floors": "floors",
    "maps": "maps",
    "tenancies": "tenancies",
    "zones": "zones",
    "control-systems": "controlSystems",
    "gateways": "gateways",
    "groups": "groups",
    "devices": "devices",
    "ecgs": "ecgs",
    "device-locations": "deviceLocations",
}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_scoped_url(scope_type: str, scope_id: str, resource: str) -> str:
    """Build a scope-based REST URL: ``/v2/{scope_path}/{scope_id}/{resource}``."""
    scope_path = SCOPE_PATH_MAP.get(scope_type)
    if scope_path is None:
        msg = (
            f"Unknown scope type: {scope_type!r}. "
            f"Must be one of: {', '.join(sorted(SCOPE_PATH_MAP))}"
        )
        raise ValueError(msg)
    return f"/v2/{scope_path}/{scope_id}/{resource}"


def _response_key(resource: str) -> str:
    """Return the JSON wrapper key for a given URL resource segment."""
    key = _RESPONSE_KEY.get(resource)
    if key is None:
        msg = f"No response-key mapping for resource: {resource!r}"
        raise ValueError(msg)
    return key


# ------------------------------------------------------------------
# API class
# ------------------------------------------------------------------


class ZenControlAPI:
    """Typed async methods for ZenControl REST API endpoints.

    All methods return validated Pydantic model instances.
    """

    def __init__(self, client: ZenControlClient) -> None:
        self.client = client

    # ------------------------------------------------------------------
    # Sites
    # ------------------------------------------------------------------

    async def list_sites(self) -> list[Site]:
        """List all sites visible to the authenticated user."""
        response = await self.client.get("/v2/sites")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        logger.debug("list_sites returned %d site(s)", len(data.get("sites", [])))
        return [Site.model_validate(s) for s in data["sites"]]

    async def get_site(self, site_id: str) -> Site:
        """Get a single site by ID."""
        response = await self.client.get(f"/v2/sites/{site_id}")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return Site.model_validate(data)

    # ------------------------------------------------------------------
    # Site-scoped collections
    # ------------------------------------------------------------------

    async def list_floors(self, site_id: str) -> list[Floor]:
        """List floors for a site."""
        response = await self.client.get(f"/v2/sites/{site_id}/floors")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [Floor.model_validate(f) for f in data["floors"]]

    async def list_tenancies(self, site_id: str) -> list[Tenancy]:
        """List tenancies for a site."""
        response = await self.client.get(f"/v2/sites/{site_id}/tenancies")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [Tenancy.model_validate(t) for t in data["tenancies"]]

    async def list_zones(self, site_id: str) -> list[Zone]:
        """List zones for a site."""
        response = await self.client.get(f"/v2/sites/{site_id}/zones")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [Zone.model_validate(z) for z in data["zones"]]

    # ------------------------------------------------------------------
    # Scope-based collections
    # ------------------------------------------------------------------

    async def list_maps(self, scope_type: str, scope_id: str) -> list[Map]:
        """List maps within a scope (site, floor, …)."""
        url = _build_scoped_url(scope_type, scope_id, "maps")
        response = await self.client.get(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [Map.model_validate(m) for m in data["maps"]]

    async def list_control_systems(
        self,
        scope_type: str,
        scope_id: str,
    ) -> list[ControlSystem]:
        """List control systems within a scope."""
        url = _build_scoped_url(scope_type, scope_id, "control-systems")
        response = await self.client.get(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [
            ControlSystem.model_validate(cs)
            for cs in data[_response_key("control-systems")]
        ]

    async def list_groups(self, scope_type: str, scope_id: str) -> list[Group]:
        """List groups within a scope (site, floor, map, control-system, gateway)."""
        url = _build_scoped_url(scope_type, scope_id, "groups")
        response = await self.client.get(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [Group.model_validate(g) for g in data["groups"]]

    async def list_gateways(
        self,
        scope_type: str,
        scope_id: str,
    ) -> list[Gateway]:
        """List gateways within a scope."""
        url = _build_scoped_url(scope_type, scope_id, "gateways")
        response = await self.client.get(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [Gateway.model_validate(gw) for gw in data["gateways"]]

    async def list_devices(
        self,
        scope_type: str,
        scope_id: str,
    ) -> list[Device]:
        """List devices within a scope."""
        url = _build_scoped_url(scope_type, scope_id, "devices")
        response = await self.client.get(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [Device.model_validate(d) for d in data["devices"]]

    async def list_ecgs(self, scope_type: str, scope_id: str) -> list[Ecg]:
        """List emergency control gear (ECGs) within a scope."""
        url = _build_scoped_url(scope_type, scope_id, "ecgs")
        response = await self.client.get(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [Ecg.model_validate(e) for e in data["ecgs"]]

    async def list_device_locations(
        self,
        scope_type: str,
        scope_id: str,
    ) -> list[DeviceLocation]:
        """List device locations within a scope."""
        url = _build_scoped_url(scope_type, scope_id, "device-locations")
        response = await self.client.get(url)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return [
            DeviceLocation.model_validate(dl)
            for dl in data[_response_key("device-locations")]
        ]

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def send_command(
        self,
        target_type: str,
        target_id: str,
        command: DaliCommand,
    ) -> DaliCommandErrors | None:
        """Send a DALI command to a target.

        Parameters
        ----------
        target_type:
            One of the keys in :data:`COMMAND_TARGET_MAP` (e.g. ``"device"``,
            ``"group"``, ``"zone"``).
        target_id:
            Target identifier.  Format varies by target type:

            * zones: ``{siteId}-{zoneId}``
            * groups: ``{gtin}-{serial}-{groupNumber}``
            * devices/ecgs/ecds:
              ``{gatewayGtin}-{gatewaySerial}-{busUnitGtin}-{busUnitSerial}``
              (plus ``-{logicalIndex}`` for ecgs/ecds)
        command:
            The DALI command payload.

        Returns
        -------
        DaliCommandErrors | None
            Parsed error details if the API reports errors, otherwise ``None``.
        """
        target_path = COMMAND_TARGET_MAP.get(target_type)
        if target_path is None:
            msg = (
                f"Unknown command target type: {target_type!r}. "
                f"Must be one of: {', '.join(sorted(COMMAND_TARGET_MAP))}"
            )
            raise ValueError(msg)

        url = f"/v1/{target_path}/{target_id}/command"
        logger.debug("Sending command to %s %s: %s", target_type, target_id, command)

        response = await self.client.post(url, json=command.model_dump(by_alias=True))
        response.raise_for_status()

        body = response.json()
        if body:
            return DaliCommandErrors.model_validate(body)
        return None
