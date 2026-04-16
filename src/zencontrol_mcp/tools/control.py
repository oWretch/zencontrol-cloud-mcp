"""MCP tools for controlling lights via DALI commands."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_mcp.api.rest import ZenControlAPI
from zencontrol_mcp.models.schemas import DaliCommand, DaliCommandType
from zencontrol_mcp.tools._helpers import confirm_broad_command, get_scope_constraint

# Valid actions mapped to their DaliCommandType
_ACTION_MAP: dict[str, DaliCommandType] = {
    "off": DaliCommandType.OFF,
    "on": DaliCommandType.RECALL_MAX,
    "set_level": DaliCommandType.SET_LEVEL,
    "recall_scene": DaliCommandType.GO_TO_SCENE,
    "dim_up": DaliCommandType.DIM_UP,
    "dim_down": DaliCommandType.DIM_DOWN,
    "identify": DaliCommandType.IDENTIFY,
}

_VALID_ACTIONS = ", ".join(sorted(_ACTION_MAP))


def _pct_to_dali(percent: int) -> int:
    """Convert a 0-100 percentage to a 0-254 DALI level."""
    return round(percent * 254 / 100)


def _format_command_result(
    result: object,
    target_type: str,
    target_id: str,
    action: str,
) -> str:
    """Format the result of a send_command call into a readable string."""
    if result is not None and hasattr(result, "errors") and result.errors:
        error_lines = [f"  • [{e.error_code}] {e.error_message}" for e in result.errors]
        return (
            f"Command '{action}' sent to {target_type} {target_id} "
            f"with errors:\n" + "\n".join(error_lines)
        )
    return f"Successfully sent '{action}' command to {target_type} {target_id}."


def register(mcp: FastMCP) -> None:
    """Register light control tools with the FastMCP server."""

    @mcp.tool()
    async def control_light(
        ctx: Context,
        target_type: str,
        target_id: str,
        action: str,
        level: int | None = None,
        scene: int | None = None,
    ) -> str:
        """Control light brightness, turn on/off, or recall scenes.

        This tool sends DALI lighting commands to any target in the ZenControl system.

        Args:
            target_type: What to control. One of: site, floor, group, device, ecg, gateway, zone, control_system, tenancy, device_location, ecd, map.
            target_id: The target's ID. Format varies by target type:
                - Sites/floors/maps/tenancies/device_locations: UUID string
                - Gateways: 'gtin-serial' (e.g., '565343546-AABBCCDD')
                - Groups: 'gtin-serial-groupNumber' (e.g., '565343546-AABBCCDD-5')
                - Devices: 'gatewayGtin-gatewaySerial-busUnitGtin-busUnitSerial'
                - ECGs/ECDs: 'gatewayGtin-gatewaySerial-busUnitGtin-busUnitSerial-logicalIndex'
                - Zones: 'siteId-zoneId'
            action: The lighting action. One of: 'off', 'on', 'set_level', 'recall_scene', 'dim_up', 'dim_down', 'identify'.
            level: Brightness percentage 0-100 (required for 'set_level' action). Converted to DALI 0-254 internally.
            scene: DALI scene number 0-15 (required for 'recall_scene' action).
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]

        # Scope constraint check
        if error := get_scope_constraint(ctx).validate_target(target_type, target_id):
            return error

        # Validate action
        command_type = _ACTION_MAP.get(action)
        if command_type is None:
            return f"Unknown action '{action}'. Must be one of: {_VALID_ACTIONS}."

        # Validate action-specific parameters
        if action == "set_level":
            if level is None:
                return "The 'level' parameter (0-100) is required for the 'set_level' action."
            if not 0 <= level <= 100:
                return "The 'level' parameter must be between 0 and 100."
        if action == "recall_scene":
            if scene is None:
                return "The 'scene' parameter (0-15) is required for the 'recall_scene' action."
            if not 0 <= scene <= 15:
                return "The 'scene' parameter must be between 0 and 15."

        # Build the DALI command
        cmd_kwargs: dict[str, object] = {"type": command_type}
        if action == "set_level":
            cmd_kwargs["level"] = _pct_to_dali(level)  # type: ignore[arg-type]
        elif action == "recall_scene":
            cmd_kwargs["scene"] = scene

        command = DaliCommand(**cmd_kwargs)  # type: ignore[arg-type]

        # Elicitation guard for broad-scope commands
        if cancelled := await confirm_broad_command(
            ctx, target_type, target_id, action
        ):
            return cancelled

        try:
            result = await api.send_command(target_type, target_id, command)
        except (ValueError, Exception) as exc:
            return f"Error sending command: {exc}"

        return _format_command_result(result, target_type, target_id, action)

    @mcp.tool()
    async def set_colour(
        ctx: Context,
        target_type: str,
        target_id: str,
        mode: str,
        level: int = 100,
        kelvin: int | None = None,
        red: int | None = None,
        green: int | None = None,
        blue: int | None = None,
        white: int | None = None,
        amber: int | None = None,
        freecolour: int | None = None,
    ) -> str:
        """Set the colour of lights using colour temperature or RGBWAF values.

        Args:
            target_type: What to control (same options as control_light).
            target_id: The target's ID (same format as control_light).
            mode: Colour mode. One of: 'temperature', 'rgbwaf'.
            level: Brightness level 0-100% to set alongside colour (default: 100).
            kelvin: Colour temperature in Kelvin (required for 'temperature' mode, e.g., 2700 for warm, 6500 for cool).
            red: Red channel 0-254, or None to leave unchanged (for 'rgbwaf' mode).
            green: Green channel 0-254, or None (for 'rgbwaf' mode).
            blue: Blue channel 0-254, or None (for 'rgbwaf' mode).
            white: White channel 0-254, or None (for 'rgbwaf' mode).
            amber: Amber channel 0-254, or None (for 'rgbwaf' mode).
            freecolour: Free colour channel 0-254, or None (for 'rgbwaf' mode).
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]

        # Scope constraint check
        if error := get_scope_constraint(ctx).validate_target(target_type, target_id):
            return error

        if mode not in ("temperature", "rgbwaf"):
            return "Mode must be 'temperature' or 'rgbwaf'."

        if not 0 <= level <= 100:
            return "The 'level' parameter must be between 0 and 100."

        dali_level = _pct_to_dali(level)

        if mode == "temperature":
            if kelvin is None:
                return "The 'kelvin' parameter is required for 'temperature' mode."
            if kelvin <= 0:
                return "The 'kelvin' value must be a positive integer."
            mirek = round(1_000_000 / kelvin)
            command = DaliCommand(
                type=DaliCommandType.COLOUR_TEMPERATURE,
                temperature=mirek,
                level=dali_level,
            )
        else:
            # RGBWAF mode: use 255 as "no change" sentinel for unset channels
            no_change = 255
            rgbwaf = [
                red if red is not None else no_change,
                green if green is not None else no_change,
                blue if blue is not None else no_change,
                white if white is not None else no_change,
                amber if amber is not None else no_change,
                freecolour if freecolour is not None else no_change,
            ]
            command = DaliCommand(
                type=DaliCommandType.COLOUR_RGBWAF,
                rgbwaf=rgbwaf,
                control=no_change,
                level=dali_level,
            )

        action_desc = (
            f"colour temperature {kelvin}K"
            if mode == "temperature"
            else "RGBWAF colour"
        )

        # Elicitation guard for broad-scope commands
        if cancelled := await confirm_broad_command(
            ctx, target_type, target_id, action_desc
        ):
            return cancelled

        try:
            result = await api.send_command(target_type, target_id, command)
        except (ValueError, Exception) as exc:
            return f"Error sending colour command: {exc}"

        return _format_command_result(result, target_type, target_id, action_desc)
