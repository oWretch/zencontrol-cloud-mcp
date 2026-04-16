"""Shared helpers for MCP tool safety guards."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastmcp.server.elicitation import AcceptedElicitation

if TYPE_CHECKING:
    from fastmcp import Context

    from zencontrol_mcp.api.rest import ZenControlAPI

from zencontrol_mcp.scope import ScopeConstraint

logger = logging.getLogger(__name__)

# Target types that affect many devices and warrant user confirmation
_BROAD_SCOPES = frozenset({"site", "tenancy", "floor"})


def _format_command_result(
    result: object,
    target_type: str,
    target_id: str,
    action: str,
) -> str:
    """Format the result of a send_command call into a human-readable string."""
    if result is not None and hasattr(result, "errors") and result.errors:
        error_lines = [f"  • [{e.error_code}] {e.error_message}" for e in result.errors]
        return (
            f"Command '{action}' sent to {target_type} {target_id} "
            f"with errors:\n" + "\n".join(error_lines)
        )
    return f"Successfully sent '{action}' command to {target_type} {target_id}."


def get_scope_constraint(ctx: Context) -> ScopeConstraint:
    """Get the ScopeConstraint from the tool context."""
    return ctx.lifespan_context["scope"]


async def resolve_scope_id(
    api: ZenControlAPI,
    scope_type: str,
    scope_id: str,
) -> str:
    """Resolve a scope identifier to a canonical UUID.

    For ``scope_type="site"``, the ``scope_id`` may be a UUID, tag (e.g.
    ``"brown-home"``), or site name.  For all other scope types the value
    is returned unchanged (floors, gateways, maps etc. have no tag system).

    Args:
        api: The REST API client.
        scope_type: One of ``"site"``, ``"floor"``, ``"map"``, etc.
        scope_id: The scope identifier to resolve.

    Returns:
        The canonical UUID string for the scope.

    Raises:
        ValueError: If ``scope_type="site"`` and no matching site is found,
            or if a name is ambiguous.
    """
    if scope_type != "site":
        return scope_id
    site = await api.resolve_site_identifier(scope_id)
    return site.site_id or scope_id


async def confirm_broad_command(
    ctx: Context,
    target_type: str,
    target_id: str,
    action_desc: str,
) -> str | None:
    """Ask user to confirm a command that targets a broad scope.

    Returns an error/cancellation string if the command should be aborted,
    or None if it should proceed.

    For narrow-scope targets (group, device, etc.), returns None immediately.
    If the client does not support elicitation, logs a warning and proceeds.
    """
    if target_type not in _BROAD_SCOPES:
        return None

    message = (
        f"This will send '{action_desc}' to all devices in "
        f"{target_type} {target_id}. This could affect many lights. Proceed?"
    )

    try:
        result = await ctx.elicit(
            message,
            response_type=bool,
            response_title="Confirm",
        )
    except Exception:
        logger.warning(
            "Elicitation not available — skipping confirmation for '%s' on %s %s",
            action_desc,
            target_type,
            target_id,
        )
        return None

    if isinstance(result, AcceptedElicitation) and result.data:
        return None

    return "Command cancelled by user."
