"""Encrypted local token storage for ZenControl OAuth tokens (stdio mode)."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import secrets
import time
import webbrowser
from asyncio import Event, start_server
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import platformdirs
from cryptography.fernet import Fernet, InvalidToken

from zencontrol_mcp.auth.oauth import (
    DEFAULT_REDIRECT_URI,
    build_authorize_url,
    exchange_code,
    generate_pkce_pair,
    refresh_access_token,
)

logger = logging.getLogger(__name__)

_CALLBACK_HTML = (
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: text/html; charset=utf-8\r\n"
    "Connection: close\r\n\r\n"
    "<html><body><h1>Authentication successful</h1>"
    "<p>You can close this window.</p></body></html>"
)

_ERROR_HTML = (
    "HTTP/1.1 400 Bad Request\r\n"
    "Content-Type: text/html; charset=utf-8\r\n"
    "Connection: close\r\n\r\n"
    "<html><body><h1>Authentication failed</h1>"
    "<p>{error}</p></body></html>"
)

# Buffer in seconds before actual expiry to trigger a refresh
_EXPIRY_BUFFER = 60


class TokenStore:
    """Encrypted local token storage using platform-appropriate directories.

    Storage locations:
      macOS:   ~/Library/Application Support/zencontrol-mcp/tokens.enc
      Linux:   ~/.local/share/zencontrol-mcp/tokens.enc
      Windows: C:\\Users\\<user>\\AppData\\Local\\zencontrol-mcp\\tokens.enc
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str = DEFAULT_REDIRECT_URI,
        token_path: Path | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

        token_dir = (
            token_path.parent
            if token_path is not None
            else Path(platformdirs.user_data_dir("zencontrol-mcp"))
        )
        self.token_path = (
            token_path if token_path is not None else token_dir / "tokens.enc"
        )
        self.key_path = token_dir / "keys.key"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_valid_token(self) -> str:
        """Return a valid access token, refreshing or re-authenticating as needed."""
        tokens = self._load_tokens()

        if tokens is None:
            logger.info("No stored tokens found — starting interactive authentication")
            tokens = await self._authenticate_interactive()
            return tokens["access_token"]

        if self._is_expired(tokens):
            logger.info("Access token expired — attempting refresh")
            try:
                tokens = await self._refresh_tokens(tokens)
                return tokens["access_token"]
            except Exception:
                logger.warning(
                    "Token refresh failed — falling back to interactive auth",
                    exc_info=True,
                )
                tokens = await self._authenticate_interactive()
                return tokens["access_token"]

        return tokens["access_token"]

    # ------------------------------------------------------------------
    # Interactive browser-based auth
    # ------------------------------------------------------------------

    async def _authenticate_interactive(self) -> dict:
        """Run the full OAuth authorization-code flow with PKCE via the browser."""
        code_verifier, code_challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(32)

        authorize_url = build_authorize_url(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            state=state,
            code_challenge=code_challenge,
        )

        parsed_redirect = urlparse(self.redirect_uri)
        port = parsed_redirect.port or 9000
        callback_path = parsed_redirect.path or "/callback"

        received_code: str | None = None
        received_state: str | None = None
        error_message: str | None = None
        callback_event = Event()

        async def _handle_connection(
            reader,
            writer,  # noqa: ANN001
        ) -> None:
            nonlocal received_code, received_state, error_message
            try:
                raw = await reader.readuntil(b"\r\n\r\n")
                request_line = raw.split(b"\r\n")[0].decode()
                # e.g. "GET /callback?code=abc&state=xyz HTTP/1.1"
                parts = request_line.split(" ")
                if len(parts) < 2:
                    writer.write(_ERROR_HTML.format(error="Malformed request").encode())
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                    return  # Don't fire the event — wrong/malformed request

                request_path = parts[1]
                parsed = urlparse(request_path)

                if parsed.path != callback_path:
                    writer.write(_ERROR_HTML.format(error="Unexpected path").encode())
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                    return  # Don't fire the event — browser preconnect etc.

                qs = parse_qs(parsed.query)

                if "error" in qs:
                    error_message = qs["error"][0]  # raw, for the RuntimeError below
                    writer.write(
                        _ERROR_HTML.format(error=html.escape(error_message)).encode()
                    )
                elif qs.get("code") and qs.get("state"):
                    received_code = qs["code"][0]
                    received_state = qs["state"][0]
                    writer.write(_CALLBACK_HTML.encode())
                else:
                    # /callback arrived but with neither code+state nor an error —
                    # treat as malformed (e.g. browser favicon fetch on the callback path).
                    writer.write(
                        _ERROR_HTML.format(
                            error="Missing required callback parameters"
                        ).encode()
                    )
                    await writer.drain()
                    writer.close()
                    await writer.wait_closed()
                    return  # Don't fire the event

                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except Exception:
                logger.debug("Error in OAuth callback handler", exc_info=True)
                try:
                    writer.close()
                except Exception:
                    pass
                return  # Don't fire the event on unexpected I/O errors

            # Only reached when we have a real OAuth result (code or error).
            callback_event.set()

        server = await start_server(_handle_connection, "127.0.0.1", port)

        logger.info("Opening browser for ZenControl authorization")
        webbrowser.open(authorize_url)

        try:
            async with asyncio.timeout(300):
                await callback_event.wait()
        except TimeoutError:
            raise RuntimeError(
                "No stored credentials found and interactive authentication timed out "
                "after 5 minutes. Run the server once in a terminal to complete the "
                "OAuth login flow before connecting from a headless environment:\n"
                "  zencontrol-mcp"
            ) from None
        finally:
            server.close()
            await server.wait_closed()

        if error_message:
            raise RuntimeError(f"OAuth authorization failed: {error_message}")

        if received_code is None:
            raise RuntimeError("No authorization code received in callback")

        if received_state != state:
            raise RuntimeError(
                "OAuth state mismatch — possible CSRF attack. "
                f"Expected {state!r}, got {received_state!r}"
            )

        tokens = await exchange_code(
            client_id=self.client_id,
            client_secret=self.client_secret,
            code=received_code,
            redirect_uri=self.redirect_uri,
            code_verifier=code_verifier,
        )

        tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)

        self._save_tokens(tokens)
        logger.info("Authentication successful — tokens saved")
        return tokens

    # ------------------------------------------------------------------
    # Token refresh
    # ------------------------------------------------------------------

    async def _refresh_tokens(self, tokens: dict) -> dict:
        """Refresh the access token and persist the updated token set."""
        new_tokens = await refresh_access_token(
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=tokens["refresh_token"],
        )
        new_tokens["expires_at"] = time.time() + new_tokens.get("expires_in", 3600)
        # Preserve the refresh token if the provider didn't issue a new one
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = tokens["refresh_token"]
        self._save_tokens(new_tokens)
        logger.info("Tokens refreshed and saved")
        return new_tokens

    # ------------------------------------------------------------------
    # Encrypted persistence
    # ------------------------------------------------------------------

    def _save_tokens(self, tokens: dict) -> None:
        """Encrypt and write tokens to disk."""
        key = self._get_or_create_key()
        fernet = Fernet(key)
        data = json.dumps(tokens).encode()
        encrypted = fernet.encrypt(data)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_bytes(encrypted)

    def _load_tokens(self) -> dict | None:
        """Read and decrypt tokens from disk. Returns None on any failure."""
        if not self.token_path.exists():
            return None
        try:
            key = self._get_or_create_key()
            fernet = Fernet(key)
            encrypted = self.token_path.read_bytes()
            data = fernet.decrypt(encrypted)
            return json.loads(data)
        except (InvalidToken, json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load stored tokens: %s", exc)
            return None

    def _get_or_create_key(self) -> bytes:
        """Load or generate the Fernet encryption key."""
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        if self.key_path.exists():
            key = self.key_path.read_bytes().strip()
            if self.key_path.stat().st_mode & 0o077:
                logger.warning(
                    "Encryption key at %s has overly permissive file permissions. "
                    "Run: chmod 600 %s",
                    self.key_path,
                    self.key_path,
                )
            return key
        key = Fernet.generate_key()
        self.key_path.write_bytes(key)
        self.key_path.chmod(0o600)
        logger.info("Generated new encryption key at %s", self.key_path)
        return key

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_expired(self, tokens: dict) -> bool:
        """Check whether the access token is expired (with a 60 s buffer)."""
        expires_at = tokens.get("expires_at", 0)
        return time.time() >= (expires_at - _EXPIRY_BUFFER)
