"""WebSocket client for ZenControl Live API one-shot subscriptions."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
import websockets.exceptions

logger = logging.getLogger(__name__)

LIVE_WS_URL = "wss://api.zencontrol.com/live/v1/events"


def _extract_handshake_status(exc: Exception) -> int | None:
    """Extract HTTP status code from a websocket handshake exception.

    Different websockets versions expose status in different places:
    - legacy: ``exc.status_code``
    - modern: ``exc.response.status_code`` (InvalidStatus)
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status

    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    # Fallback for unknown exception shapes.
    match = re.search(r"HTTP\s+(\d{3})", str(exc))
    if match:
        return int(match.group(1))

    return None


class LiveAPIError(Exception):
    """Raised when the Live API returns a protocol-level error.

    This includes subscription failures, access-denied responses, and
    stream errors. The ``code`` attribute carries the server error code
    when available (e.g. ``"UNAUTHORIZED"``, ``"FORBIDDEN"``).
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code

    @property
    def is_access_error(self) -> bool:
        """True if this error indicates the client lacks Live API access."""
        return self.code in {
            "UNAUTHORIZED",
            "FORBIDDEN",
            "NOT_AUTHORIZED",
            "ACCESS_DENIED",
        }


class LiveClient:
    """One-shot WebSocket client for ZenControl Live API.

    Connects, subscribes to a stream, collects events for a duration,
    then unsubscribes and disconnects.
    """

    def __init__(self, token_factory: Callable[[], Awaitable[str]]) -> None:
        """Initialise with an async callable that returns a valid access token."""
        self._token_factory = token_factory

    async def subscribe_once(
        self,
        method: str,
        content: dict[str, Any],
        duration: float = 5.0,
        max_events: int = 100,
    ) -> list[dict[str, Any]]:
        """Subscribe to a stream and collect events for a duration.

        Args:
            method: Stream method (e.g., ``"event.ecg.arc-level"``).
            content: Subscription content (e.g., ``{"siteId": "..."}``).
            duration: How long to listen in seconds (default 5).
            max_events: Maximum events to collect before stopping.

        Returns:
            List of event content dicts.

        Raises:
            LiveAPIError: If the server returns an ERROR protocol message,
                or if the WebSocket handshake is rejected (e.g. 401/403).
        """
        token = await self._token_factory()
        # ZenControl Live API requires the access token as a URL query parameter.
        # This is a vendor-mandated API design — the token cannot be passed via
        # an Authorization header. See: https://file.zencontrol.com/liveapi/openapi.json
        # Tokens are short-lived and rotate automatically, which limits exposure.
        url = f"{LIVE_WS_URL}?accessToken={token}"

        events: list[dict[str, Any]] = []
        subscription_id = 1

        try:
            async with websockets.connect(url) as ws:
                # Subscribe
                subscribe_msg = {
                    "version": "1.0",
                    "type": "SUBSCRIBE",
                    "id": subscription_id,
                    "method": method,
                    "content": content,
                }
                await ws.send(json.dumps(subscribe_msg))

                # Wait for START confirmation
                started = False
                try:
                    async with asyncio.timeout(10.0):
                        while not started:
                            raw = await ws.recv()
                            msg = json.loads(raw)
                            if (
                                msg.get("type") == "START"
                                and msg.get("id") == subscription_id
                            ):
                                started = True
                            elif msg.get("type") == "ERROR":
                                error = msg.get("error", {})
                                raise LiveAPIError(
                                    f"Live API subscription error: "
                                    f"[{error.get('code')}] {error.get('message')}",
                                    code=error.get("code"),
                                )
                except TimeoutError:
                    raise LiveAPIError("Timed out waiting for subscription START")

                # Collect events for duration
                try:
                    async with asyncio.timeout(duration):
                        while len(events) < max_events:
                            raw = await ws.recv()
                            msg = json.loads(raw)
                            if (
                                msg.get("type") == "EVENT"
                                and msg.get("id") == subscription_id
                            ):
                                events.append(msg.get("content", {}))
                            elif msg.get("type") == "END":
                                break
                            elif msg.get("type") == "ERROR":
                                error = msg.get("error", {})
                                raise LiveAPIError(
                                    f"Live API stream error: "
                                    f"[{error.get('code')}] {error.get('message')}",
                                    code=error.get("code"),
                                )
                except TimeoutError:
                    pass  # Expected — duration elapsed

                # Unsubscribe
                try:
                    unsubscribe_msg = {
                        "version": "1.0",
                        "type": "UNSUBSCRIBE",
                        "id": subscription_id,
                    }
                    await ws.send(json.dumps(unsubscribe_msg))
                    # Wait briefly for END confirmation
                    async with asyncio.timeout(2.0):
                        while True:
                            raw = await ws.recv()
                            msg = json.loads(raw)
                            if msg.get("type") == "END":
                                break
                except (TimeoutError, websockets.exceptions.ConnectionClosed):
                    pass  # Acceptable — we're done anyway

        except websockets.exceptions.InvalidHandshake as exc:
            # HTTP-level rejection (e.g. 401 Unauthorized, 403 Forbidden)
            status = _extract_handshake_status(exc)
            code = (
                "UNAUTHORIZED"
                if status == 401
                else "FORBIDDEN"
                if status == 403
                else None
            )
            status_text = str(status) if status is not None else "unknown"
            raise LiveAPIError(
                f"Live API connection rejected (HTTP {status_text}): {exc}",
                code=code,
            ) from exc

        return events
