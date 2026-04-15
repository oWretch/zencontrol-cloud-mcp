"""MCP tools for live-streaming sensor and light data via WebSocket."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_mcp.api.live import LiveClient


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
    ) -> str:
        """Get current live light levels from a site.

        Connects to the ZenControl Live API briefly to capture current
        brightness levels for groups or individual ECGs.

        Args:
            site_id: The UUID of the site to monitor.
            duration: How many seconds to listen for updates (1-30, default 5).
            target: What to monitor: 'groups' for group levels, 'ecgs' for individual gear levels.
        """
        if error := _validate_duration(duration):
            return error

        if target not in ("groups", "ecgs"):
            return "Target must be 'groups' or 'ecgs'."

        live: LiveClient = ctx.lifespan_context["live"]
        method = (
            "event.group.arc-level" if target == "groups" else "event.ecg.arc-level"
        )

        events = await live.subscribe_once(
            method=method,
            content={"siteId": site_id},
            duration=float(duration),
        )

        if not events:
            return (
                f"No {target} light-level events received from site {site_id} "
                f"in {duration}s. The site may have no active gateways or "
                f"no lights are currently changing."
            )

        lines: list[str] = [
            f"Live {target} light levels from site {site_id} "
            f"({len(events)} event(s) in {duration}s):\n"
        ]

        for event in events:
            gw_id = _format_gateway_id(event.get("gatewayId", {}))

            if target == "groups":
                for group in event.get("groups", []):
                    group_num = group.get("id", {}).get("groupNumber", "?")
                    value = group.get("value", 0)
                    pct = value / 254 * 100
                    lines.append(
                        f"  {gw_id} group {group_num}: {pct:.0f}% (arc {value})"
                    )
            else:
                for ecg in event.get("ecgs", []):
                    ecg_id = ecg.get("id", {})
                    bus_gtin = ecg_id.get("busUnitGtin", "?")
                    bus_serial = ecg_id.get("busUnitSerial", "?")
                    logical_idx = ecg_id.get("logicalIndex", "?")
                    value = ecg.get("value", 0)
                    pct = value / 254 * 100
                    lines.append(
                        f"  {gw_id} ecg {bus_gtin}-{bus_serial}-{logical_idx}: "
                        f"{pct:.0f}% (arc {value})"
                    )

        return "\n".join(lines)

    @mcp.tool()
    async def get_sensor_readings(
        ctx: Context,
        site_id: str,
        sensor_type: str = "light",
        duration: int = 5,
    ) -> str:
        """Get live sensor readings from a site.

        Monitors light sensors (lux) or occupancy sensors (movement) in
        real-time.

        Args:
            site_id: The UUID of the site to monitor.
            sensor_type: Type of sensor: 'light' for lux readings, 'occupancy' for movement detection.
            duration: How many seconds to listen for updates (1-30, default 5).
        """
        if error := _validate_duration(duration):
            return error

        if sensor_type not in ("light", "occupancy"):
            return "Sensor type must be 'light' or 'occupancy'."

        live: LiveClient = ctx.lifespan_context["live"]
        method = (
            "event.light-sensor.lux-report"
            if sensor_type == "light"
            else "event.occupancy-sensor.movement-detected"
        )

        events = await live.subscribe_once(
            method=method,
            content={"siteId": site_id},
            duration=float(duration),
        )

        if not events:
            return (
                f"No {sensor_type} sensor events received from site {site_id} "
                f"in {duration}s."
            )

        lines: list[str] = [
            f"Live {sensor_type} sensor readings from site {site_id} "
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
                    lines.append(
                        f"  {gw_id} sensor {bus_gtin}-{bus_serial} "
                        f"instance {instance}: {value} lx "
                        f"(calibrated: {calibrated})"
                    )
            else:
                for sensor in event.get("occupancySensors", []):
                    s_id = sensor.get("id", {})
                    bus_gtin = s_id.get("busUnitGtin", "?")
                    bus_serial = s_id.get("busUnitSerial", "?")
                    instance = s_id.get("instanceNumber", "?")
                    value = sensor.get("value", 0)
                    status = "movement detected" if value == 1 else "no movement"
                    lines.append(
                        f"  {gw_id} sensor {bus_gtin}-{bus_serial} "
                        f"instance {instance}: {status}"
                    )

        return "\n".join(lines)

    @mcp.tool()
    async def get_system_variables(
        ctx: Context,
        site_id: str,
        duration: int = 5,
    ) -> str:
        """Get live system variable changes from a site.

        System variables are custom values stored on gateways, used for
        automation logic and integrations. The actual value is calculated
        as ``signedValue * 10^(magnitude - 127)``.

        Args:
            site_id: The UUID of the site to monitor.
            duration: How many seconds to listen for updates (1-30, default 5).
        """
        if error := _validate_duration(duration):
            return error

        live: LiveClient = ctx.lifespan_context["live"]

        events = await live.subscribe_once(
            method="event.system-variable.change",
            content={"siteId": site_id},
            duration=float(duration),
        )

        if not events:
            return (
                f"No system variable events received from site {site_id} "
                f"in {duration}s."
            )

        lines: list[str] = [
            f"Live system variable changes from site {site_id} "
            f"({len(events)} event(s) in {duration}s):\n"
        ]

        for event in events:
            gw_id = _format_gateway_id(event.get("gatewayId", {}))

            for var in event.get("systemVariables", []):
                index = var.get("id", {}).get("index", "?")
                signed_value = var.get("signedValue", 0)
                magnitude = var.get("magnitude", 127)
                actual_value = signed_value * (10 ** (magnitude - 127))
                lines.append(
                    f"  {gw_id} variable {index}: {actual_value} "
                    f"(signed={signed_value}, magnitude={magnitude})"
                )

        return "\n".join(lines)
