"""Unit and integration tests for the JWT blacklist.

Covers three layers:

1. ``TokenBlacklist`` API in isolation against a ``FakeRedis``.
2. ``decode_token`` integration: a revoked ``jti`` is rejected with 401.
3. End-to-end through the API: a request with a revoked Bearer token gets
   ``401 invalid_credentials`` with the correct ``code``.
"""

from __future__ import annotations

import time

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import InvalidCredentialsError
from app.core.security import Role, create_access_token, decode_token
from app.services.token_blacklist import (
    KEY_PREFIX,
    TokenBlacklist,
)
from tests._fakes import FakeRedis

# ---------------------------------------------------------------------------
# Layer 1: TokenBlacklist class
# ---------------------------------------------------------------------------


class TestTokenBlacklist:
    def test_unknown_jti_is_not_revoked(self):
        bl = TokenBlacklist(FakeRedis(), fallback="closed")
        assert bl.is_revoked("never-revoked") is False

    def test_revoke_then_is_revoked_returns_true(self):
        fake = FakeRedis()
        bl = TokenBlacklist(fake, fallback="closed")
        bl.revoke("some-jti", exp_unix=int(time.time()) + 60)
        assert bl.is_revoked("some-jti") is True
        assert f"{KEY_PREFIX}some-jti" in fake.keys_snapshot()

    def test_ttl_is_set_to_exp_minus_now(self):
        fake = FakeRedis()
        bl = TokenBlacklist(fake, fallback="closed")
        exp = int(time.time()) + 30
        bl.revoke("ttl-jti", exp_unix=exp)
        ttl = fake.ttl(f"{KEY_PREFIX}ttl-jti")
        # 1s slack for clock + execution latency.
        assert ttl is not None
        assert 28 <= ttl <= 31

    def test_already_expired_token_gets_minimum_one_second_ttl(self):
        # Redis rejects ex=0; we must floor at 1 to keep the call valid.
        # The reported TTL right after a 1-second floor can read as 0 or 1
        # depending on how fast the clock advanced - either is fine, the
        # contract is "neither rejected nor stored as no-expiry".
        fake = FakeRedis()
        bl = TokenBlacklist(fake, fallback="closed")
        bl.revoke("expired-jti", exp_unix=int(time.time()) - 100)
        ttl = fake.ttl(f"{KEY_PREFIX}expired-jti")
        assert ttl is not None  # an expiry WAS configured
        assert 0 <= ttl <= 1


class TestFailClosed:
    def test_redis_down_in_closed_mode_raises(self):
        fake = FakeRedis()
        fake.fail_calls = True
        bl = TokenBlacklist(fake, fallback="closed")
        with pytest.raises(InvalidCredentialsError) as exc_info:
            bl.is_revoked("any-jti")
        assert "temporarily unavailable" in str(exc_info.value).lower()

    def test_revoke_failure_always_propagates(self):
        # Revocation failure is a security incident regardless of fallback:
        # silently dropping a logout request is unacceptable.
        for fallback in ("closed", "open"):
            fake = FakeRedis()
            fake.fail_calls = True
            bl = TokenBlacklist(fake, fallback=fallback)
            with pytest.raises(InvalidCredentialsError):
                bl.revoke("jti", exp_unix=int(time.time()) + 60)


class TestFailOpen:
    def test_redis_down_in_open_mode_returns_false_and_increments_metric(self):
        from app.services.token_blacklist import FAIL_OPEN_HITS

        before = FAIL_OPEN_HITS._value.get()  # type: ignore[attr-defined]
        fake = FakeRedis()
        fake.fail_calls = True
        bl = TokenBlacklist(fake, fallback="open")
        assert bl.is_revoked("any-jti") is False
        after = FAIL_OPEN_HITS._value.get()  # type: ignore[attr-defined]
        assert after == before + 1


# ---------------------------------------------------------------------------
# Layer 2: decode_token integration
# ---------------------------------------------------------------------------


class TestDecodeTokenIntegration:
    def test_valid_token_passes_blacklist(self):
        token = create_access_token(subject=1, role=Role.ADMIN)
        payload = decode_token(token, expected_type="access")
        assert payload.sub == "1"

    def test_revoked_token_is_rejected(self, fake_blacklist: FakeRedis):
        token = create_access_token(subject=1, role=Role.ADMIN)
        # Manually parse jti to revoke it.
        settings = get_settings()
        raw = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        from app.services.token_blacklist import get_blacklist

        get_blacklist().revoke(raw["jti"], exp_unix=raw["exp"])

        with pytest.raises(InvalidCredentialsError) as exc_info:
            decode_token(token, expected_type="access")
        assert "revoked" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Layer 3: end-to-end through the HTTP layer
# ---------------------------------------------------------------------------


class TestRevocationEndToEnd:
    def test_protected_route_rejects_revoked_token(
        self, client, operator_headers, operator_user, fake_blacklist
    ):
        # Sanity: token works.
        ok = client.get("/api/v1/auth/me", headers=operator_headers)
        assert ok.status_code == 200

        # Revoke the jti directly.
        token = operator_headers["Authorization"].removeprefix("Bearer ")
        settings = get_settings()
        raw = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        from app.services.token_blacklist import get_blacklist

        get_blacklist().revoke(raw["jti"], exp_unix=raw["exp"])

        # Same request now 401.
        response = client.get("/api/v1/auth/me", headers=operator_headers)
        assert response.status_code == 401
        assert response.json()["code"] == "invalid_credentials"
        assert "revoked" in response.json()["detail"].lower()

    def test_redis_outage_in_closed_mode_yields_401(
        self, client, operator_headers, operator_user, fake_blacklist
    ):
        # Bring Redis "down" mid-flight.
        fake_blacklist.fail_calls = True
        response = client.get("/api/v1/auth/me", headers=operator_headers)
        assert response.status_code == 401
        # Same code as a real revocation: no info leak about Redis status.
        assert response.json()["code"] == "invalid_credentials"
