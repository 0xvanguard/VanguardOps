"""Unit tests for :class:`SlidingWindowRateLimiter`.

Covers:

* Within-limit behaviour: ``check`` returns ``allowed=True`` until the
  count hits ``limit``.
* At-limit and beyond: returns ``allowed=False`` with a sane
  ``retry_after_seconds`` derived from the oldest in-window entry.
* Window slide: once the oldest entry leaves the window, calls succeed
  again. Verified with :mod:`freezegun` to avoid flake.
* Scope and identifier isolation.
* Fail-open behaviour when Redis is down.
"""

from __future__ import annotations

import time

from freezegun import freeze_time

from app.services.rate_limiter import (
    KEY_PREFIX,
    SlidingWindowRateLimiter,
)
from tests._fakes import FakeRedis


def _make(fail_open: bool = True) -> tuple[FakeRedis, SlidingWindowRateLimiter]:
    fake = FakeRedis()
    return fake, SlidingWindowRateLimiter(fake, fail_open=fail_open)


class TestUnderLimit:
    def test_first_request_allowed(self):
        _, rl = _make()
        result = rl.check(scope="test", identifier="ip", limit=3, window_seconds=60)
        assert result.allowed is True
        assert result.limit == 3
        assert result.remaining == 2
        assert result.retry_after_seconds == 0

    def test_remaining_decrements(self):
        _, rl = _make()
        for expected_remaining in (2, 1, 0):
            r = rl.check(scope="test", identifier="ip", limit=3, window_seconds=60)
            assert r.allowed is True
            assert r.remaining == expected_remaining


class TestAtAndOverLimit:
    def test_request_at_limit_is_rejected(self):
        _, rl = _make()
        for _ in range(3):
            assert rl.check(scope="t", identifier="ip", limit=3, window_seconds=60).allowed
        rejected = rl.check(scope="t", identifier="ip", limit=3, window_seconds=60)
        assert rejected.allowed is False
        assert rejected.remaining == 0
        assert 1 <= rejected.retry_after_seconds <= 61

    def test_rejected_request_does_not_consume_a_slot(self):
        # Three accepts, one reject. After ``window`` we must accept again
        # *exactly three more times* without the rejected request having
        # poisoned the pool.
        fake, rl = _make()
        with freeze_time("2026-05-23 10:00:00") as clock:
            for _ in range(3):
                rl.check(scope="t", identifier="ip", limit=3, window_seconds=60)
            assert rl.check(scope="t", identifier="ip", limit=3, window_seconds=60).allowed is False
            clock.tick(delta=61)
            for _ in range(3):
                assert rl.check(scope="t", identifier="ip", limit=3, window_seconds=60).allowed
            assert rl.check(scope="t", identifier="ip", limit=3, window_seconds=60).allowed is False


class TestWindowSlide:
    def test_after_window_passes_capacity_returns(self):
        with freeze_time("2026-05-23 10:00:00") as clock:
            _, rl = _make()
            for _ in range(2):
                rl.check(scope="t", identifier="ip", limit=2, window_seconds=10)
            blocked = rl.check(scope="t", identifier="ip", limit=2, window_seconds=10)
            assert blocked.allowed is False

            clock.tick(delta=11)  # cross the window
            after = rl.check(scope="t", identifier="ip", limit=2, window_seconds=10)
            assert after.allowed is True


class TestIsolation:
    def test_different_identifiers_do_not_share_quota(self):
        _, rl = _make()
        for _ in range(3):
            rl.check(scope="t", identifier="ip-a", limit=3, window_seconds=60)
        # ip-a is at the limit.
        assert rl.check(scope="t", identifier="ip-a", limit=3, window_seconds=60).allowed is False
        # ip-b is fresh.
        assert rl.check(scope="t", identifier="ip-b", limit=3, window_seconds=60).allowed is True

    def test_different_scopes_do_not_share_quota(self):
        _, rl = _make()
        for _ in range(3):
            rl.check(scope="login", identifier="ip", limit=3, window_seconds=60)
        assert rl.check(scope="login", identifier="ip", limit=3, window_seconds=60).allowed is False
        assert rl.check(scope="register", identifier="ip", limit=3, window_seconds=60).allowed is True


class TestStorageContract:
    def test_keys_use_documented_prefix_and_format(self):
        fake, rl = _make()
        rl.check(scope="login", identifier="1.2.3.4", limit=5, window_seconds=60)
        keys = fake.keys_snapshot()
        assert f"{KEY_PREFIX}login:1.2.3.4" in keys

    def test_safety_ttl_is_set_on_active_key(self):
        fake, rl = _make()
        rl.check(scope="login", identifier="1.2.3.4", limit=5, window_seconds=60)
        # The fake stores ZSET TTL via ``expire``; we just assert the key
        # has *a* TTL that is at least the window.
        ttl = fake.ttl(f"{KEY_PREFIX}login:1.2.3.4")
        assert ttl >= 60


class TestFailOpenAndFailClosed:
    def test_redis_outage_with_fail_open_allows_request(self):
        fake, rl = _make(fail_open=True)
        fake.fail_calls = True
        result = rl.check(scope="t", identifier="ip", limit=3, window_seconds=60)
        assert result.allowed is True

    def test_redis_outage_with_fail_closed_denies_request(self):
        fake, rl = _make(fail_open=False)
        fake.fail_calls = True
        result = rl.check(scope="t", identifier="ip", limit=3, window_seconds=60)
        assert result.allowed is False
        assert result.retry_after_seconds == 60


class TestHeaders:
    def test_to_headers_on_allowed_omits_retry_after(self):
        _, rl = _make()
        r = rl.check(scope="t", identifier="ip", limit=5, window_seconds=60)
        headers = r.to_headers()
        assert headers["X-RateLimit-Limit"] == "5"
        assert "Retry-After" not in headers

    def test_to_headers_on_denied_includes_retry_after(self):
        _, rl = _make()
        for _ in range(2):
            rl.check(scope="t", identifier="ip", limit=2, window_seconds=60)
        r = rl.check(scope="t", identifier="ip", limit=2, window_seconds=60)
        headers = r.to_headers()
        assert headers["X-RateLimit-Limit"] == "2"
        assert headers["X-RateLimit-Remaining"] == "0"
        assert int(headers["Retry-After"]) >= 1


def test_zero_limit_always_denies():
    # Edge case: a misconfigured rule must not let traffic through.
    _, rl = _make()
    r = rl.check(scope="t", identifier="ip", limit=0, window_seconds=60)
    assert r.allowed is False
    # And a limit of zero must not be record-of-zero - we still touch
    # a real Redis (or fake) without allocating a member.
    time.sleep(0)  # quiet ruff
