"""MCP resources for browsing the ZenControl site hierarchy.

Resources expose the site/floor/zone/group hierarchy as addressable
URIs that LLM clients can read or inject into context without tool calls.

URI scheme::

    zencontrol://sites                           → all accessible sites
    zencontrol://sites/{site_id}                 → site detail + hierarchy
    zencontrol://sites/{site_id}/floors          → floor list
    zencontrol://sites/{site_id}/zones           → zone list
    zencontrol://sites/{site_id}/groups          → group list
    zencontrol://sites/{site_id}/gateways        → gateway list
    zencontrol://sites/{site_id}/scenes          → scene list
    zencontrol://sites/{site_id}/profiles        → profile list

``{site_id}`` in the URI accepts a UUID, tag (e.g. ``brown-home``), or name.
"""

from __future__ import annotations

import asyncio

from fastmcp import Context, FastMCP

from zencontrol_cloud_mcp.api.rest import ZenControlAPI
from zencontrol_cloud_mcp.scope import ScopeConstraint


async def _resolve(api: ZenControlAPI, site_id: str) -> tuple[str, str] | str:
    """Resolve site_id to (uuid, display_name) or an error string."""
    try:
        site = await api.resolve_site_identifier(site_id)
    except ValueError as exc:
        return str(exc)
    uuid = site.site_id or site_id
    display = site.tag or site.name or uuid
    return uuid, display


def register(mcp: FastMCP) -> None:
    """Register hierarchy resources with the FastMCP server."""

    @mcp.resource(
        "zencontrol://sites",
        name="ZenControl Sites",
        description="All ZenControl sites accessible to the authenticated user.",
        mime_type="text/plain",
    )
    async def sites_resource(ctx: Context) -> str:
        """List all accessible ZenControl sites."""
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        try:
            sites = await api.list_sites()
        except Exception as exc:
            return f"Error fetching sites: {exc}"

        if scope.site_id:
            sites = [s for s in sites if s.site_id == scope.site_id]

        if not sites:
            return "No sites accessible."

        lines = [f"ZenControl Sites ({len(sites)}):\n"]
        for site in sites:
            name = site.name or "Unnamed"
            tag = site.tag or ""
            uuid = site.site_id or "N/A"
            location_parts: list[str] = []
            if site.address:
                for part in (
                    site.address.locality,
                    site.address.admin_area,
                    site.address.country,
                ):
                    if part:
                        location_parts.append(part)
            location = ", ".join(location_parts) if location_parts else "No address"

            lines.append(f"• {name}")
            if tag:
                lines.append(f"  Tag: {tag}  (URI: zencontrol://sites/{tag})")
            lines.append(f"  UUID: {uuid}")
            lines.append(f"  Location: {location}")
            lines.append("")

        return "\n".join(lines)

    @mcp.resource(
        "zencontrol://sites/{site_id}",
        name="ZenControl Site Detail",
        description=(
            "Full site hierarchy: floors, zones, groups, gateways, tenancies. "
            "{site_id} accepts a UUID, tag (e.g. brown-home), or site name."
        ),
        mime_type="text/plain",
    )
    async def site_detail_resource(site_id: str, ctx: Context) -> str:
        """Get full detail for a ZenControl site."""
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        resolved = await _resolve(api, site_id)
        if isinstance(resolved, str):
            return resolved
        uuid, display = resolved

        if error := scope.validate_site(uuid):
            return error

        try:
            site, (floors, tenancies, zones, gateways) = await asyncio.gather(
                api.get_site(uuid),
                asyncio.gather(
                    api.list_floors(uuid),
                    api.list_tenancies(uuid),
                    api.list_zones(uuid),
                    api.list_gateways("site", uuid),
                ),
            )
        except Exception as exc:
            return f"Error fetching site detail: {exc}"

        lines: list[str] = []
        lines.append(f"Site: {site.name or display}")
        lines.append(f"UUID: {site.site_id}")
        if site.tag:
            lines.append(f"Tag: {site.tag}")
            lines.append(f"Portal: https://cloud.zencontrol.com/sites/{site.tag}/")
        if site.building_size is not None:
            lines.append(f"Building size: {site.building_size}")

        lines.append(f"\nFloors ({len(floors)}):")
        for floor in floors:
            lines.append(
                f"  • {floor.label.value if floor.label and floor.label.value else 'Unlabelled'}  (ID: {floor.floor_id})"
            )
        if not floors:
            lines.append("  (none)")

        lines.append(f"\nTenancies ({len(tenancies)}):")
        for t in tenancies:
            lines.append(f"  • {t.label or 'Unlabelled'}  (ID: {t.tenancy_id})")
        if not tenancies:
            lines.append("  (none)")

        lines.append(f"\nZones ({len(zones)}):")
        for zone in zones:
            label = zone.label.value if zone.label and zone.label.value else "Unlabelled"
            lines.append(f"  • {label}  (ID: {zone.zone_id})")
        if not zones:
            lines.append("  (none)")

        lines.append(f"\nGateways ({len(gateways)}):")
        for gw in gateways:
            label = gw.label.value if gw.label and gw.label.value else "Unlabelled"
            gw_id = f"{gw.gateway_id.gtin}-{gw.gateway_id.serial}" if gw.gateway_id else "N/A"
            lines.append(f"  • {label}  (ID: {gw_id})")
        if not gateways:
            lines.append("  (none)")

        return "\n".join(lines)

    @mcp.resource(
        "zencontrol://sites/{site_id}/floors",
        name="ZenControl Site Floors",
        description=(
            "Floor list for a site. {site_id} accepts a UUID, tag (e.g. brown-home), or site name."
        ),
        mime_type="text/plain",
    )
    async def site_floors_resource(site_id: str, ctx: Context) -> str:
        """List floors for a ZenControl site."""
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        resolved = await _resolve(api, site_id)
        if isinstance(resolved, str):
            return resolved
        uuid, display = resolved

        if error := scope.validate_site(uuid):
            return error

        try:
            floors = await api.list_floors(uuid)
        except Exception as exc:
            return f"Error fetching floors: {exc}"

        if not floors:
            return f"No floors found for site '{display}'."

        lines = [f"Floors for site '{display}' ({len(floors)}):\n"]
        for floor in floors:
            lines.append(
                f"• {floor.label.value if floor.label and floor.label.value else 'Unlabelled'}  (ID: {floor.floor_id})"
            )
        return "\n".join(lines)

    @mcp.resource(
        "zencontrol://sites/{site_id}/zones",
        name="ZenControl Site Zones",
        description=(
            "Zone list for a site. Zones are schedulable lighting areas. "
            "{site_id} accepts a UUID, tag, or name."
        ),
        mime_type="text/plain",
    )
    async def site_zones_resource(site_id: str, ctx: Context) -> str:
        """List zones for a ZenControl site."""
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        resolved = await _resolve(api, site_id)
        if isinstance(resolved, str):
            return resolved
        uuid, display = resolved

        if error := scope.validate_site(uuid):
            return error

        try:
            zones = await api.list_zones(uuid)
        except Exception as exc:
            return f"Error fetching zones: {exc}"

        if not zones:
            return f"No zones found for site '{display}'."

        lines = [f"Zones for site '{display}' ({len(zones)}):\n"]
        for zone in zones:
            label = zone.label.value if zone.label and zone.label.value else "Unlabelled"
            status = zone.status.value if zone.status and zone.status.value else ""
            status_str = f"  [{status}]" if status else ""
            lines.append(f"• {label}{status_str}  (ID: {zone.zone_id})")
        return "\n".join(lines)

    @mcp.resource(
        "zencontrol://sites/{site_id}/groups",
        name="ZenControl Site Groups",
        description=(
            "Lighting group list for a site. Use group IDs with control_light. "
            "{site_id} accepts a UUID, tag, or name."
        ),
        mime_type="text/plain",
    )
    async def site_groups_resource(site_id: str, ctx: Context) -> str:
        """List lighting groups for a ZenControl site."""
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        resolved = await _resolve(api, site_id)
        if isinstance(resolved, str):
            return resolved
        uuid, display = resolved

        if error := scope.validate_site(uuid):
            return error

        try:
            groups = await api.list_groups("site", uuid)
        except Exception as exc:
            return f"Error fetching groups: {exc}"

        if not groups:
            return f"No groups found for site '{display}'."

        lines = [f"Groups for site '{display}' ({len(groups)}):\n"]
        for group in groups:
            label = group.label.value if group.label and group.label.value else "Unlabelled"
            target_id = "N/A"
            if group.group_id and group.group_id.gateway_id:
                gw = group.group_id.gateway_id
                target_id = f"{gw.gtin}-{gw.serial}-{group.group_id.group_number}"
            lines.append(f"• {label}  (control_light target: {target_id})")
        return "\n".join(lines)

    @mcp.resource(
        "zencontrol://sites/{site_id}/gateways",
        name="ZenControl Site Gateways",
        description=("DALI gateway list for a site. {site_id} accepts a UUID, tag, or name."),
        mime_type="text/plain",
    )
    async def site_gateways_resource(site_id: str, ctx: Context) -> str:
        """List gateways for a ZenControl site."""
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        resolved = await _resolve(api, site_id)
        if isinstance(resolved, str):
            return resolved
        uuid, display = resolved

        if error := scope.validate_site(uuid):
            return error

        try:
            gateways = await api.list_gateways("site", uuid)
        except Exception as exc:
            return f"Error fetching gateways: {exc}"

        if not gateways:
            return f"No gateways found for site '{display}'."

        lines = [f"Gateways for site '{display}' ({len(gateways)}):\n"]
        for gw in gateways:
            label = gw.label.value if gw.label and gw.label.value else "Unlabelled"
            gw_id = f"{gw.gateway_id.gtin}-{gw.gateway_id.serial}" if gw.gateway_id else "N/A"
            fw = gw.firmware_version or "unknown"
            lines.append(f"• {label}  (ID: {gw_id}, firmware: {fw})")
        return "\n".join(lines)

    @mcp.resource(
        "zencontrol://sites/{site_id}/scenes",
        name="ZenControl Site Scenes",
        description=(
            "DALI scene list for a site. Scenes are recalled with control_light. "
            "{site_id} accepts a UUID, tag, or name."
        ),
        mime_type="text/plain",
    )
    async def site_scenes_resource(site_id: str, ctx: Context) -> str:
        """List DALI scenes for a ZenControl site."""
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        resolved = await _resolve(api, site_id)
        if isinstance(resolved, str):
            return resolved
        uuid, display = resolved

        if error := scope.validate_site(uuid):
            return error

        try:
            scenes = await api.list_scenes(uuid)
        except Exception as exc:
            return f"Error fetching scenes: {exc}"

        if not scenes:
            return f"No scenes found for site '{display}'."

        lines = [f"Scenes for site '{display}' ({len(scenes)}):\n"]
        for scene in scenes:
            label = scene.label or "Unlabelled"
            number = scene.scene_number if scene.scene_number is not None else "N/A"
            lines.append(f"• {label}  (scene number: {number})")
        return "\n".join(lines)

    @mcp.resource(
        "zencontrol://sites/{site_id}/profiles",
        name="ZenControl Site Profiles",
        description=(
            "Lighting profile list for a site. Profiles are activated with set_profile. "
            "{site_id} accepts a UUID, tag, or name."
        ),
        mime_type="text/plain",
    )
    async def site_profiles_resource(site_id: str, ctx: Context) -> str:
        """List lighting profiles for a ZenControl site."""
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        resolved = await _resolve(api, site_id)
        if isinstance(resolved, str):
            return resolved
        uuid, display = resolved

        if error := scope.validate_site(uuid):
            return error

        try:
            profiles = await api.list_profiles(uuid)
        except Exception as exc:
            return f"Error fetching profiles: {exc}"

        if not profiles:
            return f"No profiles found for site '{display}'."

        lines = [f"Profiles for site '{display}' ({len(profiles)}):\n"]
        for profile in profiles:
            label = profile.label.value if profile.label and profile.label.value else "Unlabelled"
            number = (
                profile.profile_number.value
                if profile.profile_number and profile.profile_number.value is not None
                else "N/A"
            )
            status = profile.status.value if profile.status and profile.status.value else "unknown"
            lines.append(f"• {label}  (number: {number})  [{status}]")
        return "\n".join(lines)
