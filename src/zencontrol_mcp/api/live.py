"""WebSocket client for ZenControl Live API one-shot subscriptions."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

logger = logging.getLogger(__name__)

LIVE_WS_URL = "wss://api.zencontrol.com/live/v1/events"


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
        """
        token = await self._token_factory()
        url = f"{LIVE_WS_URL}?accessToken={token}"

        events: list[dict[str, Any]] = []
        subscription_id = 1

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
                            raise RuntimeError(
                                f"Live API subscription error: "
                                f"[{error.get('code')}] {error.get('message')}"
                            )
            except TimeoutError:
                raise RuntimeError("Timed out waiting for subscription START")

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
                            logger.warning(
                                "Live API stream error: %s", msg.get("error")
                            )
                            break
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
            except (TimeoutError, websockets.ConnectionClosed):
                pass  # Acceptable — we're done anyway

        return events
