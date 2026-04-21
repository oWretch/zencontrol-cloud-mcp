"""MCP tools for live-streaming sensor and light data via WebSocket."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_cloud_mcp.api.live import LiveAPIError, LiveClient
from zencontrol_cloud_mcp.api.rest import ZenControlAPI
from zencontrol_cloud_mcp.tools._helpers import (
    get_scope_constraint,
    parse_requested_properties,
    wants_property,
)

_LIVE_ACCESS_HINT = (
    "The Live API requires separate activation for your ZenControl client. "
    "Contact ZenControl support to request access."
)


def _format_gateway_id(gateway_id: dict) -> str:
    """Format a gateway identifier dict as 'gtin-serial'."""
    return f"{gateway_id.get('gtin', '?')}-{gateway_id.get('serial', '?')}"


def _validate_duration(duration: int) -> str | None:
    """Return an error string if duration is out of range, otherwise None."""
    if not 1 <= duration <= 30:
        return "Duration must be between 1 and 30 seconds."
    return None


def register(mcp: FastMCP) -> None:
    """Register live-streaming tools with the FastMCP server."""

    @mcp.tool()
    async def get_live_light_levels(
        ctx: Context,
        site_id: str,
        duration: int = 5,
        target: str = "groups",
        properties: str | None = None,
    ) -> str:
        """Get current live light levels from a site.

        Connects to the ZenControl Live API briefly to capture current
        brightness levels for groups or individual ECGs.

        Requires the Live API to be enabled for this client. Contact
        ZenControl support if live tools return an access error.

        Args:
            site_id: The UUID, tag (e.g. 'brown-home'), or name of the site.
            duration: How many seconds to listen for updates (1-30, default 5).
            target: What to monitor: 'groups' for group levels, 'ecgs' for individual gear levels.
            properties: Optional comma-separated fields to include. Supported:
                gateway, target_id, percent, arc.
        """
        if error := _validate_duration(duration):
            return error

        if target not in ("groups", "ecgs"):
            return "Target must be 'groups' or 'ecgs'."
        requested = parse_requested_properties(properties)

        api: ZenControlAPI = ctx.lifespan_context["api"]
        try:
            site = await api.resolve_site_identifier(site_id)
        except ValueError as exc:
            return str(exc)
        resolved_id = site.site_id or site_id

        if error := get_scope_constraint(ctx).validate_site(resolved_id):
            return error

        live: LiveClient = ctx.lifespan_context["live"]
        method = "event.group.arc-level" if target == "groups" else "event.ecg.arc-level"

        try:
            events = await live.subscribe_once(
                method=method,
                content={"siteId": resolved_id},
                duration=float(duration),
            )
        except LiveAPIError as exc:
            if exc.is_access_error:
                return f"Live API access denied. {_LIVE_ACCESS_HINT} (Error: {exc})"
            return f"Live API error: {exc}"

        if not events:
            return (
                f"No {target} light-level events received from site {resolved_id} "
                f"in {duration}s. The site may have no active gateways or "
                f"no lights are currently changing."
            )

        lines: list[str] = [
            f"Live {target} light levels from site {resolved_id} "
            f"({len(events)} event(s) in {duration}s):\n"
        ]

        for event in events:
            gw_id = _format_gateway_id(event.get("gatewayId", {}))

            if target == "groups":
                for group in event.get("groups", []):
                    group_num = group.get("id", {}).get("groupNumber", "?")
                    value = group.get("value", 0)
                    pct = value / 254 * 100
                    if requested is None:
                        lines.append(f"  {gw_id} group {group_num}: {pct:.0f}% (arc {value})")
                        continue

                    parts: list[str] = ["  "]
                    if wants_property(requested, "gateway", "gateway_id"):
                        parts.append(gw_id)
                    if wants_property(requested, "target_id", "group", "group_number"):
                        parts.append(f"group {group_num}")
                    if wants_property(requested, "percent"):
                        parts.append(f"{pct:.0f}%")
                    if wants_property(requested, "arc"):
                        parts.append(f"(arc {value})")
                    line = " ".join(parts).rstrip()
                    lines.append(line if line.strip() else f"  group {group_num}")
            else:
                for ecg in event.get("ecgs", []):
                    ecg_id = ecg.get("id", {})
                    bus_gtin = ecg_id.get("busUnitGtin", "?")
                    bus_serial = ecg_id.get("busUnitSerial", "?")
                    logical_idx = ecg_id.get("logicalIndex", "?")
                    value = ecg.get("value", 0)
                    pct = value / 254 * 100
                    ecg_target = f"ecg {bus_gtin}-{bus_serial}-{logical_idx}"
                    if requested is None:
                        lines.append(f"  {gw_id} {ecg_target}: {pct:.0f}% (arc {value})")
                        continue

                    parts = ["  "]
                    if wants_property(requested, "gateway", "gateway_id"):
                        parts.append(gw_id)
                    if wants_property(requested, "target_id", "ecg", "ecg_id"):
                        parts.append(ecg_target)
                    if wants_property(requested, "percent"):
                        parts.append(f"{pct:.0f}%")
                    if wants_property(requested, "arc"):
                        parts.append(f"(arc {value})")
                    line = " ".join(parts).rstrip()
                    lines.append(line if line.strip() else f"  {ecg_target}")

        return "\n".join(lines)

    @mcp.tool()
    async def get_sensor_readings(
        ctx: Context,
        site_id: str,
        sensor_type: str = "light",
        duration: int = 5,
        properties: str | None = None,
    ) -> str:
        """Get live sensor readings from a site.

        Monitors light sensors (lux) or occupancy sensors (movement) in
        real-time.

        Requires the Live API to be enabled for this client. Contact
        ZenControl support if live tools return an access error.

        Args:
            site_id: The UUID, tag (e.g. 'brown-home'), or name of the site.
            sensor_type: Type of sensor: 'light' for lux readings, 'occupancy' for movement detection.
            duration: How many seconds to listen for updates (1-30, default 5).
            properties: Optional comma-separated fields to include. Supported:
                gateway, sensor_id, instance, value, calibrated, status.
        """
        if error := _validate_duration(duration):
            return error

        if sensor_type not in ("light", "occupancy"):
            return "Sensor type must be 'light' or 'occupancy'."
        requested = parse_requested_properties(properties)

        api: ZenControlAPI = ctx.lifespan_context["api"]
        try:
            site = await api.resolve_site_identifier(site_id)
        except ValueError as exc:
            return str(exc)
        resolved_id = site.site_id or site_id

        if error := get_scope_constraint(ctx).validate_site(resolved_id):
            return error

        live: LiveClient = ctx.lifespan_context["live"]
        method = (
            "event.light-sensor.lux-report"
            if sensor_type == "light"
            else "event.occupancy-sensor.movement-detected"
        )

        try:
            events = await live.subscribe_once(
                method=method,
                content={"siteId": resolved_id},
                duration=float(duration),
            )
        except LiveAPIError as exc:
            if exc.is_access_error:
                return f"Live API access denied. {_LIVE_ACCESS_HINT} (Error: {exc})"
            return f"Live API error: {exc}"

        if not events:
            return (
                f"No {sensor_type} sensor events received from site {resolved_id} in {duration}s."
            )

        lines: list[str] = [
            f"Live {sensor_type} sensor readings from site {resolved_id} "
            f"({len(events)} event(s) in {duration}s):\n"
        ]

        for event in events:
            gw_id = _format_gateway_id(event.get("gatewayId", {}))

            if sensor_type == "light":
                for sensor in event.get("lightSensors", []):
                    s_id = sensor.get("id", {})
                    bus_gtin = s_id.get("busUnitGtin", "?")
                    bus_serial = s_id.get("busUnitSerial", "?")
                    instance = s_id.get("instanceNumber", "?")
                    value = sensor.get("value", 0)
                    calibrated = sensor.get("isCalibrated", False)
                    sensor_target = f"sensor {bus_gtin}-{bus_serial}"
                    parts = ["  "]
                    if wants_property(requested, "gateway", "gateway_id"):
                        parts.append(gw_id)
                    if wants_property(requested, "sensor_id"):
                        parts.append(sensor_target)
                    if wants_property(requested, "instance", "instance_number"):
                        parts.append(f"instance {instance}")
                    if wants_property(requested, "value", "lux"):
                        parts.append(f"{value} lx")
                    if wants_property(requested, "calibrated"):
                        parts.append(f"(calibrated: {calibrated})")
                    line = " ".join(parts).rstrip()
                    lines.append(line if line.strip() else f"  {sensor_target}")
            else:
                for sensor in event.get("occupancySensors", []):
                    s_id = sensor.get("id", {})
                    bus_gtin = s_id.get("busUnitGtin", "?")
                    bus_serial = s_id.get("busUnitSerial", "?")
                    instance = s_id.get("instanceNumber", "?")
                    value = sensor.get("value", 0)
                    status = "movement detected" if value == 1 else "no movement"
                    sensor_target = f"sensor {bus_gtin}-{bus_serial}"
                    parts = ["  "]
                    if wants_property(requested, "gateway", "gateway_id"):
                        parts.append(gw_id)
                    if wants_property(requested, "sensor_id"):
                        parts.append(sensor_target)
                    if wants_property(requested, "instance", "instance_number"):
                        parts.append(f"instance {instance}")
                    if wants_property(requested, "status", "value"):
                        parts.append(status)
                    line = " ".join(parts).rstrip()
                    lines.append(line if line.strip() else f"  {sensor_target}")

        return "\n".join(lines)

    @mcp.tool()
    async def get_system_variables(
        ctx: Context,
        site_id: str,
        duration: int = 5,
        properties: str | None = None,
    ) -> str:
        """Get live system variable changes from a site.

        System variables are custom values stored on gateways, used for
        automation logic and integrations. The actual value is calculated
        as ``signedValue * 10^(magnitude - 127)``.

        Requires the Live API to be enabled for this client. Contact
        ZenControl support if live tools return an access error.

        Args:
            site_id: The UUID, tag (e.g. 'brown-home'), or name of the site.
            duration: How many seconds to listen for updates (1-30, default 5).
            properties: Optional comma-separated fields to include. Supported:
                gateway, index, value, signed, magnitude.
        """
        if error := _validate_duration(duration):
            return error
        requested = parse_requested_properties(properties)

        api: ZenControlAPI = ctx.lifespan_context["api"]
        try:
            site = await api.resolve_site_identifier(site_id)
        except ValueError as exc:
            return str(exc)
        resolved_id = site.site_id or site_id

        if error := get_scope_constraint(ctx).validate_site(resolved_id):
            return error

        live: LiveClient = ctx.lifespan_context["live"]

        try:
            events = await live.subscribe_once(
                method="event.system-variable.change",
                content={"siteId": resolved_id},
                duration=float(duration),
            )
        except LiveAPIError as exc:
            if exc.is_access_error:
                return f"Live API access denied. {_LIVE_ACCESS_HINT} (Error: {exc})"
            return f"Live API error: {exc}"

        if not events:
            return f"No system variable events received from site {resolved_id} in {duration}s."

        lines: list[str] = [
            f"Live system variable changes from site {resolved_id} "
            f"({len(events)} event(s) in {duration}s):\n"
        ]

        for event in events:
            gw_id = _format_gateway_id(event.get("gatewayId", {}))

            for var in event.get("systemVariables", []):
                index = var.get("id", {}).get("index", "?")
                signed_value = var.get("signedValue", 0)
                magnitude = var.get("magnitude", 127)
                actual_value = signed_value * (10 ** (magnitude - 127))
                parts = ["  "]
                if wants_property(requested, "gateway", "gateway_id"):
                    parts.append(gw_id)
                if wants_property(requested, "index"):
                    parts.append(f"variable {index}:")
                if wants_property(requested, "value", "actual_value"):
                    parts.append(str(actual_value))
                if wants_property(requested, "signed"):
                    parts.append(f"(signed={signed_value})")
                if wants_property(requested, "magnitude"):
                    parts.append(f"(magnitude={magnitude})")
                line = " ".join(parts).rstrip()
                lines.append(line if line.strip() else f"  variable {index}")

        return "\n".join(lines)
