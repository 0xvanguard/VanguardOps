"""Shared Redis client for security state (rate limiting + IP banning).

The blacklist of revoked JWTs lives in DB ``/2`` (see ADR-007). This module
owns DB ``/3`` for ephemeral abuse-mitigation state:

* ``rl:*``       sliding-window-log rate counters (ZSETs)
* ``ban:fails:*`` per-IP failed-auth counters (TTL-scoped INCR)
* ``ban:404:*``   per-IP scanning indicators (TTL-scoped INCR)
* ``ban:count:*`` per-IP ban escalation counter
* ``ban:active:*`` active ban marker, TTL = current ban duration

Keeping these on their own logical DB matches the segregation principle from
ADR-007: a routine ``FLUSHDB`` on the broker (``/0``), result backend
(``/1``), or even on the JWT blacklist (``/2``) cannot accidentally release
banned IPs or wipe rate-limit windows mid-incident.
"""

from __future__ import annotations

from typing import Any

from redis import Redis

from app.core.config import get_settings

_client: Any | None = None


def get_security_redis() -> Any:
    """Lazily build (and cache) the Redis client for security state."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = Redis.from_url(
            settings.RATE_LIMIT_REDIS_URL,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            decode_responses=False,
            health_check_interval=30,
        )
    return _client


def set_security_redis(client: Any | None) -> None:
    """Override the cached client.

    Tests use this to inject a deterministic in-memory fake; production
    code never calls it. Pass ``None`` to clear and force re-initialization.
    """
    global _client
    _client = client
