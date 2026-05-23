"""Redis-backed JWT blacklist with fail-closed semantics.

Design (see ADR-007 for the full rationale):

* **Storage:** Redis DB ``/2``, segregated from the Celery broker (``/0``)
  and result backend (``/1``) so a routine ``FLUSHDB`` on the queue cannot
  invalidate every active session.
* **TTL:** each entry's TTL is ``exp - now`` seconds, so the row evicts
  itself precisely when the token would have expired anyway. Memory is
  bounded by the number of *outstanding* tokens, not by the total number
  ever issued.
* **Fail-closed by default:** when Redis is unreachable, ``is_revoked``
  re-raises the underlying ``RedisError`` and the caller treats it as a
  refusal. The escape hatch is the ``JWT_BLACKLIST_ON_REDIS_FAILURE``
  setting (``closed`` | ``open``); flipping to ``open`` lets the API stay
  up at the cost of honouring tokens we cannot verify.
* **Observability:** Prometheus counters track every Redis error, every
  fail-open fallback, and every successful revocation.

This module is **synchronous** because the FastAPI handlers it backs are
sync; the Redis client is the standard ``redis-py`` Redis class. We
configure short timeouts (~1s) so a partitioned Redis cannot block a
request thread for more than a second.
"""

from __future__ import annotations

import time
from typing import Literal, Protocol

from prometheus_client import Counter
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.exceptions import InvalidCredentialsError
from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

REVOCATIONS = Counter(
    "auth_blacklist_revocations_total",
    "JWT revocations written to the blacklist (successful).",
)

REDIS_ERRORS = Counter(
    "auth_blacklist_redis_errors_total",
    "Failures contacting the Redis-backed JWT blacklist.",
    labelnames=("operation",),
)

FAIL_OPEN_HITS = Counter(
    "auth_blacklist_fail_open_total",
    "Token-decode requests that proceeded despite Redis being unreachable "
    "because JWT_BLACKLIST_ON_REDIS_FAILURE=open.",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


KEY_PREFIX = "jwt:blacklist:"


class _RedisLike(Protocol):
    """Subset of the redis-py interface we actually use.

    Keeping this narrow lets tests inject a tiny in-memory fake without
    pulling in ``fakeredis``.
    """

    def exists(self, key: str) -> int: ...
    def set(self, key: str, value: str, ex: int | None = None) -> object: ...
    def ping(self) -> bool: ...
    def delete(self, *keys: str) -> int: ...


class TokenBlacklist:
    """Thin wrapper around a ``_RedisLike`` client.

    Stateless aside from the injected client and policy. Safe to share
    across threads (the underlying ``Redis`` connection pool is).
    """

    def __init__(
        self,
        redis_client: _RedisLike,
        *,
        fallback: Literal["closed", "open"] = "closed",
    ) -> None:
        self._redis = redis_client
        self._fallback = fallback

    @property
    def fallback(self) -> Literal["closed", "open"]:
        return self._fallback

    def is_revoked(self, jti: str) -> bool:
        """Return ``True`` iff ``jti`` is on the blacklist.

        On Redis failure the behaviour depends on the configured fallback:

        * ``closed`` (default): re-raise as :class:`InvalidCredentialsError`
          so the HTTP layer answers 401. The Prometheus error counter is
          incremented so dashboards can pick the incident up.
        * ``open``: log + increment the fail-open counter and return
          ``False``. The token is honoured for the rest of its TTL.
        """
        try:
            return self._redis.exists(_key(jti)) > 0
        except RedisError as exc:
            REDIS_ERRORS.labels(operation="exists").inc()
            logger.warning(
                "auth_blacklist_redis_error",
                operation="exists",
                error=str(exc),
                fallback=self._fallback,
            )
            if self._fallback == "open":
                FAIL_OPEN_HITS.inc()
                return False
            raise InvalidCredentialsError(
                "Token verification temporarily unavailable"
            ) from exc

    def revoke(self, jti: str, exp_unix: int) -> None:
        """Mark ``jti`` as revoked until its natural expiry.

        ``ttl = max(1, exp_unix - now)`` so an already-expired token still
        gets a 1-second placeholder rather than a permanent entry. Redis
        rejects ``ex=0`` so the floor of 1 is required.
        """
        ttl = max(1, exp_unix - int(time.time()))
        try:
            self._redis.set(_key(jti), "1", ex=ttl)
            REVOCATIONS.inc()
        except RedisError as exc:
            REDIS_ERRORS.labels(operation="set").inc()
            logger.error(
                "auth_blacklist_revoke_failed",
                jti=jti,
                error=str(exc),
            )
            # Surfacing as 503-ish 401 so clients retry. We do not silently
            # drop revocations even in fail-open mode: a missed revocation
            # is a security incident.
            raise InvalidCredentialsError(
                "Could not record token revocation; please retry"
            ) from exc

    def ping(self) -> bool:
        """Used by the readiness probe (see ``app/api/endpoints/health.py``)."""
        return bool(self._redis.ping())


def _key(jti: str) -> str:
    return f"{KEY_PREFIX}{jti}"


# ---------------------------------------------------------------------------
# Module-level singleton with explicit init / override hooks
# ---------------------------------------------------------------------------

_blacklist: TokenBlacklist | None = None


def get_blacklist() -> TokenBlacklist:
    """Return the process-wide blacklist, creating it on first call."""
    global _blacklist
    if _blacklist is None:
        settings = get_settings()
        client = Redis.from_url(
            settings.REDIS_BLACKLIST_URL,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            decode_responses=False,
            health_check_interval=30,
        )
        _blacklist = TokenBlacklist(
            client,
            fallback=settings.JWT_BLACKLIST_ON_REDIS_FAILURE,
        )
    return _blacklist


def set_blacklist(blacklist: TokenBlacklist | None) -> None:
    """Override the process-wide blacklist.

    Tests use this to swap in a deterministic fake. Production code must
    not call this. Pass ``None`` to clear and force re-initialization on
    the next ``get_blacklist()`` call.
    """
    global _blacklist
    _blacklist = blacklist
