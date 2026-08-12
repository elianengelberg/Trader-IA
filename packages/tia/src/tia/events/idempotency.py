"""Idempotency.

The system assumes at-least-once delivery everywhere: reconnects replay, retries
duplicate, providers repeat. The rule is that *seeing an event twice must be
indistinguishable from seeing it once*.

Two backends behind one interface. In-memory is a bounded TTL map — sufficient for a
single process and for tests. Redis uses ``SET NX EX``, which is atomic across processes,
so a horizontally-scaled fast loop cannot double-process.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any

from tia.core.clock import Clock
from tia.core.logging import get_logger

_log = get_logger("events.idempotency")

DEFAULT_TTL_SECONDS = 86_400


class IdempotencyStore(ABC):
    """Records which keys have been seen."""

    @abstractmethod
    async def claim(self, key: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        """Atomically claim ``key``. Returns ``True`` on first sight, ``False`` on a duplicate."""

    @abstractmethod
    async def seen(self, key: str) -> bool:
        """Whether ``key`` has been claimed (without claiming it)."""

    @abstractmethod
    async def release(self, key: str) -> None:
        """Drop a claim. Used when processing failed and a retry *should* be reprocessed."""

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None


class InMemoryIdempotencyStore(IdempotencyStore):
    """Bounded LRU with TTL. Single-process only."""

    def __init__(self, clock: Clock, *, max_entries: int = 200_000) -> None:
        self._clock = clock
        self._max = max_entries
        self._entries: OrderedDict[str, float] = OrderedDict()

    def _expire(self, now_ts: float) -> None:
        """Drop entries whose TTL has passed. Insertion order is close enough to expiry
        order (uniform TTLs) that stopping at the first live entry is correct."""
        while self._entries:
            _key, expires = next(iter(self._entries.items()))
            if expires > now_ts:
                break
            self._entries.popitem(last=False)

    def _trim(self) -> None:
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    async def claim(self, key: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        now_ts = self._clock.now().timestamp()
        self._expire(now_ts)
        existing = self._entries.get(key)
        if existing is not None and existing > now_ts:
            return False
        self._entries[key] = now_ts + ttl_seconds
        self._entries.move_to_end(key)
        # Trim *after* inserting, otherwise the map settles one entry above the bound.
        self._trim()
        return True

    async def seen(self, key: str) -> bool:
        now_ts = self._clock.now().timestamp()
        expires = self._entries.get(key)
        return expires is not None and expires > now_ts

    async def release(self, key: str) -> None:
        self._entries.pop(key, None)

    def __len__(self) -> int:
        return len(self._entries)


class RedisIdempotencyStore(IdempotencyStore):
    """Cross-process claims via ``SET NX EX``.

    Falls back to the in-memory store when Redis is unreachable, and logs the
    degradation loudly — duplicate suppression becomes best-effort, which the operator
    needs to know rather than discover from a double-counted position.
    """

    def __init__(self, redis_client: Any, clock: Clock, *, namespace: str = "tia:idem") -> None:
        self._redis = redis_client
        self._namespace = namespace
        self._fallback = InMemoryIdempotencyStore(clock)
        self._degraded = False

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def claim(self, key: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        try:
            result = await self._redis.set(self._key(key), "1", nx=True, ex=ttl_seconds)
            if self._degraded:
                _log.info("idempotency_store_recovered")
                self._degraded = False
            return bool(result)
        except Exception as exc:
            if not self._degraded:
                _log.error("idempotency_store_degraded", error=str(exc))
                self._degraded = True
            return await self._fallback.claim(key, ttl_seconds=ttl_seconds)

    async def seen(self, key: str) -> bool:
        try:
            return bool(await self._redis.exists(self._key(key)))
        except Exception:
            return await self._fallback.seen(key)

    async def release(self, key: str) -> None:
        try:
            await self._redis.delete(self._key(key))
        except Exception:
            await self._fallback.release(key)

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except Exception:
            return


class Deduplicator:
    """Convenience wrapper used by handlers.

    ``should_process`` is the whole API surface most call sites need, and reading it at
    the top of a handler makes the idempotency guarantee visible in the code rather than
    buried in infrastructure.
    """

    def __init__(self, store: IdempotencyStore, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._store = store
        self._ttl = ttl_seconds
        self.duplicates_suppressed = 0

    async def should_process(self, idempotency_key: str) -> bool:
        first_time = await self._store.claim(idempotency_key, ttl_seconds=self._ttl)
        if not first_time:
            self.duplicates_suppressed += 1
        return first_time

    async def undo(self, idempotency_key: str) -> None:
        await self._store.release(idempotency_key)


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "Deduplicator",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "RedisIdempotencyStore",
]
