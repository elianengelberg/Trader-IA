"""Event backbone: contracts, registry, bus and idempotency."""

from tia.events.bus import (
    ALL_EVENTS,
    DeadLetterQueue,
    EventBus,
    Handler,
    InMemoryEventBus,
    RecordingBus,
    RedisStreamsEventBus,
)
from tia.events.envelope import EventEnvelope, EventPayload, build_event
from tia.events.idempotency import (
    Deduplicator,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    RedisIdempotencyStore,
)
from tia.events.payloads import EventType
from tia.events.registry import decode, encode, known_event_types, register, register_upcaster

__all__ = [
    "ALL_EVENTS",
    "DeadLetterQueue",
    "Deduplicator",
    "EventBus",
    "EventEnvelope",
    "EventPayload",
    "EventType",
    "Handler",
    "IdempotencyStore",
    "InMemoryEventBus",
    "InMemoryIdempotencyStore",
    "RecordingBus",
    "RedisIdempotencyStore",
    "RedisStreamsEventBus",
    "build_event",
    "decode",
    "encode",
    "known_event_types",
    "register",
    "register_upcaster",
]
