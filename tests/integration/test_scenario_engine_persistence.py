"""The scenario engine's persistence and stop contract (Phase 1.4).

Before this phase the engine scheduled every write as its own task and returned from
``stop()`` with writes still in flight; two writes on separate sessions could interleave,
so a fill could reach the store before the order it references (and be refused by the
foreign key); a loop that did not stop in ten seconds left the engine RUNNING with no task.
Every scenario here is driven by events and barriers, not by sleeping and hoping.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tia.core.config import Environment, settings_for_env
from tia.runtime.engine import RuntimeConfig, RuntimeEngine, RuntimeState


def _engine(persist, *, seed: int = 20260812) -> RuntimeEngine:  # type: ignore[no-untyped-def]
    config = RuntimeConfig(
        scenario="trend_up", symbols=("BTC-USD",), initial_capital=10_000.0, seed=seed,
        bar_interval_seconds=0.0, llm_enabled=False, news_enabled=False,
    )
    return RuntimeEngine(settings_for_env(Environment.TESTING), config, persist=persist)


async def _until(predicate, *, limit_seconds: float = 30.0) -> None:  # type: ignore[no-untyped-def]
    """Yield to the loop until ``predicate()`` holds, or fail after ``limit_seconds``."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_seconds
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0)


async def test_a_fill_is_never_written_before_the_order_it_references() -> None:
    """The order write is slow, the fill write is instant. Fire-and-forget lets the fill
    overtake its order; sequenced writes land in the order they were scheduled."""
    landed: list[tuple[str, str]] = []

    async def persist(kind: str, payload: dict[str, Any]) -> None:
        if kind == "order":
            await asyncio.sleep(0.02)
            landed.append(("order", payload["order"].order_id))
        elif kind == "fill":
            landed.append(("fill", payload["fill"].order_id))

    engine = _engine(persist)
    await engine.start()
    try:
        await _until(lambda: sum(1 for k, _ in landed if k == "fill") >= 2 or not engine.is_running)
    finally:
        await engine.stop()
    assert engine.persistence_flushed is True
    fills = [(i, oid) for i, (kind, oid) in enumerate(landed) if kind == "fill"]
    assert fills, "the scenario produced no fill"
    for position, order_id in fills:
        first_order_write = next(i for i, (k, oid) in enumerate(landed) if k == "order" and oid == order_id)
        assert first_order_write < position, f"fill for {order_id} landed before its order"


async def test_stop_waits_for_the_writes_in_flight_and_says_when_it_could_not() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    async def persist(kind: str, payload: dict[str, Any]) -> None:
        entered.set()
        await release.wait()

    engine = _engine(persist)
    engine._flush_timeout_seconds = 0.2
    await engine.start()
    await asyncio.wait_for(entered.wait(), timeout=10.0)
    await engine.stop()
    assert engine.state is RuntimeState.STOPPED
    assert engine.persistence_flushed is False
    assert "still in flight" in engine.last_error
    pending_before = sum(1 for t in engine._persist_tasks if not t.done())
    assert pending_before >= 1

    release.set()
    assert await engine.flush_persistence(timeout_seconds=5.0) is True
    assert not engine._persist_tasks


async def test_a_clean_stop_reports_every_write_landed() -> None:
    writes = 0

    async def persist(kind: str, payload: dict[str, Any]) -> None:
        nonlocal writes
        await asyncio.sleep(0)
        writes += 1

    engine = _engine(persist)
    await engine.start()
    await _until(lambda: engine.counters.bars >= 5)
    await engine.stop()
    assert engine.persistence_flushed is True
    assert writes >= 1 and not engine._persist_tasks
    assert engine.counters.persist_failures == 0


async def test_persistence_failures_are_counted_and_never_stop_the_loop() -> None:
    def failing_sync(kind: str, payload: dict[str, Any]) -> None:
        raise RuntimeError("store down (sync)")

    async def failing_async(kind: str, payload: dict[str, Any]) -> None:
        raise RuntimeError("store down (async)")

    for persist in (failing_sync, failing_async):
        engine = _engine(persist)
        await engine.start()
        try:
            await _until(lambda e=engine: e.counters.bars >= 10)
            assert engine.is_running, "the loop went on despite the store"
        finally:
            await engine.stop()
        assert engine.persistence_flushed is True, "failed writes are finished writes"
        assert engine.counters.persist_failures >= 1
        assert engine.counters.errors == 0, "a store failure is not a loop error"


async def test_a_loop_that_will_not_stop_is_cancelled_and_the_engine_still_lands_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Before Phase 1.4 the timeout escaped ``stop()`` after cancelling the task: the
    engine was left RUNNING with no task behind it, an impossible state."""
    engine = _engine(None)
    ticking = asyncio.Event()

    async def stuck() -> None:
        ticking.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(engine, "_tick", stuck)
    engine._stop_timeout_seconds = 0.1
    await engine.start()
    await asyncio.wait_for(ticking.wait(), timeout=5.0)
    await engine.stop()  # must not raise
    assert engine.state is RuntimeState.STOPPED
    assert engine._task is None
    assert "did not stop" in engine.last_error
    assert engine.counters.errors == 1
    assert engine.is_running is False


async def test_stop_is_idempotent() -> None:
    engine = _engine(None)
    await engine.start()
    await _until(lambda: engine.counters.bars >= 2)
    await engine.stop()
    first = engine.stopped_at
    await engine.stop()
    assert engine.state is RuntimeState.STOPPED and engine.stopped_at is not None
    assert first is not None and engine.stopped_at >= first
