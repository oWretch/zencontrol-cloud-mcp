"""Tests for scope constraints and elicitation guards."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from zencontrol_mcp.scope import ScopeConstraint
from zencontrol_mcp.tools._helpers import confirm_broad_command, get_scope_constraint


# ===========================================================================
# ScopeConstraint unit tests
# ===========================================================================


class TestScopeConstraintInit:
    def test_default_unconstrained(self):
        scope = ScopeConstraint()
        assert scope.site_id is None

    def test_init_with_site(self):
        scope = ScopeConstraint(site_id="abc-123")
        assert scope.site_id == "abc-123"

    def test_set_and_clear(self):
        scope = ScopeConstraint()
        scope.set_site("site-1")
        assert scope.site_id == "site-1"
        scope.clear()
        assert scope.site_id is None


class TestScopeValidateSite:
    def test_unconstrained_allows_any(self):
        scope = ScopeConstraint()
        assert scope.validate_site("any-site") is None

    def test_matching_site_allowed(self):
        scope = ScopeConstraint(site_id="site-1")
        assert scope.validate_site("site-1") is None

    def test_different_site_blocked(self):
        scope = ScopeConstraint(site_id="site-1")
        result = scope.validate_site("site-2")
        assert result is not None
        assert "outside the configured scope" in result
        assert "site-1" in result


class TestScopeValidateScope:
    def test_unconstrained_allows_any(self):
        scope = ScopeConstraint()
        assert scope.validate_scope("site", "any-id") is None

    def test_matching_site_scope_allowed(self):
        scope = ScopeConstraint(site_id="site-1")
        assert scope.validate_scope("site", "site-1") is None

    def test_different_site_scope_blocked(self):
        scope = ScopeConstraint(site_id="site-1")
        result = scope.validate_scope("site", "site-2")
        assert result is not None
        assert "outside" in result

    def test_non_site_scope_always_allowed(self):
        """Sub-site scopes (floor, map, etc.) are not validated."""
        scope = ScopeConstraint(site_id="site-1")
        assert scope.validate_scope("floor", "floor-xyz") is None
        assert scope.validate_scope("gateway", "123-ABC") is None
        assert scope.validate_scope("map", "map-id") is None


class TestScopeValidateTarget:
    def test_unconstrained_allows_any(self):
        scope = ScopeConstraint()
        assert scope.validate_target("site", "any-id") is None

    def test_matching_site_target_allowed(self):
        scope = ScopeConstraint(site_id="site-1")
        assert scope.validate_target("site", "site-1") is None

    def test_different_site_target_blocked(self):
        scope = ScopeConstraint(site_id="site-1")
        result = scope.validate_target("site", "site-2")
        assert result is not None
        assert "outside" in result

    def test_zone_target_validates_embedded_site(self):
        """Zone IDs are 'siteId-zoneId' — the site prefix is validated."""
        scope = ScopeConstraint(site_id="site-1")
        assert scope.validate_target("zone", "site-1-zone-5") is None

    def test_zone_target_wrong_site_blocked(self):
        scope = ScopeConstraint(site_id="site-1")
        result = scope.validate_target("zone", "site-2-zone-5")
        assert result is not None
        assert "does not belong" in result

    def test_non_site_target_always_allowed(self):
        scope = ScopeConstraint(site_id="site-1")
        assert scope.validate_target("group", "gtin-serial-5") is None
        assert scope.validate_target("device", "gtin-serial-gtin2-serial2") is None
        assert scope.validate_target("gateway", "gtin-serial") is None


# ===========================================================================
# Helper: get_scope_constraint
# ===========================================================================


class TestGetScopeConstraint:
    def test_returns_scope_from_context(self):
        scope = ScopeConstraint(site_id="test")
        ctx = MagicMock()
        ctx.lifespan_context = {"scope": scope}
        assert get_scope_constraint(ctx) is scope


# ===========================================================================
# Elicitation guard: confirm_broad_command
# ===========================================================================


class TestConfirmBroadCommand:
    async def test_narrow_scope_skips_elicitation(self):
        """Narrow targets (group, device, etc.) never trigger confirmation."""
        ctx = MagicMock()
        result = await confirm_broad_command(ctx, "group", "gtin-serial-5", "off")
        assert result is None
        # elicit should never be called
        ctx.elicit.assert_not_called()

    async def test_broad_scope_accepted(self):
        """User confirms a broad-scope command."""
        from fastmcp.server.elicitation import AcceptedElicitation

        ctx = MagicMock()
        ctx.elicit = AsyncMock(
            return_value=AcceptedElicitation(action="accept", data=True)
        )
        result = await confirm_broad_command(ctx, "site", "site-1", "off")
        assert result is None
        ctx.elicit.assert_called_once()

    async def test_broad_scope_declined(self):
        """User declines a broad-scope command."""
        from mcp.server.elicitation import DeclinedElicitation

        ctx = MagicMock()
        ctx.elicit = AsyncMock(return_value=DeclinedElicitation(action="decline"))
        result = await confirm_broad_command(ctx, "site", "site-1", "off")
        assert result is not None
        assert "cancelled" in result.lower()

    async def test_broad_scope_cancelled(self):
        """User cancels a broad-scope command."""
        from mcp.server.elicitation import CancelledElicitation

        ctx = MagicMock()
        ctx.elicit = AsyncMock(return_value=CancelledElicitation(action="cancel"))
        result = await confirm_broad_command(ctx, "floor", "floor-1", "set_level")
        assert result is not None
        assert "cancelled" in result.lower()

    async def test_broad_scope_accepted_false(self):
        """User submits the form but with False → treated as cancel."""
        from fastmcp.server.elicitation import AcceptedElicitation

        ctx = MagicMock()
        ctx.elicit = AsyncMock(
            return_value=AcceptedElicitation(action="accept", data=False)
        )
        result = await confirm_broad_command(ctx, "tenancy", "t-1", "on")
        assert result is not None
        assert "cancelled" in result.lower()

    async def test_elicitation_unsupported_proceeds(self):
        """If client doesn't support elicitation, proceed with a warning."""
        ctx = MagicMock()
        ctx.elicit = AsyncMock(side_effect=Exception("not supported"))
        result = await confirm_broad_command(ctx, "site", "site-1", "off")
        assert result is None  # Should proceed, not block

    async def test_elicitation_message_includes_details(self):
        """The confirmation message includes the action and target details."""
        from fastmcp.server.elicitation import AcceptedElicitation

        ctx = MagicMock()
        ctx.elicit = AsyncMock(
            return_value=AcceptedElicitation(action="accept", data=True)
        )
        await confirm_broad_command(ctx, "site", "site-abc", "dim_down")
        call_args = ctx.elicit.call_args
        message = call_args.args[0]
        assert "dim_down" in message
        assert "site" in message
        assert "site-abc" in message


# ===========================================================================
# Scope tools integration tests
# ===========================================================================


class TestResolveSiteIdentifier:
    """Tests for ZenControlAPI.resolve_site_identifier."""

    @staticmethod
    def _make_site(site_id: str, tag: str | None = None, name: str | None = None):
        site = MagicMock()
        site.site_id = site_id
        site.tag = tag
        site.name = name
        return site

    @pytest.mark.asyncio
    async def test_resolves_uuid_directly(self):
        from zencontrol_mcp.api.rest import ZenControlAPI

        api = MagicMock(spec=ZenControlAPI)
        site = self._make_site("3b5b2c02-0e43-423f-9719-758ab3fcb456", tag="hq")
        api.get_site = AsyncMock(return_value=site)
        api.list_sites = AsyncMock(return_value=[])

        result = await ZenControlAPI.resolve_site_identifier(
            api, "3b5b2c02-0e43-423f-9719-758ab3fcb456"
        )
        api.get_site.assert_called_once_with("3b5b2c02-0e43-423f-9719-758ab3fcb456")
        api.list_sites.assert_not_called()
        assert result is site

    @pytest.mark.asyncio
    async def test_resolves_by_tag(self):
        from zencontrol_mcp.api.rest import ZenControlAPI

        api = MagicMock(spec=ZenControlAPI)
        site_a = self._make_site("uuid-a", tag="alpha-site", name="Alpha Site")
        site_b = self._make_site("uuid-b", tag="beta-site", name="Beta Site")
        api.list_sites = AsyncMock(return_value=[site_a, site_b])

        result = await ZenControlAPI.resolve_site_identifier(api, "beta-site")
        api.get_site.assert_not_called()
        assert result is site_b

    @pytest.mark.asyncio
    async def test_resolves_by_name_case_insensitive(self):
        from zencontrol_mcp.api.rest import ZenControlAPI

        api = MagicMock(spec=ZenControlAPI)
        site = self._make_site("uuid-x", tag=None, name="Brown Home")
        api.list_sites = AsyncMock(return_value=[site])

        result = await ZenControlAPI.resolve_site_identifier(api, "brown home")
        assert result is site

    @pytest.mark.asyncio
    async def test_tag_match_precedes_name_match(self):
        from zencontrol_mcp.api.rest import ZenControlAPI

        api = MagicMock(spec=ZenControlAPI)
        # site_a.name happens to equal identifier, but site_b.tag is exact match
        site_a = self._make_site("uuid-a", tag=None, name="brown-home")
        site_b = self._make_site("uuid-b", tag="brown-home", name="Brown Home")
        api.list_sites = AsyncMock(return_value=[site_a, site_b])

        result = await ZenControlAPI.resolve_site_identifier(api, "brown-home")
        assert result is site_b

    @pytest.mark.asyncio
    async def test_raises_value_error_if_not_found(self):
        from zencontrol_mcp.api.rest import ZenControlAPI

        api = MagicMock(spec=ZenControlAPI)
        api.list_sites = AsyncMock(return_value=[])

        with pytest.raises(ValueError, match="No site found matching"):
            await ZenControlAPI.resolve_site_identifier(api, "nonexistent-tag")


class TestScopeTools:
    """Test the set_scope / get_scope / clear_scope tools."""

    @staticmethod
    async def _get_tool_fn(name: str):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.scope import register

        mcp = FastMCP("test")
        register(mcp)
        tool = await mcp._get_tool(name)
        assert tool is not None, f"Tool '{name}' not found"
        return tool.fn

    async def test_get_scope_unconstrained(self):
        fn = await self._get_tool_fn("get_scope")
        ctx = MagicMock()
        ctx.lifespan_context = {"scope": ScopeConstraint()}
        result = await fn(ctx=ctx)
        assert "No scope constraint" in result

    async def test_get_scope_constrained(self):
        fn = await self._get_tool_fn("get_scope")
        ctx = MagicMock()
        scope = ScopeConstraint()
        scope.set_site("s-1", tag="my-site", name="My Site")
        ctx.lifespan_context = {"scope": scope}
        result = await fn(ctx=ctx)
        assert "my-site" in result
        assert "scoped" in result.lower()

    async def test_set_scope_success(self):
        fn = await self._get_tool_fn("set_scope")
        api = MagicMock()
        site_obj = MagicMock()
        site_obj.name = "HQ Office"
        site_obj.tag = "hq-office"
        site_obj.site_id = "site-uuid-1"
        api.resolve_site_identifier = AsyncMock(return_value=site_obj)
        scope = ScopeConstraint()
        ctx = MagicMock()
        ctx.lifespan_context = {"api": api, "scope": scope}

        result = await fn(ctx=ctx, site_identifier="hq-office")
        assert "hq-office" in result
        assert scope.site_id == "site-uuid-1"
        assert scope._site_tag == "hq-office"

    async def test_set_scope_by_uuid(self):
        fn = await self._get_tool_fn("set_scope")
        api = MagicMock()
        site_obj = MagicMock()
        site_obj.name = "HQ Office"
        site_obj.tag = "hq-office"
        site_obj.site_id = "3b5b2c02-0e43-423f-9719-758ab3fcb456"
        api.resolve_site_identifier = AsyncMock(return_value=site_obj)
        scope = ScopeConstraint()
        ctx = MagicMock()
        ctx.lifespan_context = {"api": api, "scope": scope}

        result = await fn(
            ctx=ctx, site_identifier="3b5b2c02-0e43-423f-9719-758ab3fcb456"
        )
        assert "hq-office" in result
        assert scope.site_id == "3b5b2c02-0e43-423f-9719-758ab3fcb456"

    async def test_set_scope_invalid_site(self):
        fn = await self._get_tool_fn("set_scope")
        api = MagicMock()
        api.resolve_site_identifier = AsyncMock(
            side_effect=ValueError("No site found matching 'bad-id'")
        )
        scope = ScopeConstraint()
        ctx = MagicMock()
        ctx.lifespan_context = {"api": api, "scope": scope}

        result = await fn(ctx=ctx, site_identifier="bad-id")
        assert "Cannot set scope" in result
        assert scope.site_id is None  # Unchanged

    async def test_clear_scope(self):
        fn = await self._get_tool_fn("clear_scope")
        scope = ScopeConstraint(site_id="s-1")
        ctx = MagicMock()
        ctx.lifespan_context = {"scope": scope}

        result = await fn(ctx=ctx)
        assert "removed" in result.lower()
        assert scope.site_id is None

    async def test_clear_scope_when_unconstrained(self):
        fn = await self._get_tool_fn("clear_scope")
        ctx = MagicMock()
        ctx.lifespan_context = {"scope": ScopeConstraint()}

        result = await fn(ctx=ctx)
        assert "No scope constraint was active" in result


# ===========================================================================
# Integration: scope enforcement in tools
# ===========================================================================


class TestScopeEnforcementInTools:
    """Verify that tools respect scope constraints."""

    @staticmethod
    def _ctx_with_scope(api_mock=None, scope_site: str | None = None):
        if api_mock is None:
            api_mock = MagicMock()
            api_mock.send_command = AsyncMock(return_value=None)
            api_mock.list_sites = AsyncMock(return_value=[])
            api_mock.list_groups = AsyncMock(return_value=[])
        scope = ScopeConstraint(site_id=scope_site)
        ctx = MagicMock()
        ctx.lifespan_context = {"api": api_mock, "scope": scope}
        return ctx

    async def test_control_light_blocks_wrong_site(self):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.control import register

        mcp = FastMCP("test")
        register(mcp)
        fn = (await mcp._get_tool("control_light")).fn

        ctx = self._ctx_with_scope(scope_site="allowed-site")
        result = await fn(
            ctx=ctx,
            target_type="site",
            target_id="other-site",
            action="off",
        )
        assert "outside" in result

    async def test_control_light_allows_matching_site(self):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.control import register

        mcp = FastMCP("test")
        register(mcp)
        fn = (await mcp._get_tool("control_light")).fn

        # Mock elicitation to auto-accept
        from fastmcp.server.elicitation import AcceptedElicitation

        ctx = self._ctx_with_scope(scope_site="the-site")
        ctx.elicit = AsyncMock(
            return_value=AcceptedElicitation(action="accept", data=True)
        )
        result = await fn(
            ctx=ctx,
            target_type="site",
            target_id="the-site",
            action="off",
        )
        assert "outside" not in result

    async def test_list_groups_blocks_wrong_site_scope(self):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.devices import register

        mcp = FastMCP("test")
        register(mcp)
        fn = (await mcp._get_tool("list_groups")).fn

        ctx = self._ctx_with_scope(scope_site="allowed")
        result = await fn(ctx=ctx, scope_type="site", scope_id="other")
        assert "outside" in result

    async def test_list_groups_allows_non_site_scope(self):
        from fastmcp import FastMCP

        from zencontrol_mcp.tools.devices import register

        mcp = FastMCP("test")
        register(mcp)
        fn = (await mcp._get_tool("list_groups")).fn

        ctx = self._ctx_with_scope(scope_site="allowed")
        result = await fn(ctx=ctx, scope_type="floor", scope_id="any-floor")
        # Should proceed (not blocked), even though floor isn't validated
        assert "outside" not in result
