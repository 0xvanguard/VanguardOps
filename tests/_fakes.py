"""In-process fakes used by the test suite.

Kept minimal on purpose: we expose only the surface the production code
actually calls. If a future feature uses, say, ``HSET``, the test fake
will fail loudly until the corresponding method is added here, which is
exactly the safety net we want.
"""

from __future__ import annotations

import time
from typing import Final

from redis.exceptions import RedisError


class FakeRedis:
    """Single-process stand-in for a Redis client.

    Implements the surface used by:

    * :class:`app.services.token_blacklist.TokenBlacklist`
      (``exists``, ``set`` with ``ex=`` TTL, ``ping``, ``delete``)
    * :class:`app.services.rate_limiter.SlidingWindowRateLimiter`
      (``zadd``, ``zremrangebyscore``, ``zcard``, ``zrange``, ``expire``)
    * :class:`app.services.ip_banlist.IPBanlist`
      (``incr``, ``get``, ``ttl``, ``set``, ``delete``, ``expire``)

    Set :attr:`fail_calls` to ``True`` to make every call raise
    :class:`redis.exceptions.RedisError`; the security services use this
    to exercise their fail-closed / fail-open branches.
    """

    _UNSET: Final[object] = object()

    def __init__(self) -> None:
        self._store: dict[str, tuple[bytes, float | None]] = {}
        self._zsets: dict[str, dict[str, float]] = {}
        self._zset_expiry: dict[str, float | None] = {}
        #: Toggle to simulate a Redis outage.
        self.fail_calls: bool = False

    # --- helpers ------------------------------------------------------

    def _maybe_fail(self) -> None:
        if self.fail_calls:
            raise RedisError("FakeRedis: simulated failure")

    def _is_alive(self, expires_at: float | None) -> bool:
        return expires_at is None or expires_at > time.time()

    def _gc(self, key: str) -> None:
        entry = self._store.get(key)
        if entry is not None and not self._is_alive(entry[1]):
            self._store.pop(key, None)
        zexp = self._zset_expiry.get(key)
        if zexp is not None and not self._is_alive(zexp):
            self._zsets.pop(key, None)
            self._zset_expiry.pop(key, None)

    # --- key ops ------------------------------------------------------

    def exists(self, *keys: str) -> int:
        self._maybe_fail()
        if len(keys) == 1:
            self._gc(keys[0])
            return 1 if keys[0] in self._store or keys[0] in self._zsets else 0
        count = 0
        for key in keys:
            self._gc(key)
            if key in self._store or key in self._zsets:
                count += 1
        return count

    def get(self, key: str) -> bytes | None:
        self._maybe_fail()
        self._gc(key)
        entry = self._store.get(key)
        return entry[0] if entry is not None else None

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self._maybe_fail()
        expires_at = time.time() + ex if ex else None
        encoded = value if isinstance(value, bytes) else str(value).encode()
        self._store[key] = (encoded, expires_at)
        return True

    def incr(self, key: str) -> int:
        self._maybe_fail()
        self._gc(key)
        entry = self._store.get(key)
        if entry is None:
            self._store[key] = (b"1", None)
            return 1
        try:
            current = int(entry[0])
        except (TypeError, ValueError) as exc:
            raise RedisError(f"value at {key} is not an integer") from exc
        new_val = current + 1
        # INCR preserves the existing TTL on the key.
        self._store[key] = (str(new_val).encode(), entry[1])
        return new_val

    def expire(self, key: str, seconds: int) -> int:
        self._maybe_fail()
        target_at = time.time() + seconds
        if key in self._store:
            value, _ = self._store[key]
            self._store[key] = (value, target_at)
            return 1
        if key in self._zsets:
            self._zset_expiry[key] = target_at
            return 1
        return 0

    def ttl(self, key: str) -> int:
        self._maybe_fail()
        self._gc(key)
        entry = self._store.get(key)
        if entry is not None:
            if entry[1] is None:
                return -1
            return max(0, int(entry[1] - time.time()))
        if key in self._zsets:
            zexp = self._zset_expiry.get(key)
            if zexp is None:
                return -1
            return max(0, int(zexp - time.time()))
        return -2

    def ping(self) -> bool:
        self._maybe_fail()
        return True

    def delete(self, *keys: str) -> int:
        self._maybe_fail()
        count = 0
        for key in keys:
            removed = False
            if self._store.pop(key, None) is not None:
                removed = True
            if self._zsets.pop(key, None) is not None:
                self._zset_expiry.pop(key, None)
                removed = True
            if removed:
                count += 1
        return count

    # --- ZSET ops -----------------------------------------------------

    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self._maybe_fail()
        self._gc(key)
        zset = self._zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in zset:
                added += 1
            zset[member] = float(score)
        return added

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        self._maybe_fail()
        self._gc(key)
        zset = self._zsets.get(key)
        if not zset:
            return 0
        to_remove = [
            m for m, s in zset.items() if min_score <= s <= max_score
        ]
        for m in to_remove:
            del zset[m]
        return len(to_remove)

    def zcard(self, key: str) -> int:
        self._maybe_fail()
        self._gc(key)
        return len(self._zsets.get(key, {}))

    def zrange(
        self,
        key: str,
        start: int,
        stop: int,
        withscores: bool = False,
    ) -> list:
        self._maybe_fail()
        self._gc(key)
        zset = self._zsets.get(key, {})
        ordered = sorted(zset.items(), key=lambda kv: (kv[1], kv[0]))
        # Redis-style: stop is inclusive; -1 means last element.
        if stop == -1:
            sliced = ordered[start:]
        else:
            sliced = ordered[start : stop + 1]
        if withscores:
            return [(m, s) for m, s in sliced]
        return [m for m, _ in sliced]

    # --- introspection helpers used only by tests ---------------------

    def keys_snapshot(self) -> list[str]:
        out: list[str] = []
        for key, (_, exp) in self._store.items():
            if self._is_alive(exp):
                out.append(key)
        for key in self._zsets:
            zexp = self._zset_expiry.get(key)
            if self._is_alive(zexp):
                out.append(key)
        return out
