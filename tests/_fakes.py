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

    Implements only ``exists``, ``set`` (with ``ex=`` TTL), ``ping`` and
    ``delete`` - the methods used by :class:`app.services.token_blacklist.TokenBlacklist`.
    Set :attr:`fail_calls` to ``True`` to make every call raise
    :class:`redis.exceptions.RedisError`, which is how tests exercise the
    fail-closed / fail-open code paths.
    """

    _UNSET: Final[object] = object()

    def __init__(self) -> None:
        self._store: dict[str, tuple[bytes, float | None]] = {}
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

    # --- minimal Redis API --------------------------------------------

    def exists(self, key: str) -> int:
        self._maybe_fail()
        self._gc(key)
        return 1 if key in self._store else 0

    def set(self, key: str, value: object, ex: int | None = None) -> bool:
        self._maybe_fail()
        expires_at = time.time() + ex if ex else None
        encoded = value if isinstance(value, bytes) else str(value).encode()
        self._store[key] = (encoded, expires_at)
        return True

    def ping(self) -> bool:
        self._maybe_fail()
        return True

    def delete(self, *keys: str) -> int:
        self._maybe_fail()
        count = 0
        for key in keys:
            if self._store.pop(key, None) is not None:
                count += 1
        return count

    # --- introspection helpers used only by tests ---------------------

    def keys_snapshot(self) -> list[str]:
        return [k for k, (_, exp) in self._store.items() if self._is_alive(exp)]

    def ttl(self, key: str) -> int | None:
        entry = self._store.get(key)
        if entry is None or entry[1] is None:
            return None
        return max(0, int(entry[1] - time.time()))
