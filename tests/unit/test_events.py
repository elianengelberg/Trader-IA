"""Event envelope, registry, bus and idempotency."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import make_candle
from tia.core.clock import SimulatedClock
from tia.core.errors import SchemaValidationError, UnknownEventTypeError
from tia.domain.enums import MarketRegime
from tia.events.bus import ALL_EVENTS, InMemoryEventBus, RecordingBus
from tia.events.envelope import EventEnvelope, build_event
from tia.events.idempotency import Deduplicator, InMemoryIdempotencyStore
from tia.events.payloads import CandleClosed, EventType, RegimeChanged
from tia.events.registry import decode, encode, known_event_types, payload_class


def _candle_event(clock: SimulatedClock) -> EventEnvelope:
    candle = make_candle(open_time=clock.now())
    return build_event(
        event_type=EventType.CANDLE_CLOSED,
        payload=CandleClosed(candle=candle),
        clock=clock,
        source="provider:test",
        idempotency_parts=candle.dedup_key(),
    )


class TestEnvelope:
    def test_carries_all_required_metadata(self, clock: SimulatedClock) -> None:
        event = _candle_event(clock)
        for field in (
            "event_id",
            "event_type",
            "schema_version",
            "source",
            "occurred_at",
            "ingestion_at",
            "correlation_id",
            "idempotency_key",
        ):
            assert getattr(event, field) is not None

    def test_root_event_correlates_to_itself(self, clock: SimulatedClock) -> None:
        event = _candle_event(clock)
        assert event.correlation_id == event.event_id
        assert event.causation_id is None

    def test_caused_events_inherit_correlation_and_chain_causation(
        self, clock: SimulatedClock
    ) -> None:
        root = _candle_event(clock)
        child = root.caused(
            event_type=EventType.REGIME_CHANGED,
            payload=RegimeChanged(
                symbol="BTC-USD",
                previous=MarketRegime.RANGING,
                current=MarketRegime.TRENDING_UP,
                confidence=0.8,
            ),
            clock=clock,
            source="engine:regime",
        )
        assert child.correlation_id == root.correlation_id
        assert child.causation_id == root.event_id

    def test_idempotency_key_is_content_derived(self, clock: SimulatedClock) -> None:
        """Two deliveries of the same candle must produce the same dedup key even though
        their event ids differ."""
        first = _candle_event(clock)
        clock.advance_by(timedelta(seconds=30))
        second = _candle_event(SimulatedClock(clock.now()))
        # Same candle content (same open_time is used for the key) -> same key.
        assert first.idempotency_key != second.idempotency_key  # different open_time
        again = build_event(
            event_type=EventType.CANDLE_CLOSED,
            payload=CandleClosed(candle=make_candle(open_time=first.payload.candle.open_time)),
            clock=clock,
            source="provider:test",
            idempotency_parts=first.payload.candle.dedup_key(),
        )
        assert again.idempotency_key == first.idempotency_key

    def test_future_dated_event_is_flagged_not_silently_accepted(
        self, clock: SimulatedClock
    ) -> None:
        event = build_event(
            event_type=EventType.CANDLE_CLOSED,
            payload=CandleClosed(candle=make_candle()),
            clock=clock,
            source="provider:test",
            occurred_at=clock.now() + timedelta(minutes=10),
        )
        assert event.clock_skew_warning is True

    def test_payload_is_frozen(self, clock: SimulatedClock) -> None:
        event = _candle_event(clock)
        with pytest.raises(Exception, match=r"frozen|immutable"):
            event.payload.candle = make_candle()  # type: ignore[misc]

    def test_summary_does_not_dump_the_payload(self, clock: SimulatedClock) -> None:
        summary = _candle_event(clock).summary()
        assert summary["payload_type"] == "CandleClosed"
        assert "candle" not in summary


class TestRegistry:
    def test_all_catalogued_types_are_registered(self) -> None:
        catalogued = {
            v for k, v in vars(EventType).items() if not k.startswith("_") and isinstance(v, str)
        }
        assert catalogued <= set(known_event_types())

    def test_roundtrip_preserves_content(self, clock: SimulatedClock) -> None:
        event = _candle_event(clock)
        decoded = decode(encode(event))
        assert decoded.event_id == event.event_id
        assert decoded.payload.candle.close == event.payload.candle.close

    def test_unknown_type_raises_rather_than_dropping(self) -> None:
        with pytest.raises(UnknownEventTypeError):
            payload_class("market.does_not_exist")

    def test_malformed_payload_raises_schema_error(self, clock: SimulatedClock) -> None:
        raw = encode(_candle_event(clock))
        raw["payload"]["candle"]["close"] = -5  # impossible price
        with pytest.raises(SchemaValidationError):
            decode(raw)

    def test_missing_event_type_is_rejected(self) -> None:
        with pytest.raises(SchemaValidationError, match="event_type"):
            decode({"payload": {}})

    def test_upcaster_is_required_for_version_gaps(self) -> None:
        from tia.events import registry
        from tia.events.envelope import EventPayload

        class V2(EventPayload):
            value: int

        registry.register("test.upcast", V2, version=2)
        registry.register("test.upcast", V2, version=1)
        with pytest.raises(SchemaValidationError, match="no upcaster"):
            registry.decode(
                {
                    "event_type": "test.upcast",
                    "schema_version": 1,
                    "payload": {"value": 1},
                    "event_id": "e",
                    "source": "s",
                    "occurred_at": "2026-01-01T00:00:00Z",
                    "ingestion_at": "2026-01-01T00:00:00Z",
                    "recorded_at": "2026-01-01T00:00:00Z",
                    "correlation_id": "c",
                    "idempotency_key": "i",
                }
            )


class TestIdempotency:
    async def test_first_claim_wins(self, clock: SimulatedClock) -> None:
        store = InMemoryIdempotencyStore(clock)
        assert await store.claim("k") is True
        assert await store.claim("k") is False

    async def test_claim_expires(self, clock: SimulatedClock) -> None:
        store = InMemoryIdempotencyStore(clock)
        await store.claim("k", ttl_seconds=60)
        clock.advance_by(timedelta(seconds=61))
        assert await store.claim("k", ttl_seconds=60) is True

    async def test_release_allows_reprocessing(self, clock: SimulatedClock) -> None:
        store = InMemoryIdempotencyStore(clock)
        await store.claim("k")
        await store.release("k")
        assert await store.claim("k") is True

    async def test_store_is_bounded(self, clock: SimulatedClock) -> None:
        store = InMemoryIdempotencyStore(clock, max_entries=10)
        for i in range(100):
            await store.claim(f"k{i}")
        assert len(store) <= 10

    async def test_deduplicator_counts_suppressions(self, clock: SimulatedClock) -> None:
        dedup = Deduplicator(InMemoryIdempotencyStore(clock))
        assert await dedup.should_process("a") is True
        assert await dedup.should_process("a") is False
        assert await dedup.should_process("a") is False
        assert dedup.duplicates_suppressed == 2


class TestBus:
    async def test_sync_bus_delivers_in_order(self, clock: SimulatedClock) -> None:
        bus = InMemoryEventBus(sync=True)
        seen: list[str] = []

        async def first(e: EventEnvelope) -> None:
            seen.append("first")

        async def second(e: EventEnvelope) -> None:
            seen.append("second")

        bus.subscribe(EventType.CANDLE_CLOSED, first)
        bus.subscribe(EventType.CANDLE_CLOSED, second)
        await bus.publish(_candle_event(clock))
        assert seen == ["first", "second"]

    async def test_wildcard_subscription_sees_everything(self, clock: SimulatedClock) -> None:
        bus = InMemoryEventBus(sync=True)
        count = 0

        async def watch(e: EventEnvelope) -> None:
            nonlocal count
            count += 1

        bus.subscribe(ALL_EVENTS, watch)
        await bus.publish(_candle_event(clock))
        clock.advance_by(timedelta(minutes=1))
        await bus.publish(_candle_event(clock))
        assert count == 2

    async def test_failing_handler_does_not_break_the_publisher(
        self, clock: SimulatedClock
    ) -> None:
        """One bad subscriber must never be able to stop market data flowing."""
        bus = InMemoryEventBus(sync=True)
        survivor_ran = False

        async def broken(e: EventEnvelope) -> None:
            raise RuntimeError("boom")

        async def survivor(e: EventEnvelope) -> None:
            nonlocal survivor_ran
            survivor_ran = True

        bus.subscribe(EventType.CANDLE_CLOSED, broken)
        bus.subscribe(EventType.CANDLE_CLOSED, survivor)
        await bus.publish(_candle_event(clock))

        assert survivor_ran is True
        assert bus.handler_failures == 1
        assert len(bus.dead_letters) == 1

    async def test_async_bus_drains(self, clock: SimulatedClock) -> None:
        bus = InMemoryEventBus(sync=False)
        received: list[str] = []

        async def handler(e: EventEnvelope) -> None:
            received.append(e.event_id)

        bus.subscribe(EventType.CANDLE_CLOSED, handler)
        await bus.start()
        try:
            await bus.publish(_candle_event(clock))
            await bus.drain(max_wait_seconds=2.0)
        finally:
            await bus.stop()
        assert len(received) == 1

    async def test_recording_bus_indexes_by_type_and_correlation(
        self, clock: SimulatedClock
    ) -> None:
        bus = RecordingBus()
        event = _candle_event(clock)
        await bus.publish(event)
        assert len(bus.of_type(EventType.CANDLE_CLOSED)) == 1
        assert len(bus.by_correlation(event.correlation_id)) == 1

    async def test_queue_full_is_dead_lettered_not_raised(self, clock: SimulatedClock) -> None:
        bus = InMemoryEventBus(sync=False, queue_size=1)
        await bus.publish(_candle_event(clock))
        clock.advance_by(timedelta(minutes=1))
        await bus.publish(_candle_event(clock))
        clock.advance_by(timedelta(minutes=1))
        await bus.publish(_candle_event(clock))
        assert bus.dead_letters.total >= 1
        assert any(d["reason"] == "queue_full" for d in bus.dead_letters.items())


class TestDomainInvariants:
    def test_candle_rejects_impossible_ohlc(self) -> None:
        with pytest.raises(ValueError, match="OHLC invariant"):
            make_candle(open_=100, close=110, high=105, low=99)

    def test_candle_rejects_naive_timestamps(self) -> None:
        with pytest.raises(Exception, match=r"timezone-aware|NAIVE"):
            make_candle(open_time=datetime(2026, 1, 1))

    def test_quote_rejects_crossed_book(self) -> None:
        from tia.domain.market import Quote

        with pytest.raises(ValueError, match="crossed book"):
            Quote(
                symbol="BTC-USD",
                timestamp=datetime(2026, 1, 1, tzinfo=UTC),
                bid=101.0,
                ask=100.0,
            )
