"""MCP tools for managing the operational scope constraint."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_mcp.api.rest import ZenControlAPI
from zencontrol_mcp.scope import ScopeConstraint


def register(mcp: FastMCP) -> None:
    """Register scope management tools with the FastMCP server."""

    @mcp.tool()
    async def set_scope(ctx: Context, site_id: str) -> str:
        """Restrict all operations to a specific site.

        Once set, tools will refuse requests targeting other sites.
        This is a best-effort safety guardrail for multi-site deployments.
        Sub-site resources (floors, gateways, devices) are not validated
        because determining their parent site would require extra API calls.

        Args:
            site_id: The UUID of the site to scope to. Must be a valid, accessible site.
        """
        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        # Validate the site exists before setting scope
        try:
            site = await api.get_site(site_id)
        except Exception as exc:
            return f"Cannot set scope: failed to verify site {site_id} — {exc}"

        name = site.name or site_id
        scope.set_site(site_id)
        return f"Scope set to site '{name}' ({site_id}). Operations targeting other sites will be blocked."

    @mcp.tool()
    async def get_scope(ctx: Context) -> str:
        """Show the current operational scope constraint.

        Returns whether operations are restricted to a specific site
        or if the server is operating without constraints.
        """
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        if scope.site_id:
            return (
                f"Operations are scoped to site {scope.site_id}.\n"
                f"Tools will block requests targeting other sites.\n"
                f"Use clear_scope to remove this restriction."
            )
        return "No scope constraint is active. All sites are accessible."

    @mcp.tool()
    async def clear_scope(ctx: Context) -> str:
        """Remove the operational scope constraint.

        After clearing, tools will accept requests for any accessible site.
        """
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        if not scope.site_id:
            return "No scope constraint was active."

        prev_site = scope.site_id
        scope.clear()
        return f"Scope constraint removed (was site {prev_site}). All sites are now accessible."
