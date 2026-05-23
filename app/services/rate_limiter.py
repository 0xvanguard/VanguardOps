"""Sliding-window-log rate limiter backed by Redis sorted sets.

Why sliding-window-log
----------------------
The two cheap alternatives have well-known limitations:

* **Fixed windows** allow a burst of ``2 * limit`` at the boundary between
  buckets - an attacker who waits for the window flip can effectively
  double the configured limit.
* **Token bucket** smooths bursts but its behaviour around the limit is
  approximate and difficult to reason about for security-critical
  endpoints like ``/auth/login``.

Sliding-window-log records every accepted request as a member in a sorted
set, scored by its UNIX timestamp. Each call:

1. Drops members older than the window (``ZREMRANGEBYSCORE``).
2. Counts members still inside it (``ZCARD``).
3. If the count is below the limit, records this request and accepts it.
4. Otherwise computes ``retry_after`` from the oldest member in the window
   and rejects.

Memory cost: ``O(limit)`` per ``(scope, identifier)`` pair, capped because
rejected requests are not recorded. A safety ``EXPIRE`` evicts idle keys.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from prometheus_client import Counter

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

RATE_LIMIT_HITS = Counter(
    "rate_limit_hits_total",
    "Requests that hit a rate-limit rule.",
    labelnames=("scope", "outcome"),  # outcome = allowed | denied
)

RATE_LIMIT_REDIS_ERRORS = Counter(
    "rate_limit_redis_errors_total",
    "Failures contacting the Redis-backed rate limiter.",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a single ``check()`` call."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int

    def to_headers(self) -> dict[str, str]:
        """RFC-6585-compatible headers for the HTTP response."""
        out = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
        }
        if not self.allowed:
            out["Retry-After"] = str(self.retry_after_seconds)
        return out


KEY_PREFIX = "rl:"


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window-log rate limiter."""

    def __init__(self, redis_client: Any, *, fail_open: bool = True) -> None:
        self._redis = redis_client
        # ``fail_open=True`` means a Redis outage degrades to "allow" rather
        # than locking every visitor out. Rate limiting is abuse mitigation,
        # not a security boundary - the JWT blacklist already handles
        # security-critical token revocation under fail-closed (ADR-007).
        self._fail_open = fail_open

    def check(
        self,
        *,
        scope: str,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Record this request and tell the caller whether it should proceed."""
        if limit <= 0:
            return RateLimitResult(False, limit, 0, window_seconds)

        key = f"{KEY_PREFIX}{scope}:{identifier}"
        now = time.time()
        cutoff = now - window_seconds

        try:
            self._redis.zremrangebyscore(key, 0, cutoff)
            count = int(self._redis.zcard(key))

            if count >= limit:
                oldest = self._redis.zrange(key, 0, 0, withscores=True)
                if oldest:
                    oldest_score = float(oldest[0][1])
                    retry = max(1, int(oldest_score + window_seconds - now) + 1)
                else:
                    retry = window_seconds
                RATE_LIMIT_HITS.labels(scope=scope, outcome="denied").inc()
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    retry_after_seconds=retry,
                )

            member = uuid.uuid4().hex
            self._redis.zadd(key, {member: now})
            self._redis.expire(key, window_seconds + 60)
            RATE_LIMIT_HITS.labels(scope=scope, outcome="allowed").inc()
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=max(0, limit - count - 1),
                retry_after_seconds=0,
            )
        except Exception as exc:
            RATE_LIMIT_REDIS_ERRORS.inc()
            logger.warning(
                "rate_limit_redis_error",
                scope=scope,
                identifier=identifier,
                error=str(exc),
                fail_open=self._fail_open,
            )
            if self._fail_open:
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=limit,
                    retry_after_seconds=0,
                )
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                retry_after_seconds=window_seconds,
            )


# ---------------------------------------------------------------------------
# Singleton accessor (mirrors the pattern in token_blacklist.py)
# ---------------------------------------------------------------------------

_limiter: SlidingWindowRateLimiter | None = None


def get_rate_limiter() -> SlidingWindowRateLimiter:
    """Return the process-wide rate limiter, creating it on first call."""
    global _limiter
    if _limiter is None:
        from app.services.security_redis import get_security_redis

        _limiter = SlidingWindowRateLimiter(get_security_redis())
    return _limiter


def set_rate_limiter(limiter: SlidingWindowRateLimiter | None) -> None:
    """Override the cached rate limiter (test-only hook)."""
    global _limiter
    _limiter = limiter
