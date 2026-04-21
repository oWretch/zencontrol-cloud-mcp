"""Scope constraints for limiting server operations to specific sites."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ScopeConstraint:
    """Best-effort guardrail that restricts operations to a specific site.

    When a site scope is set, tools that accept site IDs directly (like
    ``list_scenes``) or via scope/target parameters will validate that the
    requested site matches the allowed one.

    Sub-site resources (floor, map, gateway, etc.) are **not** validated
    because determining their parent site would require an API call. The
    one exception is zone targets, whose ID format embeds the site ID.

    Note:
        This is a single-session constraint stored in the lifespan context.
        In stdio mode (single client) this works naturally. In multi-user
        HTTP mode, all users share the same constraint.
    """

    def __init__(self, site_id: str | None = None) -> None:
        self._site_id = site_id
        self._site_tag: str | None = None
        self._site_name: str | None = None

    @property
    def site_id(self) -> str | None:
        """The currently constrained site UUID, or None if unconstrained."""
        return self._site_id

    @property
    def display_name(self) -> str | None:
        """Human-readable identifier: tag if available, else name, else UUID."""
        return self._site_tag or self._site_name or self._site_id

    @property
    def site_tag(self) -> str | None:
        """The site's portal tag (URL slug), or None if not set."""
        return self._site_tag

    def set_site(
        self,
        site_id: str,
        *,
        tag: str | None = None,
        name: str | None = None,
    ) -> None:
        """Lock operations to a specific site, optionally storing tag/name for display."""
        self._site_id = site_id
        self._site_tag = tag
        self._site_name = name
        label = tag or name or site_id
        logger.info("Scope set to site %s (%s)", site_id, label)

    def clear(self) -> None:
        """Remove the site scope constraint."""
        prev = self.display_name
        self._site_id = None
        self._site_tag = None
        self._site_name = None
        if prev:
            logger.info("Scope cleared (was %s)", prev)

    def validate_site(self, site_id: str) -> str | None:
        """Check a direct site_id parameter. Returns error string or None."""
        if self._site_id and site_id != self._site_id:
            return (
                f"Site {site_id} is outside the configured scope. "
                f"Allowed site: {self.display_name}. "
                f"Use get_scope to check or clear_scope to remove the constraint."
            )
        return None

    def validate_scope(self, scope_type: str, scope_id: str) -> str | None:
        """Check scope_type/scope_id parameters. Enforces site-level only."""
        if self._site_id and scope_type == "site" and scope_id != self._site_id:
            return (
                f"Site {scope_id} is outside the configured scope. "
                f"Allowed site: {self.display_name}."
            )
        return None

    def validate_target(self, target_type: str, target_id: str) -> str | None:
        """Check command target parameters. Enforces site and zone targets."""
        if not self._site_id:
            return None
        if target_type == "site" and target_id != self._site_id:
            return (
                f"Site {target_id} is outside the configured scope. "
                f"Allowed site: {self.display_name}."
            )
        # Zone IDs are formatted as 'siteId-zoneId' — check site prefix including
        # the delimiter so that site 'abc' does not match zone 'abcdef-zone1'.
        if target_type == "zone" and self._site_id:
            if not target_id.startswith(f"{self._site_id}-"):
                return (
                    f"Zone {target_id} does not belong to the scoped site. "
                    f"Allowed site: {self.display_name}."
                )
        return None
