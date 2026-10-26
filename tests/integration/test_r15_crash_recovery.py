"""R15 — a process that dies between the commits of a round trip leaves a record that says so.

The writes of one round trip, in the order the live runtime schedules them (one session and one
commit each, through the production dispatcher ``AppState._persist``)::

    entry:  order(ack) · fill · account.fill · order(filled) · stop order · account.mark · account.plan
    exit:   stop(cancelled) · order(ack) · fill · account.fill · edge_outcome · order(filled)

A crash can fall between any two of them. What recovery must guarantee, whatever the boundary:

* **complete means consistent** — the rebuild never calls a record complete while it is missing a
  piece another piece proves was there (a fill row without its journal event or the reverse, a
  round trip the journal closed with no outcome on record);
* **consistent means complete** — a record that simply ends earlier (the crash came before the
  next write) is not refused: it is what happened as far as the store knows.

The oracle below reads the raw tables and does not use the code under test: journal fills against
fill rows, and round trips closed in the journal (the position back to flat) against outcomes.

Before R15's fix the boundary after the exit's ``account.fill`` and before its ``edge_outcome``
broke the first property: the journal rebuilt complete, the track record one trade short. The
fix: the closing fill's journal event names the outcome it closes (``closes_outcome``) and the
rebuild holds the journal against ``edge_outcomes``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from tests.integration import test_account_restore as account
from tia.core.config import Environment, settings_for_env
from tia.persistence import RunRepository
from tia.persistence.models import EdgeOutcomeRow, EventRecord, FillRow, OrderRow

Persist = Callable[[str, Any], Awaitable[Any]]


def _state(tmp_path: Path, name: str = "r15.db") -> Any:
    from tia.api.state import AppState

    url = f"sqlite+aiosqlite:///{tmp_path / name}"
    return AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": url}))


def _crashing(persist: Persist, *, land: int, log: list[str]) -> Persist:
    """The dispatcher of a process that dies after ``land`` writes reached the store: the ones
    after never do. Nothing is raised — the process is gone, nobody would see it."""
    landed = {"n": 0}

    async def write(kind: str, payload: Any) -> Any:
        log.append(kind)
        if landed["n"] >= land:
            return None
        landed["n"] += 1
        return await persist(kind, payload)

    return write


async def _round_trip(state: Any, persist: Persist) -> Any:
    runtime, _engine, market, _clock = account.build(persist=persist)
    runtime._poll_interval = 3600.0  # the test drives the cycles
    await account.register_run(state.database, runtime.run_id)
    await runtime.start()
    try:
        await account.open_position(runtime, market)
        if await runtime._close_position("time stop") is not True:
            raise RuntimeError("precondition: the exit was not sent")
        for _ in range(20):
            market.advance()
            await runtime._cycle_once()
            if runtime._open_trade is None:
                break
        if runtime.counters["round_trips"] != 1:
            raise RuntimeError("precondition: the round trip did not close")
        await account.settle(runtime)
    finally:
        runtime._stop_requested = True
        await runtime._finalize_stop()  # the process dies: no stop record, no stamp
    return runtime


async def _oracle(state: Any) -> dict[str, Any]:
    """What the raw tables say, read without the code under test."""
    async with state.database.session() as session:
        journal = (await session.execute(
            select(EventRecord.payload).where(EventRecord.event_type == "account.fill")
            .order_by(EventRecord.occurred_at, EventRecord.sequence, EventRecord.event_id)
        )).scalars().all()
        fill_rows = int((await session.execute(select(func.count()).select_from(FillRow))).scalar_one())
        outcomes = int((await session.execute(
            select(func.count()).select_from(EdgeOutcomeRow).where(EdgeOutcomeRow.source == "live"))).scalar_one())
    position, closed = 0.0, 0
    for payload in journal:
        before = position
        position += float(payload["quantity"]) * (1.0 if payload["side"] == "buy" else -1.0)
        if abs(before) > 1e-12 and abs(position) <= 1e-12:
            closed += 1
    return {"journal_fills": len(journal), "fill_rows": fill_rows, "closed_round_trips": closed, "outcomes": outcomes,
            "consistent": len(journal) == fill_rows and closed == outcomes}


async def _writes_of_a_whole_session(tmp_path: Path) -> list[str]:
    state = _state(tmp_path, "count.db")
    await state.database.ensure_schema()
    log: list[str] = []
    try:
        await _round_trip(state, _crashing(state._persist, land=10_000, log=log))
    finally:
        await state.database.close()
    return log


async def test_at_every_commit_boundary_complete_means_consistent_and_consistent_means_complete(tmp_path: Path) -> None:
    writes = await _writes_of_a_whole_session(tmp_path)
    assert "edge_outcome" in writes and writes.count("fill") == 2
    violations: list[dict[str, Any]] = []
    for land in range(len(writes) + 1):
        state = _state(tmp_path, f"crash_{land:03d}.db")
        await state.database.ensure_schema()
        try:
            log: list[str] = []
            await _round_trip(state, _crashing(state._persist, land=land, log=log))
            restore = await account.rebuild(state.database)
            truth = await _oracle(state)
        finally:
            await state.database.close()
        if restore.complete != truth["consistent"]:
            violations.append({"landed": land, "last_landed": log[land - 1] if land else None,
                               "next_lost": log[land] if land < len(log) else None,
                               "rebuild_complete": restore.complete, "error": restore.error, **truth})
    assert violations == [], violations


async def test_a_round_trip_the_journal_closed_without_its_outcome_is_named_and_blocks_the_next_session(tmp_path: Path) -> None:
    """The boundary that used to pass: the exit's journal event landed, its outcome did not."""
    writes = await _writes_of_a_whole_session(tmp_path)
    land = writes.index("edge_outcome")  # everything before the outcome lands
    state = _state(tmp_path)
    await state.database.ensure_schema()
    try:
        runtime = await _round_trip(state, _crashing(state._persist, land=land, log=[]))
        restore = await account.rebuild(state.database)
        assert restore.complete is False
        missing = restore.checks.get("round_trips_without_outcome")
        assert missing and missing[0]["run_id"] == runtime.run_id, restore.checks
        assert missing[0]["outcome_id"] in restore.error
        # The next session starts from that record: it manages what it holds and opens nothing.
        runtime_b, _, market_b, _ = account.build(account=restore)
        await runtime_b.start()
        try:
            assert "account_state" in runtime_b.entry_blocks
            account._seed_every_bucket(runtime_b)
            for _ in range(40):
                market_b.advance()
                await runtime_b._cycle_once()
            assert runtime_b.counters["orders"] == 0
        finally:
            await runtime_b.stop()
    finally:
        await state.database.close()


async def test_an_operator_acknowledgement_of_the_crashed_run_lifts_the_block_and_stays_on_view(tmp_path: Path) -> None:
    writes = await _writes_of_a_whole_session(tmp_path)
    state = _state(tmp_path)
    await state.database.ensure_schema()
    try:
        runtime = await _round_trip(state, _crashing(state._persist, land=writes.index("edge_outcome"), log=[]))
        with pytest.raises(ValueError):
            async with state.database.session() as session:  # a reason is required
                await RunRepository(session).acknowledge_persistence(runtime.run_id, actor="elian", reason=" ", at=datetime.now(UTC))
        async with state.database.session() as session:
            await RunRepository(session).acknowledge_persistence(
                runtime.run_id, actor="elian", reason="outcome lost in a crash; track record one trade short",
                at=datetime.now(UTC),
            )
        restore = await account.rebuild(state.database)
        assert restore.complete, restore.error
        assert restore.checks["session_runs_acknowledged"] == [runtime.run_id]
        assert restore.checks["round_trips_without_outcome_acknowledged"][0]["run_id"] == runtime.run_id
    finally:
        await state.database.close()


async def test_an_outcome_the_store_refused_is_detected_with_and_without_a_stop_record(tmp_path: Path) -> None:
    """Point 10 of the matrix: a write the database refuses. Without a stop (the process died
    later) the journal says what is missing; with one, the run's record says it too (R19)."""
    state = _state(tmp_path)
    await state.database.ensure_schema()

    async def refusing(kind: str, payload: Any) -> Any:
        if kind == "edge_outcome":
            raise RuntimeError("constraint violated")  # what the dispatcher absorbs and counts
        return await state._persist(kind, payload)

    try:
        runtime = await _round_trip(state, refusing)
        assert runtime.persist_failed_writes == 1
        crashed = await account.rebuild(state.database)
        assert crashed.complete is False and crashed.checks["round_trips_without_outcome"]
        async with state.database.session() as session:
            await RunRepository(session).mark_persistence(runtime.run_id, runtime.persistence_report())
        stopped = await account.rebuild(state.database)
        assert stopped.complete is False
        assert stopped.checks["session_runs_with_unconfirmed_writes"] == [runtime.run_id]
    finally:
        await state.database.close()


async def test_a_fill_refused_by_its_foreign_key_is_seen_by_the_cross_check(tmp_path: Path) -> None:
    """The order row never landed, so the database refuses the fill that references it; its
    journal event lands. The rebuild says so instead of trusting either table."""
    state = _state(tmp_path)
    await state.database.ensure_schema()

    async def no_orders(kind: str, payload: Any) -> Any:
        if kind == "order":
            return None  # lost
        return await state._persist(kind, payload)

    try:
        runtime = await _round_trip(state, no_orders)
        assert runtime.persist_failed_writes >= 2, "both fills refused by the foreign key, and counted"
        restore = await account.rebuild(state.database)
        assert restore.complete is False and "fills table" in restore.error
    finally:
        await state.database.close()


async def test_replaying_every_write_of_a_session_twice_leaves_exactly_one_row_each(tmp_path: Path) -> None:
    """Point 8: an operation retried after an uncertain answer. Every write of the round trip's
    record (orders, fills, the account journal, the outcome), applied twice in order — the
    second time as a redelivery — changes nothing. (The redelivery of the other kinds is the
    adversarial case ``test_adversarial_duplicates.py``.)"""
    captured: list[tuple[str, Any]] = []
    source = _state(tmp_path, "source.db")
    await source.database.ensure_schema()
    record_kinds = {"order", "fill", "account_event", "account_events", "edge_outcome"}

    async def recording(kind: str, payload: Any) -> Any:
        if kind in record_kinds:
            captured.append((kind, payload))
        return await source._persist(kind, payload)

    try:
        runtime = await _round_trip(source, recording)
    finally:
        await source.database.close()

    async def tables(state: Any) -> dict[str, Any]:
        async with state.database.session() as session:
            return {
                "orders": sorted((r.order_id, r.state, r.filled_quantity) for r in (await session.execute(select(OrderRow))).scalars()),
                "fills": sorted(r.fill_id for r in (await session.execute(select(FillRow))).scalars()),
                "events": sorted(r.idempotency_key for r in (await session.execute(select(EventRecord))).scalars()),
                "outcomes": sorted(r.outcome_id for r in (await session.execute(select(EdgeOutcomeRow))).scalars()),
            }

    target = _state(tmp_path, "target.db")
    await target.database.ensure_schema()
    try:
        await account.register_run(target.database, runtime.run_id)
        for kind, payload in captured:
            assert await target._persist(kind, payload) is not False, kind
        once = await tables(target)
        for kind, payload in captured:
            assert await target._persist(kind, payload) is not False, f"redelivery of {kind} refused"
        twice = await tables(target)
        assert twice == once and len(once["outcomes"]) == 1 and len(once["fills"]) == 2
        assert (await account.rebuild(target.database)).complete
    finally:
        await target.database.close()


# ------------------------------------------------------------- R19 x R15: a stop that cannot drain


async def _a_stop_whose_outcome_is_held(tmp_path: Path) -> tuple[Any, Any, Any]:
    """A session closes a round trip while its outcome write is held at the store; the stop's
    flush runs out with it queued (the R19 path), and the stop is recorded."""
    import asyncio

    state = _state(tmp_path)
    await state.database.ensure_schema()
    gate = asyncio.Event()

    async def holding(kind: str, payload: Any) -> Any:
        if kind == "edge_outcome":
            await gate.wait()
        return await state._persist(kind, payload)

    runtime, _engine, market, _clock = account.build(persist=holding)
    runtime._poll_interval = 3600.0
    runtime._flush_timeout_seconds = 0.2
    await account.register_run(state.database, runtime.run_id)
    await runtime.start()
    await account.open_position(runtime, market)
    assert await runtime._close_position("time stop") is True
    for _ in range(20):
        market.advance()
        await runtime._cycle_once()
        if runtime._open_trade is None:
            break
    await runtime.stop()
    record = await state._record_stop(runtime, stamp=True, release_lease=True)
    return state, runtime, (gate, record)


async def test_a_stop_that_could_not_drain_the_outcome_is_refused_for_both_reasons_until_acknowledged(tmp_path: Path) -> None:
    state, runtime, (gate, record) = await _a_stop_whose_outcome_is_held(tmp_path)
    try:
        assert record["status"] == "incomplete" and record["pending"] >= 1
        # The process dies before the late drain gets its write: nothing more lands.
        for task in list(state._late_drains.values()):
            task.cancel()
        runtime.abandon_persistence()
        restore = await account.rebuild(state.database)
        assert restore.complete is False
        assert restore.checks["session_runs_with_unconfirmed_writes"] == [runtime.run_id], "R19 sees the queued write"
        assert restore.checks["round_trips_without_outcome"][0]["run_id"] == runtime.run_id, "R15 names what it was"
        async with state.database.session() as session:
            await RunRepository(session).acknowledge_persistence(runtime.run_id, actor="elian", reason="outcome lost at stop",
                                                                 at=datetime.now(UTC))
        after = await account.rebuild(state.database)
        assert after.complete, after.error
        assert after.checks["round_trips_without_outcome_acknowledged"][0]["run_id"] == runtime.run_id
    finally:
        gate.set()
        await state.database.close()


async def test_a_stop_whose_outcome_lands_late_is_upgraded_and_rebuilds_whole(tmp_path: Path) -> None:
    import asyncio

    state, runtime, (gate, record) = await _a_stop_whose_outcome_is_held(tmp_path)
    try:
        assert record["status"] == "incomplete"
        gate.set()  # the store answers after the stop: the late drain sees the write land
        for _ in range(200):
            if not state._late_drains:
                break
            await asyncio.sleep(0.01)
        async with state.database.session() as session:
            records = await RunRepository(session).persistence_records()
        assert records[runtime.run_id]["status"] == "complete_after_stop"
        restore = await account.rebuild(state.database)
        assert restore.complete, restore.error
        assert restore.checks["round_trips_without_outcome"] == []
    finally:
        await state.database.close()
