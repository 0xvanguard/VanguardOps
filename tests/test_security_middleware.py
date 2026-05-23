"""End-to-end tests for :class:`SecurityRateLimitMiddleware`.

Exercises the middleware through the real FastAPI app:

* Rate limit triggers a 429 ``rate_limited`` Problem+JSON with
  ``Retry-After`` and ``X-RateLimit-*`` headers, while exempt paths
  (``/livez``, ``/metrics``, ...) bypass the limiter entirely.
* Repeated 401s on ``/auth/login`` activate an IP ban; the next request
  from that IP is short-circuited with 429 ``ip_banned``.
* Repeated 404s activate a scan ban with the same shape.
* ``TRUST_PROXY`` honours ``X-Forwarded-For``; without it, the header
  is ignored so two distinct forwarded-IPs share the limiter pool of
  the actual transport peer.
* CIDR whitelist bypass.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.core.config import get_settings
from app.main import create_app

# ---------------------------------------------------------------------------
# Custom-app helper: the default ``client`` fixture builds the app once with
# the cached settings; here we need to swap settings (per-IP limit, trust
# proxy, whitelist) per test case so we instantiate a small helper that
# rebuilds the app with the desired settings overrides.
# ---------------------------------------------------------------------------


def _build_client(db_session, **overrides):
    """Spin up an isolated TestClient with patched settings.

    ``overrides`` keys are attribute names of :class:`Settings` (e.g.
    ``RATE_LIMIT_LOGIN_PER_IP=2``). They are mutated on the cached
    settings object for the duration of the test.

    Crucially we *rebuild* the rate limiter and the IP banlist after the
    settings are patched: the banlist caches its thresholds at __init__
    time, so without rebuilding, an override like
    ``RATE_LIMIT_AUTH_FAILURE_THRESHOLD=3`` would be silently ignored.
    The autouse ``fake_security_redis`` fixture's underlying ``FakeRedis``
    is preserved so the new banlist reuses the same in-memory store.
    """
    settings = get_settings()
    saved = {k: getattr(settings, k) for k in overrides}
    for k, v in overrides.items():
        object.__setattr__(settings, k, v)

    # Rebuild security singletons against the patched settings.
    from app.services.ip_banlist import IPBanlist, get_banlist, set_banlist
    from app.services.rate_limiter import (
        SlidingWindowRateLimiter,
        get_rate_limiter,
        set_rate_limiter,
    )

    fake_redis = get_rate_limiter()._redis  # type: ignore[attr-defined]
    saved_limiter = get_rate_limiter()
    saved_banlist = get_banlist()
    set_rate_limiter(SlidingWindowRateLimiter(fake_redis, fail_open=True))
    set_banlist(
        IPBanlist(
            fake_redis,
            auth_failure_threshold=settings.RATE_LIMIT_AUTH_FAILURE_THRESHOLD,
            auth_failure_window=settings.RATE_LIMIT_AUTH_FAILURE_WINDOW,
            scan_threshold=settings.RATE_LIMIT_404_THRESHOLD,
            scan_window=settings.RATE_LIMIT_404_WINDOW,
        )
    )

    app = create_app()

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    return _ClientWrapper(
        TestClient(app),
        settings,
        saved,
        restore_limiter=saved_limiter,
        restore_banlist=saved_banlist,
    )


class _ClientWrapper:
    def __init__(
        self,
        client: TestClient,
        settings,
        saved,
        *,
        restore_limiter=None,
        restore_banlist=None,
    ):
        self.client = client
        self._settings = settings
        self._saved = saved
        self._restore_limiter = restore_limiter
        self._restore_banlist = restore_banlist

    def __enter__(self):
        self.client.__enter__()
        return self.client

    def __exit__(self, *args):
        try:
            self.client.__exit__(*args)
        finally:
            for k, v in self._saved.items():
                object.__setattr__(self._settings, k, v)
            if self._restore_limiter is not None:
                from app.services.rate_limiter import set_rate_limiter

                set_rate_limiter(self._restore_limiter)
            if self._restore_banlist is not None:
                from app.services.ip_banlist import set_banlist

                set_banlist(self._restore_banlist)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExemptPaths:
    def test_livez_is_never_rate_limited(self, db_session):
        with _build_client(db_session, RATE_LIMIT_LOGIN_PER_IP=1) as client:
            for _ in range(20):
                r = client.get("/livez")
                assert r.status_code == 200
            assert "X-RateLimit-Limit" not in r.headers


class TestLoginRateLimit:
    def test_login_blocked_after_quota_exhausted(self, db_session):
        with _build_client(
            db_session,
            RATE_LIMIT_LOGIN_PER_IP=2,
            RATE_LIMIT_AUTH_FAILURE_THRESHOLD=999,  # disable banning side-effect
        ) as client:
            for _ in range(2):
                resp = client.post(
                    "/api/v1/auth/login",
                    json={"email": "x@vanguardops.io", "password": "y"},
                )
                # 401 because the user does not exist; ratelimiter still ate the slot.
                assert resp.status_code == 401
                assert resp.headers.get("X-RateLimit-Limit") == "2"

            blocked = client.post(
                "/api/v1/auth/login",
                json={"email": "x@vanguardops.io", "password": "y"},
            )
            assert blocked.status_code == 429
            body = blocked.json()
            assert body["code"] == "rate_limited"
            assert body["scope"] == "auth_login"
            assert int(blocked.headers["Retry-After"]) >= 1

    def test_register_uses_its_own_quota(self, db_session, admin_headers):
        with _build_client(
            db_session,
            RATE_LIMIT_REGISTER_PER_IP=2,
        ) as client:
            payload = {
                "email": "u1@vanguardops.io",
                "password": "Test!2345",
                "role": "viewer",
            }
            r1 = client.post("/api/v1/auth/register", json=payload, headers=admin_headers)
            assert r1.status_code in (201, 401, 409)  # any non-429 is fine
            r2 = client.post(
                "/api/v1/auth/register",
                json={**payload, "email": "u2@vanguardops.io"},
                headers=admin_headers,
            )
            assert r2.status_code in (201, 401, 409)
            blocked = client.post(
                "/api/v1/auth/register",
                json={**payload, "email": "u3@vanguardops.io"},
                headers=admin_headers,
            )
            assert blocked.status_code == 429
            assert blocked.json()["scope"] == "auth_register"


class TestAuthFailureBan:
    def test_repeated_401_activates_ban(self, db_session, fake_security_redis):
        # Threshold of 3, then the next request should be banned outright.
        with _build_client(
            db_session,
            RATE_LIMIT_LOGIN_PER_IP=999,  # avoid hitting rate limit before ban
            RATE_LIMIT_AUTH_FAILURE_THRESHOLD=3,
            RATE_LIMIT_AUTH_FAILURE_WINDOW=300,
        ) as client:
            for _ in range(3):
                r = client.post(
                    "/api/v1/auth/login",
                    json={"email": "x@vanguardops.io", "password": "y"},
                )
                assert r.status_code == 401

            # 4th request: IP is banned, middleware short-circuits before
            # even hitting the route. We send to /auth/me to make sure the
            # ban applies globally, not just to the login endpoint.
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 429
            body = resp.json()
            assert body["code"] == "ip_banned"
            assert body["reason"] == "auth_failures"
            assert int(resp.headers["Retry-After"]) >= 1


class TestScanBan:
    def test_repeated_404_activates_scan_ban(self, db_session):
        with _build_client(
            db_session,
            RATE_LIMIT_API_DEFAULT_PER_IP=999,  # avoid plain rate limit
            RATE_LIMIT_404_THRESHOLD=4,
            RATE_LIMIT_404_WINDOW=60,
        ) as client:
            for path in (
                "/admin/.env",
                "/wp-login.php",
                "/api/v1/does-not-exist",
                "/.git/config",
            ):
                r = client.get(path)
                assert r.status_code == 404

            # 5th request: now banned.
            resp = client.get("/api/v1/auth/me")
            assert resp.status_code == 429
            assert resp.json()["code"] == "ip_banned"
            assert resp.json()["reason"] == "scan_attempt"


class TestTrustProxy:
    def test_x_forwarded_for_ignored_when_trust_proxy_false(self, db_session):
        with _build_client(
            db_session,
            RATE_LIMIT_LOGIN_PER_IP=2,
            RATE_LIMIT_AUTH_FAILURE_THRESHOLD=999,
            TRUST_PROXY=False,
        ) as client:
            # Two distinct claimed IPs, but trust_proxy=False -> they share
            # the transport peer's pool, which is the same. Third call gets
            # 429 even though we claim a brand new IP each time.
            for ip in ("1.1.1.1", "2.2.2.2"):
                r = client.post(
                    "/api/v1/auth/login",
                    json={"email": "x@vanguardops.io", "password": "y"},
                    headers={"X-Forwarded-For": ip},
                )
                assert r.status_code == 401
            blocked = client.post(
                "/api/v1/auth/login",
                json={"email": "x@vanguardops.io", "password": "y"},
                headers={"X-Forwarded-For": "9.9.9.9"},
            )
            assert blocked.status_code == 429

    def test_x_forwarded_for_honoured_when_trust_proxy_true(self, db_session):
        with _build_client(
            db_session,
            RATE_LIMIT_LOGIN_PER_IP=2,
            RATE_LIMIT_AUTH_FAILURE_THRESHOLD=999,
            TRUST_PROXY=True,
        ) as client:
            # Two requests from claimed-IP-A, then one from claimed-IP-B
            # which must NOT be rate-limited because they have separate pools.
            for _ in range(2):
                r = client.post(
                    "/api/v1/auth/login",
                    json={"email": "x@vanguardops.io", "password": "y"},
                    headers={"X-Forwarded-For": "10.0.0.1"},
                )
                assert r.status_code == 401
            blocked_a = client.post(
                "/api/v1/auth/login",
                json={"email": "x@vanguardops.io", "password": "y"},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
            assert blocked_a.status_code == 429

            allowed_b = client.post(
                "/api/v1/auth/login",
                json={"email": "x@vanguardops.io", "password": "y"},
                headers={"X-Forwarded-For": "10.0.0.2"},
            )
            assert allowed_b.status_code == 401  # NOT rate limited


class TestWhitelist:
    def test_whitelisted_ip_is_never_throttled(self, db_session):
        # ``testserver`` reports ``client.host == 'testclient'`` for the
        # transport peer. With TRUST_PROXY=True we can claim an IP inside
        # a whitelisted CIDR.
        with _build_client(
            db_session,
            RATE_LIMIT_LOGIN_PER_IP=1,
            RATE_LIMIT_AUTH_FAILURE_THRESHOLD=2,
            RATE_LIMIT_WHITELIST_CIDRS=["10.0.0.0/8"],
            TRUST_PROXY=True,
        ) as client:
            for _ in range(10):
                r = client.post(
                    "/api/v1/auth/login",
                    json={"email": "x@vanguardops.io", "password": "y"},
                    headers={"X-Forwarded-For": "10.50.50.50"},
                )
                # Always 401, never 429 - whitelisted IP bypasses both
                # rate limiter and banlist.
                assert r.status_code == 401


@pytest.mark.parametrize("path", ["/livez", "/readyz", "/metrics", "/health"])
def test_health_endpoints_are_exempt(client, path):
    # Hit each many times; never throttled.
    for _ in range(15):
        r = client.get(path)
        assert r.status_code == 200, path
