"""MCP tools for listing devices, groups, and control gear."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_mcp.api.rest import ZenControlAPI
from zencontrol_mcp.tools._helpers import get_scope_constraint, resolve_scope_id


def _format_dali_id(dali_id: object) -> str:
    """Format a DaliId as 'gtin-serial'."""
    return f"{dali_id.gtin}-{dali_id.serial}"  # type: ignore[union-attr]


def register(mcp: FastMCP) -> None:
    """Register device/group listing tools with the FastMCP server."""

    @mcp.tool()
    async def list_groups(
        ctx: Context,
        scope_type: str,
        scope_id: str,
    ) -> str:
        """List lighting groups within a scope.

        Groups are collections of lights that can be controlled together.
        Use 'control_light' with target_type='group' to control a group.

        Args:
            scope_type: The type of parent scope. One of: site, floor, map, control_system, gateway.
            scope_id: The ID of the parent scope. When scope_type is 'site', accepts a
                UUID, tag (e.g. 'brown-home'), or name.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]

        try:
            resolved_id = await resolve_scope_id(api, scope_type, scope_id)
        except ValueError as exc:
            return str(exc)

        if error := get_scope_constraint(ctx).validate_scope(scope_type, resolved_id):
            return error

        groups = await api.list_groups(scope_type, resolved_id, permission_group="ALL")

        if not groups:
            return f"No groups found in {scope_type} {resolved_id}."

        lines: list[str] = [
            f"Found {len(groups)} group(s) in {scope_type} {resolved_id}:\n"
        ]
        for group in groups:
            label = (
                group.label.value if group.label and group.label.value else "Unlabelled"
            )
            group_type = (
                group.type.value if group.type and group.type.value else "unknown"
            )
            status = (
                group.status.value if group.status and group.status.value else "unknown"
            )

            # Build command target ID: gtin-serial-groupNumber
            target_id = "N/A"
            if group.group_id and group.group_id.gateway_id:
                gw = group.group_id.gateway_id
                target_id = f"{gw.gtin}-{gw.serial}-{group.group_id.group_number}"

            # Determine lighting permission from permissionGroup=ALL response
            perm_tag = ""
            if group.permissions and group.permissions.group:
                lighting = group.permissions.group.lighting
                aggregate = group.permissions.group.aggregate
                can_control = (lighting and lighting.write) or (
                    aggregate and aggregate.write
                )
                can_read = (lighting and lighting.read) or (
                    aggregate and aggregate.read
                )
                if can_control:
                    perm_tag = "  [can control]"
                elif can_read:
                    perm_tag = "  [view only]"

            lines.append(f"• {label}{perm_tag}")
            lines.append(f"  Target ID: {target_id}")
            lines.append(f"  Type: {group_type}  |  Status: {status}")
            lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def list_devices(
        ctx: Context,
        scope_type: str,
        scope_id: str,
    ) -> str:
        """List lighting devices and their control gear (ECGs) within a scope.

        Devices represent physical light fittings. Each device contains one or
        more ECGs (Electronic Control Gear) which are the individually controllable units.

        Args:
            scope_type: The type of parent scope. One of: site, floor, map, control_system, gateway.
            scope_id: The ID of the parent scope. When scope_type is 'site', accepts a
                UUID, tag (e.g. 'brown-home'), or name.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]

        try:
            resolved_id = await resolve_scope_id(api, scope_type, scope_id)
        except ValueError as exc:
            return str(exc)

        if error := get_scope_constraint(ctx).validate_scope(scope_type, resolved_id):
            return error

        devices = await api.list_devices(scope_type, resolved_id)

        if not devices:
            return f"No devices found in {scope_type} {resolved_id}."

        lines: list[str] = [
            f"Found {len(devices)} device(s) in {scope_type} {resolved_id}:\n"
        ]
        for device in devices:
            label = (
                device.label.value
                if device.label and device.label.value
                else "Unlabelled"
            )
            status = (
                device.status.value
                if device.status and device.status.value
                else "unknown"
            )

            # Build device identifier string
            dev_id_str = "N/A"
            if (
                device.device_id
                and device.device_id.gateway_id
                and device.device_id.bus_unit_id
            ):
                gw = device.device_id.gateway_id
                bu = device.device_id.bus_unit_id
                dev_id_str = f"{gw.gtin}-{gw.serial}-{bu.gtin}-{bu.serial}"

            identifier = (
                device.identifier.value
                if device.identifier and device.identifier.value is not None
                else ""
            )
            id_str = f"  Identifier: {identifier}" if identifier else ""

            lines.append(f"• {label}  [{status}]")
            lines.append(f"  Device ID: {dev_id_str}")
            if id_str:
                lines.append(id_str)

            # ECGs
            if device.ecgs:
                for ecg in device.ecgs:
                    ecg_label = (
                        ecg.label.value
                        if ecg.label and ecg.label.value
                        else "Unlabelled ECG"
                    )
                    ecg_status = (
                        ecg.status.value
                        if ecg.status and ecg.status.value
                        else "unknown"
                    )
                    ecg_id_str = "N/A"
                    if ecg.ecg_id and ecg.ecg_id.gateway_id and ecg.ecg_id.bus_unit_id:
                        eg = ecg.ecg_id.gateway_id
                        eb = ecg.ecg_id.bus_unit_id
                        ecg_id_str = (
                            f"{eg.gtin}-{eg.serial}-{eb.gtin}-{eb.serial}"
                            f"-{ecg.ecg_id.logical_index}"
                        )
                    lines.append(
                        f"    ECG: {ecg_label}  [{ecg_status}]  (ID: {ecg_id_str})"
                    )

            # ECDs
            if device.ecds:
                for ecd in device.ecds:
                    ecd_label = (
                        ecd.label.value
                        if ecd.label and ecd.label.value
                        else "Unlabelled ECD"
                    )
                    ecd_status = (
                        ecd.status.value
                        if ecd.status and ecd.status.value
                        else "unknown"
                    )
                    ecd_id_str = "N/A"
                    if ecd.ecd_id and ecd.ecd_id.gateway_id and ecd.ecd_id.bus_unit_id:
                        dg = ecd.ecd_id.gateway_id
                        db = ecd.ecd_id.bus_unit_id
                        ecd_id_str = (
                            f"{dg.gtin}-{dg.serial}-{db.gtin}-{db.serial}"
                            f"-{ecd.ecd_id.logical_index}"
                        )
                    lines.append(
                        f"    ECD: {ecd_label}  [{ecd_status}]  (ID: {ecd_id_str})"
                    )

            lines.append("")

        return "\n".join(lines)
