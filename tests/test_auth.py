"""Tests for OAuth and token store modules."""

from __future__ import annotations

import base64
import hashlib
import time

from zencontrol_cloud_mcp.auth.oauth import (
    AUTHORIZE_URL,
    build_authorize_url,
    generate_pkce_pair,
)
from zencontrol_cloud_mcp.auth.token_store import TokenStore

# ---------------------------------------------------------------------------
# build_authorize_url
# ---------------------------------------------------------------------------


class TestBuildAuthorizeUrl:
    def test_basic_url(self):
        url = build_authorize_url(
            client_id="my-client",
            redirect_uri="http://localhost:9000/callback",
            state="random-state",
        )
        assert url.startswith(AUTHORIZE_URL)
        assert "response_type=code" in url
        assert "client_id=my-client" in url
        assert "redirect_uri=http" in url
        assert "state=random-state" in url

    def test_no_pkce_by_default(self):
        url = build_authorize_url(
            client_id="c",
            redirect_uri="http://localhost/cb",
            state="s",
        )
        assert "code_challenge" not in url
        assert "code_challenge_method" not in url

    def test_with_pkce(self):
        url = build_authorize_url(
            client_id="c",
            redirect_uri="http://localhost/cb",
            state="s",
            code_challenge="test-challenge",
        )
        assert "code_challenge=test-challenge" in url
        assert "code_challenge_method=S256" in url


# ---------------------------------------------------------------------------
# generate_pkce_pair
# ---------------------------------------------------------------------------


class TestGeneratePkcePair:
    def test_verifier_length(self):
        verifier, _ = generate_pkce_pair()
        assert 43 <= len(verifier) <= 128

    def test_challenge_is_base64url(self):
        _, challenge = generate_pkce_pair()
        # Should not contain padding
        assert "=" not in challenge
        # Should be valid base64url characters
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in challenge)

    def test_challenge_matches_verifier(self):
        """challenge == base64url(sha256(verifier)) without padding."""
        verifier, challenge = generate_pkce_pair()
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_pairs_are_unique(self):
        v1, c1 = generate_pkce_pair()
        v2, c2 = generate_pkce_pair()
        assert v1 != v2
        assert c1 != c2


# ---------------------------------------------------------------------------
# TokenStore — encrypted persistence
# ---------------------------------------------------------------------------


class TestTokenStorePersistence:
    def test_save_and_load_tokens(self, tmp_path):
        token_path = tmp_path / "tokens.enc"
        store = TokenStore(
            client_id="cid",
            client_secret="csec",
            token_path=token_path,
        )

        tokens = {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_at": time.time() + 3600,
        }
        store._save_tokens(tokens)

        loaded = store._load_tokens()
        assert loaded is not None
        assert loaded["access_token"] == "at-123"
        assert loaded["refresh_token"] == "rt-456"

    def test_load_returns_none_when_no_file(self, tmp_path):
        token_path = tmp_path / "missing.enc"
        store = TokenStore(
            client_id="cid",
            client_secret="csec",
            token_path=token_path,
        )
        assert store._load_tokens() is None

    def test_load_returns_none_for_corrupted_file(self, tmp_path):
        token_path = tmp_path / "tokens.enc"
        # Write garbage data
        token_path.write_bytes(b"not encrypted data at all")

        store = TokenStore(
            client_id="cid",
            client_secret="csec",
            token_path=token_path,
        )
        # The key won't match the data, so decryption should fail gracefully
        assert store._load_tokens() is None


# ---------------------------------------------------------------------------
# TokenStore — _is_expired
# ---------------------------------------------------------------------------


class TestTokenStoreExpiry:
    def _make_store(self, tmp_path) -> TokenStore:
        return TokenStore(
            client_id="cid",
            client_secret="csec",
            token_path=tmp_path / "t.enc",
        )

    def test_not_expired(self, tmp_path):
        store = self._make_store(tmp_path)
        tokens = {"expires_at": time.time() + 3600}
        assert store._is_expired(tokens) is False

    def test_expired_past(self, tmp_path):
        store = self._make_store(tmp_path)
        tokens = {"expires_at": time.time() - 100}
        assert store._is_expired(tokens) is True

    def test_expired_within_buffer(self, tmp_path):
        """Token expiring within the 60s buffer should be treated as expired."""
        store = self._make_store(tmp_path)
        tokens = {"expires_at": time.time() + 30}  # 30s < 60s buffer
        assert store._is_expired(tokens) is True

    def test_missing_expires_at(self, tmp_path):
        """Missing expires_at defaults to 0, which is always expired."""
        store = self._make_store(tmp_path)
        tokens = {}
        assert store._is_expired(tokens) is True

    def test_just_outside_buffer(self, tmp_path):
        """Token expiring in 120s (well outside 60s buffer) should not be expired."""
        store = self._make_store(tmp_path)
        tokens = {"expires_at": time.time() + 120}
        assert store._is_expired(tokens) is False


# ---------------------------------------------------------------------------
# TokenStore — key management
# ---------------------------------------------------------------------------


class TestTokenStoreKeys:
    def test_key_is_created_on_first_access(self, tmp_path):
        token_path = tmp_path / "tokens.enc"
        store = TokenStore(
            client_id="cid",
            client_secret="csec",
            token_path=token_path,
        )
        key = store._get_or_create_key()
        assert len(key) > 0
        assert store.key_path.exists()

    def test_key_is_reused(self, tmp_path):
        token_path = tmp_path / "tokens.enc"
        store = TokenStore(
            client_id="cid",
            client_secret="csec",
            token_path=token_path,
        )
        key1 = store._get_or_create_key()
        key2 = store._get_or_create_key()
        assert key1 == key2
