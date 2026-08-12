"""The event bus.

One interface, two implementations. The in-memory bus runs the demo, the tests and the
backtester — it is synchronous-in-order, which is exactly what a deterministic replay
needs. The Redis Streams bus adds durability, consumer groups and at-least-once delivery
for the multi-process deployment.

The interface is the hedge against the throughput ceiling: swapping in Kafka or Redpanda
later is a new class here, not a change to any handler.

**Delivery is at-least-once, never exactly-once.** Handlers must therefore be idempotent;
:class:`~tia.events.idempotency.Deduplicator` is how they achieve it. A bus that promised
exactly-once would be lying, and the handlers would be written to trust the lie.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from tia.core.clock import Clock
from tia.core.errors import SchemaValidationError
from tia.core.logging import get_logger
from tia.events.envelope import EventEnvelope
from tia.events.registry import decode, encode

_log = get_logger("events.bus")

Handler = Callable[[EventEnvelope[Any]], Awaitable[None]]

ALL_EVENTS = "*"


class DeadLetterQueue:
    """Where unparseable or repeatedly-failing events go.

    Bounded, so a storm of bad events cannot exhaust memory, and inspectable, so the
    operator can see *what* was quarantined rather than only that something was.
    """

    def __init__(self, max_size: int = 5_000) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=max_size)
        self.total = 0

    def add(self, raw: Any, reason: str, *, error: str = "") -> None:
        self.total += 1
        self._items.append({"raw": raw, "reason": reason, "error": error})
        _log.warning("event_dead_lettered", reason=reason, error=error, total=self.total)

    def items(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._items)

    def __len__(self) -> int:
        return len(self._items)


class EventBus(ABC):
    """Publish/subscribe over :class:`EventEnvelope`."""

    def __init__(self) -> None:
        self.dead_letters = DeadLetterQueue()
        self.published_count = 0
        self.delivered_count = 0
        self.handler_failures = 0

    @abstractmethod
    async def publish(self, envelope: EventEnvelope[Any]) -> None: ...

    @abstractmethod
    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register ``handler`` for ``event_type`` (or :data:`ALL_EVENTS`)."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def publish_many(self, envelopes: Iterable[EventEnvelope[Any]]) -> None:
        for envelope in envelopes:
            await self.publish(envelope)


class InMemoryEventBus(EventBus):
    """In-process bus.

    Two modes, deliberately:

    ``sync=True``   handlers run inline, in registration order, before ``publish``
                    returns. Deterministic — the backtester and unit tests use this.
    ``sync=False``  events go through an ``asyncio.Queue`` drained by a worker task.
                    Closer to production behaviour; used by the live runtime.

    A handler that raises never breaks the publisher: the failure is counted, logged and
    dead-lettered, and the remaining handlers still run. One bad subscriber must not be
    able to stop market data from flowing.
    """

    def __init__(self, *, sync: bool = True, queue_size: int = 10_000) -> None:
        super().__init__()
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._sync = sync
        self._queue: asyncio.Queue[EventEnvelope[Any]] = asyncio.Queue(maxsize=queue_size)
        self._worker: asyncio.Task[None] | None = None
        self._running = False
        self.history: deque[EventEnvelope[Any]] = deque(maxlen=10_000)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        with contextlib.suppress(ValueError):
            self._handlers[event_type].remove(handler)

    async def publish(self, envelope: EventEnvelope[Any]) -> None:
        self.published_count += 1
        self.history.append(envelope)
        if self._sync:
            await self._dispatch(envelope)
            return
        try:
            self._queue.put_nowait(envelope)
        except asyncio.QueueFull:
            # Backpressure is a real condition, not an assertion failure. Drop the
            # newest event and make the drop visible instead of blocking ingestion.
            self.dead_letters.add(envelope.summary(), reason="queue_full")

    async def _dispatch(self, envelope: EventEnvelope[Any]) -> None:
        handlers = [*self._handlers.get(envelope.event_type, []), *self._handlers.get(ALL_EVENTS, [])]
        for handler in handlers:
            try:
                await handler(envelope)
                self.delivered_count += 1
            except Exception as exc:
                self.handler_failures += 1
                self.dead_letters.add(
                    envelope.summary(),
                    reason=f"handler_error:{getattr(handler, '__qualname__', handler)}",
                    error=str(exc),
                )
                _log.error(
                    "event_handler_failed",
                    event_type=envelope.event_type,
                    correlation_id=envelope.correlation_id,
                    error=str(exc),
                )

    async def _run(self) -> None:
        while self._running:
            try:
                envelope = await asyncio.wait_for(self._queue.get(), timeout=0.25)
            except TimeoutError:
                continue
            except asyncio.CancelledError:  # pragma: no cover - shutdown path
                break
            try:
                await self._dispatch(envelope)
            finally:
                self._queue.task_done()

    async def start(self) -> None:
        if self._sync or self._running:
            return
        self._running = True
        self._worker = asyncio.create_task(self._run(), name="tia-eventbus")

    async def stop(self) -> None:
        self._running = False
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def drain(self, max_wait_seconds: float = 5.0) -> None:
        """Wait for the queue to empty. Used by tests and by graceful shutdown."""
        if self._sync:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._queue.join(), timeout=max_wait_seconds)


class RedisStreamsEventBus(EventBus):
    """Durable bus over Redis Streams with consumer groups.

    Chosen over Kafka for this stage: consumer groups, acknowledgements and
    ``XAUTOCLAIM`` for messages orphaned by a dead consumer give at-least-once delivery
    with one fewer system to operate. When partitioning and retention genuinely matter,
    a ``KafkaEventBus`` implements this same interface.
    """

    def __init__(
        self,
        redis_client: Any,
        clock: Clock,
        *,
        stream: str = "tia:events",
        group: str = "tia-core",
        consumer: str = "worker-1",
        max_stream_length: int = 1_000_000,
        block_ms: int = 1_000,
        batch_size: int = 64,
    ) -> None:
        super().__init__()
        self._redis = redis_client
        self._clock = clock
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._maxlen = max_stream_length
        self._block_ms = block_ms
        self._batch = batch_size
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    async def publish(self, envelope: EventEnvelope[Any]) -> None:
        self.published_count += 1
        await self._redis.xadd(
            self._stream,
            {"data": json.dumps(encode(envelope), separators=(",", ":"))},
            maxlen=self._maxlen,
            approximate=True,
        )

    async def _ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(self._stream, self._group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _handle_raw(self, message_id: str, fields: dict[Any, Any]) -> None:
        raw = fields.get("data") or fields.get(b"data")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            envelope = decode(json.loads(raw))
        except (SchemaValidationError, json.JSONDecodeError, TypeError) as exc:
            self.dead_letters.add(raw, reason="decode_failed", error=str(exc))
            await self._redis.xack(self._stream, self._group, message_id)
            return

        handlers = [*self._handlers.get(envelope.event_type, []), *self._handlers.get(ALL_EVENTS, [])]
        failed = False
        for handler in handlers:
            try:
                await handler(envelope)
                self.delivered_count += 1
            except Exception as exc:
                failed = True
                self.handler_failures += 1
                _log.error(
                    "event_handler_failed",
                    event_type=envelope.event_type,
                    error=str(exc),
                    message_id=message_id,
                )
        if failed:
            # Leave it unacknowledged so XAUTOCLAIM can retry it later; a handler bug
            # should not silently consume the event.
            self.dead_letters.add(envelope.summary(), reason="handler_error")
            return
        await self._redis.xack(self._stream, self._group, message_id)

    async def _run(self) -> None:
        while self._running:
            try:
                response = await self._redis.xreadgroup(
                    self._group,
                    self._consumer,
                    {self._stream: ">"},
                    count=self._batch,
                    block=self._block_ms,
                )
            except asyncio.CancelledError:  # pragma: no cover
                break
            except Exception as exc:
                _log.error("event_bus_read_failed", error=str(exc))
                await asyncio.sleep(1.0)
                continue
            if not response:
                continue
            for _stream_name, messages in response:
                for message_id, fields in messages:
                    mid = message_id.decode() if isinstance(message_id, bytes) else message_id
                    await self._handle_raw(mid, fields)

    async def start(self) -> None:
        if self._running:
            return
        await self._ensure_group()
        self._running = True
        self._task = asyncio.create_task(self._run(), name="tia-redis-eventbus")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


class RecordingBus(InMemoryEventBus):
    """In-memory bus that keeps every event. Used by the backtester and by e2e tests."""

    def __init__(self) -> None:
        super().__init__(sync=True)
        self.recorded: list[EventEnvelope[Any]] = []

    async def publish(self, envelope: EventEnvelope[Any]) -> None:
        self.recorded.append(envelope)
        await super().publish(envelope)

    def of_type(self, event_type: str) -> list[EventEnvelope[Any]]:
        return [e for e in self.recorded if e.event_type == event_type]

    def by_correlation(self, correlation_id: str) -> list[EventEnvelope[Any]]:
        return [e for e in self.recorded if e.correlation_id == correlation_id]


__all__ = [
    "ALL_EVENTS",
    "DeadLetterQueue",
    "EventBus",
    "Handler",
    "InMemoryEventBus",
    "RecordingBus",
    "RedisStreamsEventBus",
]
