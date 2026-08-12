"""Time.

Nothing in this package calls ``datetime.now()`` directly. Every component receives a
``Clock``. That single rule is what makes backtests reproducible, lets failure tests
fast-forward, and keeps "what time did the system think it was?" answerable after the fact.

Three distinct timestamps are tracked throughout the system and must never be conflated:

``market_time``      when the fact happened at the venue
``ingestion_time``   when we received it
``processing_time``  when we acted on it

A ``Clock`` supplies *processing* time. Market and ingestion times come from the data.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

from tia.core.errors import NaiveDatetimeError

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def ensure_utc(value: datetime, *, field: str = "datetime") -> datetime:
    """Return ``value`` as an aware UTC datetime, or raise.

    Naive datetimes are rejected rather than assumed to be UTC: assuming is how a system
    silently mis-stamps an entire dataset.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise NaiveDatetimeError(
            f"{field} must be timezone-aware; got a naive datetime",
            field=field,
            value=value.isoformat(),
        )
    return value.astimezone(UTC)


def utc_from_millis(ms: int) -> datetime:
    """Convert an epoch-milliseconds integer (the common exchange format) to UTC."""
    return datetime.fromtimestamp(ms / 1000.0, tz=UTC)


def millis_from_utc(value: datetime) -> int:
    return int(ensure_utc(value).timestamp() * 1000)


class Clock(ABC):
    """Source of processing time and monotonic durations."""

    @abstractmethod
    def now(self) -> datetime:
        """Current processing time, timezone-aware UTC."""

    @abstractmethod
    def monotonic_ns(self) -> int:
        """Monotonic nanosecond counter, for measuring durations only."""

    def timestamp_ms(self) -> int:
        return millis_from_utc(self.now())


class SystemClock(Clock):
    """Wall-clock time. Used in demo, paper and shadow runtimes."""

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


class SimulatedClock(Clock):
    """Deterministic clock driven by the event stream.

    The backtest engine advances this clock to each event's ``occurred_at`` before the
    handlers run, so handlers see exactly the time the historical event happened — no
    more, no less. Attempting to move it backwards raises, which catches out-of-order
    replay bugs immediately.
    """

    __slots__ = ("_mono_ns", "_now")

    def __init__(self, start: datetime) -> None:
        self._now = ensure_utc(start, field="start")
        self._mono_ns = 0

    def now(self) -> datetime:
        return self._now

    def monotonic_ns(self) -> int:
        return self._mono_ns

    def advance_to(self, moment: datetime) -> None:
        moment = ensure_utc(moment, field="moment")
        if moment < self._now:
            raise ValueError(
                f"SimulatedClock cannot move backwards: {moment.isoformat()} < {self._now.isoformat()}"
            )
        self._mono_ns += int((moment - self._now).total_seconds() * 1_000_000_000)
        self._now = moment

    def advance_by(self, delta: timedelta) -> None:
        if delta.total_seconds() < 0:
            raise ValueError("SimulatedClock cannot advance by a negative duration")
        self.advance_to(self._now + delta)


class FrozenClock(Clock):
    """A clock that never moves. Only for tests that assert on exact timestamps."""

    __slots__ = ("_now",)

    def __init__(self, moment: datetime) -> None:
        self._now = ensure_utc(moment, field="moment")

    def now(self) -> datetime:
        return self._now

    def monotonic_ns(self) -> int:
        return 0


__all__ = [
    "EPOCH",
    "Clock",
    "FrozenClock",
    "SimulatedClock",
    "SystemClock",
    "ensure_utc",
    "millis_from_utc",
    "utc_from_millis",
]
