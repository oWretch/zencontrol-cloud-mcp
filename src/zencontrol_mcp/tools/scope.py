"""MCP tools for managing the operational scope constraint."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_mcp.api.rest import ZenControlAPI
from zencontrol_mcp.scope import ScopeConstraint


def register(mcp: FastMCP) -> None:
    """Register scope management tools with the FastMCP server."""

    @mcp.tool()
    async def set_scope(ctx: Context, site_identifier: str) -> str:
        """Restrict all operations to a specific site.

        Once set, tools will refuse requests targeting other sites.
        This is a best-effort safety guardrail for multi-site deployments.
        Sub-site resources (floors, gateways, devices) are not validated
        because determining their parent site would require extra API calls.

        Not available in HTTP multi-user mode — use the
        ``ZENCONTROL_SCOPE_SITE`` environment variable instead.

        Args:
            site_identifier: The site UUID, tag (portal slug, e.g. 'brown-home'),
                or name (e.g. 'Brown Home'). Tags match the portal URL:
                https://cloud.zencontrol.com/sites/{tag}/
        """
        if ctx.lifespan_context.get("multi_user"):
            return (
                "Scope management is not available in HTTP multi-user mode — "
                "the scope would be shared across all connected users. "
                "Set the ZENCONTROL_SCOPE_SITE environment variable on the "
                "server instead."
            )

        api: ZenControlAPI = ctx.lifespan_context["api"]
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        try:
            site = await api.resolve_site_identifier(site_identifier)
        except Exception as exc:
            return f"Cannot set scope: {exc}"

        scope.set_site(
            site.site_id or site_identifier,
            tag=site.tag,
            name=site.name,
        )

        label = site.tag or site.name or site.site_id or site_identifier
        uuid = site.site_id or "unknown"
        return (
            f"Scope set to site '{label}' ({uuid}).\n"
            f"Operations targeting other sites will be blocked.\n"
            f"Portal URL: https://cloud.zencontrol.com/sites/{site.tag}/"
            if site.tag
            else f"Scope set to site '{label}' ({uuid}). Operations targeting other sites will be blocked."
        )

    @mcp.tool()
    async def get_scope(ctx: Context) -> str:
        """Show the current operational scope constraint.

        Returns whether operations are restricted to a specific site
        or if the server is operating without constraints.
        """
        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        if not scope.site_id:
            return "No scope constraint is active. All sites are accessible."

        lines = [f"Operations are scoped to site '{scope.display_name}'."]
        if scope.site_tag:
            lines.append(
                f"Portal URL: https://cloud.zencontrol.com/sites/{scope.site_tag}/"
            )
        lines.append(f"UUID: {scope.site_id}")
        lines.append("Use clear_scope to remove this restriction.")
        return "\n".join(lines)

    @mcp.tool()
    async def clear_scope(ctx: Context) -> str:
        """Remove the operational scope constraint.

        After clearing, tools will accept requests for any accessible site.

        Not available in HTTP multi-user mode — use the
        ``ZENCONTROL_SCOPE_SITE`` environment variable instead.
        """
        if ctx.lifespan_context.get("multi_user"):
            return (
                "Scope management is not available in HTTP multi-user mode — "
                "the scope would be shared across all connected users. "
                "Set the ZENCONTROL_SCOPE_SITE environment variable on the "
                "server instead."
            )

        scope: ScopeConstraint = ctx.lifespan_context["scope"]

        if not scope.site_id:
            return "No scope constraint was active."

        prev = scope.display_name
        scope.clear()
        return f"Scope constraint removed (was '{prev}'). All sites are now accessible."
