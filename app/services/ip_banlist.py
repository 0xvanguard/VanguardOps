"""Dynamic IP banlist with escalating durations.

Two abuse signals are tracked per source IP:

* **Authentication failures** (``ban:fails:{ip}``)
  Triggered by ``decode_token`` returning 401 for the standard auth
  endpoints. ``RATE_LIMIT_AUTH_FAILURE_THRESHOLD`` failures within
  ``RATE_LIMIT_AUTH_FAILURE_WINDOW`` seconds activates a ban.

* **Vulnerability scanning** (``ban:404:{ip}``)
  Triggered by responses with status 404. Automated scanners (dirb,
  gobuster, nikto, etc.) walk a wordlist of paths; their footprint is
  hundreds of 404s per minute from a single IP.
  ``RATE_LIMIT_404_THRESHOLD`` 404s within ``RATE_LIMIT_404_WINDOW``
  seconds activates a ban.

Bans **escalate** so a repeat offender pays an exponentially growing cost:

* 1st ban → 15 minutes
* 2nd ban → 1 hour
* 3rd+    → 24 hours

The escalation counter (``ban:count:{ip}``) itself has a 24h TTL after the
last ban, so good citizens whose IPs were assigned to a previous offender
recover the lighter ban schedule once a day passes without incidents.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from prometheus_client import Counter

from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

BANS_ACTIVATED = Counter(
    "ip_bans_activated_total",
    "Bans activated by the dynamic IP banlist.",
    labelnames=("reason",),
)

BAN_HITS_BLOCKED = Counter(
    "ip_ban_blocked_requests_total",
    "Requests rejected because their source IP was actively banned.",
    labelnames=("reason",),
)

BANLIST_REDIS_ERRORS = Counter(
    "ip_banlist_redis_errors_total",
    "Failures contacting the IP banlist Redis store.",
    labelnames=("operation",),
)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


class BanReason(StrEnum):
    AUTH_FAILURES = "auth_failures"
    SCAN_ATTEMPT = "scan_attempt"


@dataclass(frozen=True)
class BanInfo:
    banned: bool
    reason: str | None = None
    retry_after_seconds: int = 0


# Default ladder - exposed for ADR documentation and tests.
DEFAULT_BAN_DURATIONS: tuple[int, ...] = (15 * 60, 60 * 60, 24 * 60 * 60)
DEFAULT_BAN_COUNTER_TTL: int = 24 * 60 * 60  # 24h memory of past bans


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


class IPBanlist:
    """Counter + ban-state state machine over Redis."""

    def __init__(
        self,
        redis_client: Any,
        *,
        auth_failure_threshold: int = 10,
        auth_failure_window: int = 300,
        scan_threshold: int = 20,
        scan_window: int = 60,
        ban_durations: tuple[int, ...] = DEFAULT_BAN_DURATIONS,
        ban_counter_ttl: int = DEFAULT_BAN_COUNTER_TTL,
    ) -> None:
        if not ban_durations:
            raise ValueError("ban_durations must contain at least one entry")
        self._redis = redis_client
        self._auth_threshold = auth_failure_threshold
        self._auth_window = auth_failure_window
        self._scan_threshold = scan_threshold
        self._scan_window = scan_window
        self._ban_durations = ban_durations
        self._ban_counter_ttl = ban_counter_ttl

    # --- queries ------------------------------------------------------

    def is_banned(self, ip: str) -> BanInfo:
        """Check whether ``ip`` is currently banned.

        Fails open: a Redis error returns ``BanInfo(banned=False)`` so a
        broken banlist cannot lock the entire user base out (the JWT
        blacklist on DB /2 still enforces session integrity per ADR-007).
        """
        try:
            value = self._redis.get(self._active_key(ip))
            if value is None:
                return BanInfo(banned=False)
            ttl = self._redis.ttl(self._active_key(ip))
            if ttl is None or ttl < 0:
                ttl = 1  # key existed but TTL gone - treat as ending now
            reason = value.decode() if isinstance(value, bytes) else str(value)
            BAN_HITS_BLOCKED.labels(reason=reason).inc()
            return BanInfo(banned=True, reason=reason, retry_after_seconds=int(ttl))
        except Exception as exc:
            BANLIST_REDIS_ERRORS.labels(operation="get").inc()
            logger.warning("ip_banlist_redis_error", operation="get", error=str(exc))
            return BanInfo(banned=False)

    # --- counters & ban transitions -----------------------------------

    def track_auth_failure(self, ip: str) -> BanInfo:
        return self._track(
            ip,
            kind="fails",
            threshold=self._auth_threshold,
            window=self._auth_window,
            reason=BanReason.AUTH_FAILURES,
        )

    def track_scan(self, ip: str) -> BanInfo:
        return self._track(
            ip,
            kind="404",
            threshold=self._scan_threshold,
            window=self._scan_window,
            reason=BanReason.SCAN_ATTEMPT,
        )

    def clear(self, ip: str) -> None:
        """Manually lift a ban and reset all counters for ``ip``."""
        try:
            self._redis.delete(
                self._active_key(ip),
                f"ban:fails:{ip}",
                f"ban:404:{ip}",
                f"ban:count:{ip}",
            )
        except Exception as exc:
            BANLIST_REDIS_ERRORS.labels(operation="delete").inc()
            logger.warning("ip_banlist_redis_error", operation="delete", error=str(exc))

    # --- internals ----------------------------------------------------

    def _track(
        self,
        ip: str,
        *,
        kind: str,
        threshold: int,
        window: int,
        reason: BanReason,
    ) -> BanInfo:
        key = f"ban:{kind}:{ip}"
        try:
            count = int(self._redis.incr(key))
            if count == 1:
                # First increment in the window; pin the TTL.
                self._redis.expire(key, window)
            if count < threshold:
                return BanInfo(banned=False)
            duration = self._activate_ban(ip, reason)
            # Drop the counter so post-ban behaviour starts from zero.
            self._redis.delete(key)
            return BanInfo(
                banned=True, reason=reason.value, retry_after_seconds=duration
            )
        except Exception as exc:
            BANLIST_REDIS_ERRORS.labels(operation="track").inc()
            logger.warning(
                "ip_banlist_redis_error",
                operation="track",
                kind=kind,
                error=str(exc),
            )
            # Fail open on errors: counters are best-effort.
            return BanInfo(banned=False)

    def _activate_ban(self, ip: str, reason: BanReason) -> int:
        duration = self._next_ban_duration(ip)
        self._redis.set(self._active_key(ip), reason.value, ex=duration)
        BANS_ACTIVATED.labels(reason=reason.value).inc()
        logger.info(
            "ip_banned",
            ip=ip,
            reason=reason.value,
            duration_seconds=duration,
        )
        return duration

    def _next_ban_duration(self, ip: str) -> int:
        count_key = f"ban:count:{ip}"
        ban_count = int(self._redis.incr(count_key))
        if ban_count == 1:
            # Reset the escalation counter after a quiet period.
            self._redis.expire(count_key, self._ban_counter_ttl)
        idx = min(ban_count - 1, len(self._ban_durations) - 1)
        return self._ban_durations[idx]

    @staticmethod
    def _active_key(ip: str) -> str:
        return f"ban:active:{ip}"


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_banlist: IPBanlist | None = None


def get_banlist() -> IPBanlist:
    """Return the process-wide IP banlist, creating it on first call."""
    global _banlist
    if _banlist is None:
        from app.core.config import get_settings
        from app.services.security_redis import get_security_redis

        settings = get_settings()
        _banlist = IPBanlist(
            get_security_redis(),
            auth_failure_threshold=settings.RATE_LIMIT_AUTH_FAILURE_THRESHOLD,
            auth_failure_window=settings.RATE_LIMIT_AUTH_FAILURE_WINDOW,
            scan_threshold=settings.RATE_LIMIT_404_THRESHOLD,
            scan_window=settings.RATE_LIMIT_404_WINDOW,
        )
    return _banlist


def set_banlist(banlist: IPBanlist | None) -> None:
    """Override the cached banlist (test-only hook)."""
    global _banlist
    _banlist = banlist
