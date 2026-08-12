"""The event envelope.

Every fact that moves through the system is wrapped in this envelope. The fields exist to
answer, for any event, months later: *what happened, where did it come from, when did it
happen versus when did we see it, what caused it, and have we already processed it?*

Three timestamps, never conflated:

``occurred_at``  when the fact happened at the source (market time)
``ingestion_at`` when we received it
``recorded_at``  when we persisted it

A clock-skew check compares them and flags inconsistency rather than silently accepting
an event that claims to have happened in the future.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tia.core.clock import Clock, ensure_utc
from tia.core.ids import deterministic_id, new_ulid

P = TypeVar("P", bound=BaseModel)

MAX_FUTURE_SKEW = timedelta(seconds=5)


class EventPayload(BaseModel):
    """Base class for every payload. Frozen: an event is a fact, and facts don't mutate."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class EventEnvelope(BaseModel, Generic[P]):
    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: str
    schema_version: int = 1
    source: str
    occurred_at: datetime
    ingestion_at: datetime
    recorded_at: datetime
    correlation_id: str
    causation_id: str | None = None
    sequence: int = Field(0, ge=0)
    idempotency_key: str
    payload: P
    clock_skew_warning: bool = False

    @field_validator("occurred_at", "ingestion_at", "recorded_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v, field="event timestamp")

    @model_validator(mode="after")
    def _skew(self) -> EventEnvelope[P]:
        if self.occurred_at > self.ingestion_at + MAX_FUTURE_SKEW and not self.clock_skew_warning:
            object.__setattr__(self, "clock_skew_warning", True)
        return self

    @property
    def ingestion_latency_ms(self) -> float:
        return (self.ingestion_at - self.occurred_at).total_seconds() * 1000.0

    def caused(
        self,
        *,
        event_type: str,
        payload: BaseModel,
        clock: Clock,
        source: str,
        sequence: int = 0,
        schema_version: int = 1,
        idempotency_parts: tuple[Any, ...] | None = None,
        deterministic_id_seed: str | None = None,
    ) -> EventEnvelope[Any]:
        """Create a child event, inheriting correlation and pointing back at this one.

        This is the only sanctioned way to derive an event from another, which is what
        keeps the causation chain unbroken all the way from a closed candle to a P&L
        update.
        """
        now = clock.now()
        parts = idempotency_parts or (event_type, self.event_id)
        return build_event(
            event_type=event_type,
            payload=payload,
            clock=clock,
            source=source,
            correlation_id=self.correlation_id,
            causation_id=self.event_id,
            sequence=sequence,
            schema_version=schema_version,
            occurred_at=now,
            idempotency_parts=parts,
            deterministic_id_seed=deterministic_id_seed,
        )

    def summary(self) -> dict[str, Any]:
        """Compact form for logs — payload replaced by its type, never dumped wholesale."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "source": self.source,
            "occurred_at": self.occurred_at.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "sequence": self.sequence,
            "payload_type": type(self.payload).__name__,
        }


def build_event(
    *,
    event_type: str,
    payload: BaseModel,
    clock: Clock,
    source: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    sequence: int = 0,
    schema_version: int = 1,
    occurred_at: datetime | None = None,
    ingestion_at: datetime | None = None,
    idempotency_parts: tuple[Any, ...] | None = None,
    deterministic_id_seed: str | None = None,
) -> EventEnvelope[Any]:
    """Construct an envelope with consistent ids, timestamps and dedup key.

    ``deterministic_id_seed`` makes the ``event_id`` itself reproducible, which the
    backtester uses so that two runs of the same experiment produce byte-identical
    event logs.
    """
    now = clock.now()
    occurred = ensure_utc(occurred_at) if occurred_at is not None else now
    ingested = ensure_utc(ingestion_at) if ingestion_at is not None else now

    if deterministic_id_seed is not None:
        event_id = deterministic_id("evt", deterministic_id_seed, length=26)
    else:
        event_id = f"evt_{new_ulid(clock)}"

    parts = idempotency_parts if idempotency_parts is not None else (event_type, event_id)
    idem = deterministic_id("idem", event_type, *parts)

    return EventEnvelope[Any](
        event_id=event_id,
        event_type=event_type,
        schema_version=schema_version,
        source=source,
        occurred_at=occurred,
        ingestion_at=ingested,
        recorded_at=now,
        correlation_id=correlation_id or event_id,
        causation_id=causation_id,
        sequence=sequence,
        idempotency_key=idem,
        payload=payload,
    )


__all__ = ["MAX_FUTURE_SKEW", "EventEnvelope", "EventPayload", "build_event"]
