"""MCP tools for Phase 2: gateways, device locations, scenes, and profiles."""

from __future__ import annotations

import time

from fastmcp import Context, FastMCP

from zencontrol_cloud_mcp.api.rest import ZenControlAPI
from zencontrol_cloud_mcp.models.schemas import DaliCommand, DaliCommandType
from zencontrol_cloud_mcp.tools._helpers import (
    _format_command_result,
    confirm_broad_command,
    get_scope_constraint,
    parse_requested_properties,
    resolve_scope_id,
    wants_property,
)


def register(mcp: FastMCP) -> None:
    """Register Phase 2 extended tools with the FastMCP server."""

    @mcp.tool()
    async def list_gateways(
        ctx: Context,
        scope_type: str,
        scope_id: str,
        properties: str | None = None,
    ) -> str:
        """List gateways (DALI controllers) within a scope.

        Gateways are the physical controllers that manage DALI lighting buses.
        Each gateway connects to one or more lighting devices.

        Args:
            scope_type: Parent scope type. One of: site, floor, map, control_system.
            scope_id: The ID of the parent scope. When scope_type is 'site', accepts a
                UUID, tag (e.g. 'brown-home'), or name.
            properties: Optional comma-separated fields to include. Supported:
                label, id, firmware, mac, sync.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]
        requested = parse_requested_properties(properties)

        try:
            resolved_id = await resolve_scope_id(api, scope_type, scope_id)
        except ValueError as exc:
            return str(exc)

        if error := get_scope_constraint(ctx).validate_scope(scope_type, resolved_id):
            return error

        gateways = await api.list_gateways(scope_type, resolved_id)

        if not gateways:
            return f"No gateways found in {scope_type} {resolved_id}."

        lines: list[str] = [f"Found {len(gateways)} gateway(s) in {scope_type} {resolved_id}:\n"]
        for gw in gateways:
            label = gw.label.value if gw.label and gw.label.value else "Unlabelled"
            gw_id_str = "N/A"
            if gw.gateway_id:
                gw_id_str = f"{gw.gateway_id.gtin}-{gw.gateway_id.serial}"
            fw = gw.firmware_version or "unknown"
            mac = gw.mac_address or "unknown"
            sync = ""
            if gw.sync_status:
                sync = f"  Sync: {gw.sync_status}"

            lines.append(f"• {label if wants_property(requested, 'label', 'name') else 'Gateway'}")
            if wants_property(requested, "id", "gateway_id"):
                lines.append(f"  ID: {gw_id_str}")

            fw_mac: list[str] = []
            if wants_property(requested, "firmware"):
                fw_mac.append(f"Firmware: {fw}")
            if wants_property(requested, "mac", "mac_address"):
                fw_mac.append(f"MAC: {mac}")
            if fw_mac:
                lines.append(f"  {'  |  '.join(fw_mac)}")

            if sync and wants_property(requested, "sync", "sync_status"):
                lines.append(sync)
            lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def list_device_locations(
        ctx: Context,
        scope_type: str,
        scope_id: str,
        properties: str | None = None,
    ) -> str:
        """List device locations within a scope.

        Device locations represent commissioned positions for lighting fixtures.
        They track addressing and commissioning state.

        Args:
            scope_type: Parent scope type. One of: site, floor, map, control_system, gateway.
            scope_id: The ID of the parent scope. When scope_type is 'site', accepts a
                UUID, tag (e.g. 'brown-home'), or name.
            properties: Optional comma-separated fields to include. Supported:
                label, status, id, linked_device.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]
        requested = parse_requested_properties(properties)

        try:
            resolved_id = await resolve_scope_id(api, scope_type, scope_id)
        except ValueError as exc:
            return str(exc)

        if error := get_scope_constraint(ctx).validate_scope(scope_type, resolved_id):
            return error

        locations = await api.list_device_locations(scope_type, resolved_id)

        if not locations:
            return f"No device locations found in {scope_type} {resolved_id}."

        lines: list[str] = [
            f"Found {len(locations)} device location(s) in {scope_type} {resolved_id}:\n"
        ]
        for loc in locations:
            label = loc.label.value if loc.label and loc.label.value else "Unlabelled"
            loc_id = loc.device_location_id or "N/A"
            status = loc.status.value if loc.status and loc.status.value else "unknown"

            # Linked device ID
            linked = "N/A"
            if loc.device_id and loc.device_id.gateway_id and loc.device_id.bus_unit_id:
                gw = loc.device_id.gateway_id
                bu = loc.device_id.bus_unit_id
                linked = f"{gw.gtin}-{gw.serial}-{bu.gtin}-{bu.serial}"

            title = label if wants_property(requested, "label", "name") else "Device location"
            if wants_property(requested, "status"):
                lines.append(f"• {title}  [{status}]")
            else:
                lines.append(f"• {title}")
            if wants_property(requested, "id", "device_location_id"):
                lines.append(f"  ID: {loc_id}")
            if wants_property(requested, "linked_device", "device_id"):
                lines.append(f"  Linked device: {linked}")
            lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def list_scenes(
        ctx: Context,
        site_id: str,
        properties: str | None = None,
    ) -> str:
        """List available DALI scenes for a site.

        Scenes are preconfigured lighting states that can be recalled with control_light.

        Args:
            site_id: The UUID, tag (e.g. 'brown-home'), or name of the site.
            properties: Optional comma-separated fields to include. Supported:
                label, number.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]
        requested = parse_requested_properties(properties)

        try:
            site = await api.resolve_site_identifier(site_id)
        except ValueError as exc:
            return str(exc)
        resolved_id = site.site_id or site_id

        if error := get_scope_constraint(ctx).validate_site(resolved_id):
            return error

        scenes = await api.list_scenes(resolved_id)

        if not scenes:
            return f"No scenes found for site {resolved_id}."

        lines: list[str] = [f"Found {len(scenes)} scene(s) for site {resolved_id}:\n"]
        for scene in scenes:
            label = scene.label or "Unlabelled"
            number = scene.scene_number if scene.scene_number is not None else "N/A"
            scene_title = label if wants_property(requested, "label", "name") else "Scene"
            if wants_property(requested, "number", "scene_number"):
                lines.append(f"• {scene_title}  (scene number: {number})")
            else:
                lines.append(f"• {scene_title}")

        return "\n".join(lines)

    @mcp.tool()
    async def list_profiles(
        ctx: Context,
        site_id: str,
        properties: str | None = None,
    ) -> str:
        """List lighting profiles for a site.

        Profiles define scheduled lighting configurations (e.g., 'Work hours', 'After hours').
        Use set_profile to activate a profile.

        Args:
            site_id: The UUID, tag (e.g. 'brown-home'), or name of the site.
            properties: Optional comma-separated fields to include. Supported:
                label, number, status.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]
        requested = parse_requested_properties(properties)

        try:
            site = await api.resolve_site_identifier(site_id)
        except ValueError as exc:
            return str(exc)
        resolved_id = site.site_id or site_id

        if error := get_scope_constraint(ctx).validate_site(resolved_id):
            return error

        profiles = await api.list_profiles(resolved_id)

        if not profiles:
            return f"No profiles found for site {resolved_id}."

        lines: list[str] = [f"Found {len(profiles)} profile(s) for site {resolved_id}:\n"]
        for profile in profiles:
            label = profile.label.value if profile.label and profile.label.value else "Unlabelled"
            number = (
                profile.profile_number.value
                if profile.profile_number and profile.profile_number.value is not None
                else "N/A"
            )
            status = profile.status.value if profile.status and profile.status.value else "unknown"
            title = label if wants_property(requested, "label", "name") else "Profile"
            parts: list[str] = [f"• {title}"]
            if wants_property(requested, "number", "profile_number"):
                parts.append(f"(number: {number})")
            if wants_property(requested, "status"):
                parts.append(f"[{status}]")
            lines.append("  ".join(parts))

        return "\n".join(lines)

    @mcp.tool()
    async def set_profile(
        ctx: Context,
        target_type: str,
        target_id: str,
        profile_number: int,
    ) -> str:
        """Activate a lighting profile on a target.

        Profiles define scheduled lighting configurations. Use list_profiles to
        see available profiles and their numbers.

        Args:
            target_type: What to apply the profile to. Same options as control_light.
            target_id: The target's ID (same format as control_light).
            profile_number: The profile number to activate (0-65535).
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]

        # Scope constraint check
        if error := get_scope_constraint(ctx).validate_target(target_type, target_id):
            return error

        if not 0 <= profile_number <= 65535:
            return "The 'profile_number' parameter must be between 0 and 65535."

        command = DaliCommand(
            type=DaliCommandType.GO_TO_PROFILE,
            profile_number=profile_number,
        )

        # Elicitation guard for broad-scope commands
        if cancelled := await confirm_broad_command(ctx, target_type, target_id, "set_profile"):
            return cancelled

        try:
            result = await api.send_command(target_type, target_id, command)
        except Exception as exc:
            return f"Error sending profile command: {exc}"

        return _format_command_result(result, target_type, target_id, "set_profile")

    @mcp.tool()
    async def get_device_health(
        ctx: Context,
        scope_type: str,
        scope_id: str,
        properties: str | None = None,
    ) -> str:
        """Get control gear health and diagnostic information.

        Retrieves operating time, start counts, temperature, and failure
        conditions for all accessible ECGs (lighting control gear) in the
        given scope. Queries the last 7 days of data using LAST aggregation
        to return the most recent reading per device.

        Args:
            scope_type: Scope type. One of: site, tenancy.
            scope_id: The UUID of the site or tenancy. When scope_type is
                'site', also accepts a tag (e.g. 'brown-home') or name.
            properties: Optional comma-separated fields to include. Supported:
                metric, id, value.
        """
        import asyncio as _asyncio

        api: ZenControlAPI = ctx.lifespan_context["api"]
        requested = parse_requested_properties(properties)

        if scope_type == "site":
            try:
                site = await api.resolve_site_identifier(scope_id)
            except ValueError as exc:
                return str(exc)
            resolved_id = site.site_id or scope_id
            if error := get_scope_constraint(ctx).validate_site(resolved_id):
                return error
        else:
            resolved_id = scope_id
            # Tenancy scope cannot be validated against the site constraint without
            # an API lookup.  If a site constraint is active, block tenancy scope
            # to prevent accidental cross-site queries.
            constraint = get_scope_constraint(ctx)
            if constraint.site_id:
                return (
                    f"Cannot query health for {scope_type} scope when a site "
                    f"constraint is active.  Use scope_type='site' with the "
                    f"constrained site ID instead."
                )

        # Use last 7 days as time window to catch recent readings.
        now_ms = int(time.time() * 1000)
        seven_days_ms = 7 * 24 * 60 * 60 * 1000
        start_ms = now_ms - seven_days_ms

        metrics = [
            ("control-gear-operating-time-sum", "Operating time (hours)"),
            ("control-gear-start-counter-sum", "Start count"),
            ("control-gear-temperature", "Temperature (°C)"),
            ("control-gear-overall-failure-condition", "Failure conditions"),
        ]

        async def _fetch(metric: str) -> tuple[str, object]:
            try:
                result = await api.get_control_gear_health(
                    scope_type, resolved_id, metric, start_ms, now_ms
                )
                return metric, result
            except Exception as exc:  # noqa: BLE001
                return metric, exc

        fetch_results = await _asyncio.gather(*[_fetch(m) for m, _ in metrics])
        results = dict(fetch_results)

        from zencontrol_cloud_mcp.models.schemas import AnalyticsResponse

        lines: list[str] = [f"Control gear health for {scope_type} {resolved_id}:\n"]

        for metric_key, label in metrics:
            result = results.get(metric_key)
            if wants_property(requested, "metric", "label"):
                lines.append(f"## {label}")
            if isinstance(result, Exception):
                lines.append(f"  (unavailable: {result})\n")
                continue

            if not isinstance(result, AnalyticsResponse) or not result.items:
                lines.append("  No data available.\n")
                continue

            for item in result.items:
                item_id = item.id or "unknown"
                if not item.values:
                    continue
                latest = item.values[-1]
                if isinstance(latest, dict):
                    # Failure condition response format
                    issue = latest.get("issue", "")
                    details = latest.get("details", {})
                    contains_issue = details.get("containsIssue", False)
                    value_str = "⚠ ISSUE" if contains_issue else "OK"
                    if issue:
                        value_str += f" ({issue})"
                else:
                    value_str = str(latest)
                if wants_property(requested, "id") and wants_property(requested, "value"):
                    lines.append(f"  • {item_id}: {value_str}")
                elif wants_property(requested, "id"):
                    lines.append(f"  • {item_id}")
                elif wants_property(requested, "value"):
                    lines.append(f"  • {value_str}")
            lines.append("")

        return "\n".join(lines)
