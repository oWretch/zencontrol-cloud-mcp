"""MCP tools for site discovery and hierarchy browsing."""

from __future__ import annotations

import asyncio

from fastmcp import Context, FastMCP

from zencontrol_cloud_mcp.api.rest import ZenControlAPI
from zencontrol_cloud_mcp.tools._helpers import (
    get_scope_constraint,
    parse_requested_properties,
    wants_property,
)


def register(mcp: FastMCP) -> None:
    """Register site-related tools with the FastMCP server."""

    @mcp.tool()
    async def list_sites(ctx: Context, properties: str | None = None) -> str:
        """List all ZenControl sites accessible to the authenticated user.

        Returns site names, IDs, and locations. Use the site ID with other
        tools to query site resources like floors, groups, and devices.

        Args:
            properties: Optional comma-separated fields to include. Supported:
                name, id, tag, location.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]
        sites = await api.list_sites()
        requested = parse_requested_properties(properties)

        # Filter to scoped site if constraint is active
        scope = get_scope_constraint(ctx)
        if scope.site_id:
            sites = [s for s in sites if s.site_id == scope.site_id]

        if not sites:
            return "No sites found for the authenticated user."

        lines: list[str] = [f"Found {len(sites)} site(s):\n"]
        for site in sites:
            name = site.name or "Unnamed"
            site_id = site.site_id or "N/A"
            tag = site.tag or ""
            location_parts: list[str] = []
            if site.address:
                if site.address.street:
                    location_parts.append(site.address.street)
                if site.address.locality:
                    location_parts.append(site.address.locality)
                if site.address.admin_area:
                    location_parts.append(site.address.admin_area)
                if site.address.country:
                    location_parts.append(site.address.country)
            location = ", ".join(location_parts) if location_parts else "No address"

            bullet = name if wants_property(requested, "name") else "Site"
            lines.append(f"• {bullet}")
            if wants_property(requested, "id", "site_id"):
                lines.append(f"  ID: {site_id}")
            if tag and wants_property(requested, "tag"):
                lines.append(f"  Tag: {tag}")
            if wants_property(requested, "location", "address"):
                lines.append(f"  Location: {location}")
            lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def get_site_details(
        ctx: Context,
        site_id: str,
        properties: str | None = None,
    ) -> str:
        """Get detailed information about a ZenControl site including its hierarchy.

        Returns site info plus its floors, tenancies, zones, and gateways.
        Use this to discover the structure of a site before controlling devices.

        Args:
            site_id: The UUID, tag (e.g. 'brown-home'), or name of the site to query.
            properties: Optional comma-separated fields to include. Supported:
                name, id, tag, address, coordinates, building_size,
                floors, tenancies, zones, gateways.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]
        requested = parse_requested_properties(properties)

        try:
            resolved_site = await api.resolve_site_identifier(site_id)
        except ValueError as exc:
            return str(exc)
        resolved_id = resolved_site.site_id or site_id

        if error := get_scope_constraint(ctx).validate_site(resolved_id):
            return error

        need_floors = wants_property(requested, "floors")
        need_tenancies = wants_property(requested, "tenancies")
        need_zones = wants_property(requested, "zones")
        need_gateways = wants_property(requested, "gateways")

        async def _fetch_floors():
            return await api.list_floors(resolved_id) if need_floors else []

        async def _fetch_tenancies():
            return await api.list_tenancies(resolved_id) if need_tenancies else []

        async def _fetch_zones():
            return await api.list_zones(resolved_id) if need_zones else []

        async def _fetch_gateways():
            return await api.list_gateways("site", resolved_id) if need_gateways else []

        site, (floors, tenancies, zones, gateways) = await asyncio.gather(
            api.get_site(resolved_id),
            asyncio.gather(
                _fetch_floors(),
                _fetch_tenancies(),
                _fetch_zones(),
                _fetch_gateways(),
            ),
        )

        lines: list[str] = []

        # Site header
        name = site.name or "Unnamed"
        if wants_property(requested, "name", "site"):
            lines.append(f"Site: {name}")
        if wants_property(requested, "id", "site_id"):
            lines.append(f"ID: {site.site_id}")
        if site.tag and wants_property(requested, "tag"):
            lines.append(f"Tag: {site.tag}")
        if site.address and wants_property(requested, "address", "location"):
            addr_parts: list[str] = []
            if site.address.street:
                addr_parts.append(site.address.street)
            if site.address.locality:
                addr_parts.append(site.address.locality)
            if site.address.admin_area:
                addr_parts.append(site.address.admin_area)
            if site.address.post_code:
                addr_parts.append(site.address.post_code)
            if site.address.country:
                addr_parts.append(site.address.country)
            if addr_parts:
                lines.append(f"Address: {', '.join(addr_parts)}")
        if site.geographic_location and wants_property(
            requested, "coordinates", "geographic_location"
        ):
            lat = site.geographic_location.latitude
            lon = site.geographic_location.longitude
            if lat is not None and lon is not None:
                lines.append(f"Coordinates: {lat}, {lon}")
        if site.building_size is not None and wants_property(requested, "building_size"):
            lines.append(f"Building size: {site.building_size}")

        # Floors
        if wants_property(requested, "floors"):
            lines.append(f"\nFloors ({len(floors)}):")
            if floors:
                for floor in floors:
                    label = floor.label.value if floor.label and floor.label.value else "Unlabelled"
                    lines.append(f"  • {label}  (ID: {floor.floor_id})")
            else:
                lines.append("  (none)")

        # Tenancies
        if wants_property(requested, "tenancies"):
            lines.append(f"\nTenancies ({len(tenancies)}):")
            if tenancies:
                for tenancy in tenancies:
                    label = (
                        tenancy.label.value
                        if tenancy.label and tenancy.label.value
                        else "Unlabelled"
                    )
                    status = tenancy.status.value if tenancy.status and tenancy.status.value else ""
                    status_str = f"  [{status}]" if status else ""
                    lines.append(f"  • {label}{status_str}  (ID: {tenancy.tenancy_id})")
            else:
                lines.append("  (none)")

        # Zones
        if wants_property(requested, "zones"):
            lines.append(f"\nZones ({len(zones)}):")
            if zones:
                for zone in zones:
                    label = zone.label.value if zone.label and zone.label.value else "Unlabelled"
                    status = zone.status.value if zone.status and zone.status.value else ""
                    status_str = f"  [{status}]" if status else ""
                    lines.append(f"  • {label}{status_str}  (ID: {zone.zone_id})")
            else:
                lines.append("  (none)")

        # Gateways
        if wants_property(requested, "gateways"):
            lines.append(f"\nGateways ({len(gateways)}):")
            if gateways:
                for gw in gateways:
                    label = gw.label.value if gw.label and gw.label.value else "Unlabelled"
                    gw_id_str = ""
                    if gw.gateway_id:
                        gw_id_str = f"{gw.gateway_id.gtin}-{gw.gateway_id.serial}"
                    fw = gw.firmware_version or "unknown"
                    lines.append(f"  • {label}  (ID: {gw_id_str}, firmware: {fw})")
            else:
                lines.append("  (none)")

        if not lines:
            return (
                "No fields selected for output. "
                "Choose one or more properties, e.g. properties='id,name,gateways'."
            )

        return "\n".join(lines)
