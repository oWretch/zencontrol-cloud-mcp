"""Shared helpers for MCP tool safety guards."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastmcp.server.elicitation import AcceptedElicitation

if TYPE_CHECKING:
    from fastmcp import Context

from zencontrol_mcp.scope import ScopeConstraint

logger = logging.getLogger(__name__)

# Target types that affect many devices and warrant user confirmation
_BROAD_SCOPES = frozenset({"site", "tenancy", "floor"})


def get_scope_constraint(ctx: Context) -> ScopeConstraint:
    """Get the ScopeConstraint from the tool context."""
    return ctx.lifespan_context["scope"]


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
