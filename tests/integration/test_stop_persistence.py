"""R19 — a stop, a shutdown and a restart with persistence writes still in flight.

Measured before this change (PLAN_R19_NUEVO v1, L2): the scenario stop's flush ran out of
its 10 s with 112-423 writes queued, ``stop_run`` stamped the run row as stopped anyway,
``shutdown`` closed the store under the queued writes, and the restarted process read one
closed trade where the first session had closed two (``test_restart_recovery``:
``assert 1 == 2``). Nothing on disk said the record was short.

Here the queue is held by a gate on the dispatcher (no sleeping, no load): every write
past the first few waits until the test releases it, exactly the state a slow store leaves
at stop. Numbered after the acceptance criteria of the mission:

1. the stop does not declare success while writes it owes are unconfirmed;
2. what a stop declares complete is on disk, and a refused write keeps it from saying so;
3. a flush that runs out says so in the answer, in the run row and in the runtime;
4. the restart tells confirmed records from unconfirmed ones (and the account rebuild,
   which decides whether a session may open positions, refuses to call itself complete);
5. no silent loss and no duplicate across the restart;
6. the stop stamp and its persistence mark commit together or not at all;
7. writes abandoned at shutdown (cancelled tasks) never leave a record read as complete.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.integration.test_live_api import _FakePublicFeed
from tests.integration.test_run_lifecycle import RUN, _runs, _state
from tia.api.state import AppState
from tia.persistence import AccountJournalRepository, EdgeStateRepository, RunRepository

TRADING_RUN = {**RUN, "seed": 11}  # the seed test_restart_recovery uses: it closes trades


def fake_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)


@pytest.fixture(autouse=True)
def _feed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_feed(monkeypatch)


def gate_writes(state: AppState, monkeypatch: pytest.MonkeyPatch, *, after: int) -> asyncio.Event:
    """Every write after the first ``after`` waits for the returned event."""
    real = state._persist
    gate = asyncio.Event()
    seen = {"n": 0}

    async def persist(kind: str, payload: Any) -> Any:
        seen["n"] += 1
        if seen["n"] > after:
            await gate.wait()
        return await real(kind, payload)

    monkeypatch.setattr(state, "_persist", persist)
    return gate


async def until(predicate: Any, *, limit_seconds: float = 120.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + limit_seconds
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0)


def mark_of(notes: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(notes) if notes else None
    except ValueError:
        return None
    return payload.get("persistence") if isinstance(payload, dict) else None


async def edge_outcomes(state_or_url: Any, run_id: str) -> int:
    database = state_or_url.database
    async with database.session() as session:
        return int((await session.execute(
            text("SELECT COUNT(*) FROM edge_outcomes WHERE run_id = :r"), {"r": run_id})).scalar() or 0)


async def incomplete_stop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[AppState, asyncio.Event, dict[str, Any]]:
    """A scenario run stopped with writes still queued behind the gate."""
    state = await _state(tmp_path)
    gate = gate_writes(state, monkeypatch, after=40)
    await state.start_run(dict(TRADING_RUN))
    assert state.runtime is not None
    state.runtime._flush_timeout_seconds = 0.2
    await until(lambda: not state.runtime.is_running)
    answer = await state.stop_run()
    return state, gate, answer


# 1 and 3 ------------------------------------------------------------------------------


async def test_1_3_a_stop_that_cannot_drain_says_so_in_its_answer_its_row_and_its_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _gate, answer = await incomplete_stop(tmp_path, monkeypatch)
    try:
        report = answer.get("persistence_at_stop")
        assert report is not None, "the stop answer says nothing about the writes it left behind"
        assert report["status"] == "incomplete" and report["pending"] > 0
        [(run_id, stopped_at, notes)] = await _runs(state)
        assert stopped_at is not None, "the stop happened; the stamp says when"
        mark = mark_of(notes)
        assert mark is not None and mark["status"] == "incomplete", "the row must not read as a clean stop"
        assert mark["pending"] == report["pending"]
        assert "still in flight" in (state.runtime.last_error or "")
        assert run_id in state.persistence_status()["incomplete_runs"]
    finally:
        state._shutdown_drain_seconds = 0.1
        await state.shutdown()


# 2 ------------------------------------------------------------------------------------


async def test_2_a_stop_declared_complete_has_its_record_on_disk(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    try:
        await state.start_run(dict(TRADING_RUN))
        engine = state.runtime
        await until(lambda: not engine.is_running)
        answer = await state.stop_run()
        report = answer.get("persistence_at_stop") or {}
        assert report.get("status") == "complete" and report.get("pending") == 0 and report.get("failed_writes") == 0
        closed = len(engine.closed_trades)
        assert closed > 0
        assert await edge_outcomes(state, engine.run_id) == closed
        [(_run_id, _stopped, notes)] = await _runs(state)
        assert (mark_of(notes) or {}).get("status") == "complete"
        assert state.persistence_status()["incomplete_runs"] == []
    finally:
        await state.shutdown()


async def test_2_a_write_the_store_refused_keeps_the_stop_from_declaring_the_run_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _state(tmp_path)
    real_append = EdgeStateRepository.append
    refused = {"n": 0}

    async def refuse_the_first(self: Any, payload: Any) -> Any:
        if refused["n"] == 0:
            refused["n"] += 1
            raise RuntimeError("disk I/O error")
        return await real_append(self, payload)

    monkeypatch.setattr(EdgeStateRepository, "append", refuse_the_first)
    try:
        await state.start_run(dict(TRADING_RUN))
        engine = state.runtime
        await until(lambda: not engine.is_running)
        answer = await state.stop_run()
        assert refused["n"] == 1
        report = answer.get("persistence_at_stop") or {}
        assert report.get("status") == "writes_failed", report
        assert report.get("failed_writes", 0) >= 1 and report.get("pending") == 0
        [(run_id, _stopped, notes)] = await _runs(state)
        assert (mark_of(notes) or {}).get("status") == "writes_failed"
        assert run_id in state.persistence_status()["incomplete_runs"]
    finally:
        await state.shutdown()


# 4 and 5 ------------------------------------------------------------------------------


async def test_4_5_a_restart_lists_the_run_whose_writes_were_lost_and_not_the_clean_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _gate, _answer = await incomplete_stop(tmp_path, monkeypatch)
    [(lost_run, _s, _n)] = await _runs(state)
    state._shutdown_drain_seconds = 0.1  # the writes stay held: they are lost with the process
    await state.shutdown()
    monkeypatch.undo()
    fake_feed(monkeypatch)

    reborn = await _state(tmp_path)
    await reborn.startup()
    try:
        assert lost_run in reborn.persistence_status()["incomplete_runs"], "the loss is not silent"
        await reborn.start_run(dict(TRADING_RUN, seed=12))
        engine = reborn.runtime
        await until(lambda: not engine.is_running)
        answer = await reborn.stop_run()
        assert (answer.get("persistence_at_stop") or {}).get("status") == "complete"
        assert reborn.persistence_status()["incomplete_runs"] == [lost_run], "only the run that lost writes"
    finally:
        await reborn.shutdown()


async def test_4_5_writes_that_land_after_the_stop_upgrade_the_mark_and_nothing_is_lost_or_doubled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, gate, answer = await incomplete_stop(tmp_path, monkeypatch)
    engine = state.runtime
    closed = len(engine.closed_trades)
    assert answer["persistence_at_stop"]["status"] == "incomplete"
    gate.set()  # the store catches up while the process still lives
    state._shutdown_drain_seconds = 30.0
    await state.shutdown()
    monkeypatch.undo()
    fake_feed(monkeypatch)

    reborn = await _state(tmp_path)
    await reborn.startup()
    try:
        [(run_id, _stopped, notes)] = await _runs(reborn)
        mark = mark_of(notes) or {}
        assert mark.get("status") == "complete_after_stop", mark
        assert mark.get("pending_at_stop", 0) > 0, "the late landing keeps the record of the short stop"
        assert reborn.persistence_status()["incomplete_runs"] == []
        assert await edge_outcomes(reborn, run_id) == closed, "every closed trade on disk"
        await reborn.start_run(dict(TRADING_RUN, seed=12))
        second = reborn.runtime
        await until(lambda: not second.is_running)
        await reborn.stop_run()
        async with reborn.database.session() as session:
            doubled = (await session.execute(text(
                "SELECT client_order_id FROM orders GROUP BY client_order_id HAVING COUNT(*) > 1"))).all()
        assert doubled == []
    finally:
        await reborn.shutdown()


async def test_4_the_account_rebuild_is_not_complete_over_a_session_run_with_unconfirmed_writes(tmp_path: Path) -> None:
    """The paper-live account is rebuilt from the journal, cross-checked against the fills
    table. A write lost at the tail of a session (the fill AND its journal event) passes
    that cross-check; the run's own persistence mark is what tells."""
    state = await _state(tmp_path)
    now = datetime.now(UTC)
    try:
        async with state.database.session() as session:
            repo = RunRepository(session)
            for run_id in ("pl_clean", "pl_short", "pl_legacy", "demo_short"):
                await repo.create(run_id=run_id, mode="paper" if run_id.startswith("demo") else "paper-live",
                                  scenario="live", started_at=now, initial_capital=10_000.0, seed=0, symbols=["BTC-USD"])
                await repo.stop(run_id, now)
        marks = {"pl_clean": {"status": "complete", "pending": 0, "failed_writes": 0},
                 "pl_short": {"status": "incomplete", "pending": 7, "failed_writes": 0},
                 "demo_short": {"status": "incomplete", "pending": 3, "failed_writes": 0}}
        async with state.database.session() as session:
            for run_id, mark in marks.items():
                await session.execute(text("UPDATE runs SET notes = :n WHERE run_id = :r"),
                                      {"n": json.dumps({"persistence": mark}), "r": run_id})

        async def rebuild() -> Any:
            async with state.database.session() as session:
                return await AccountJournalRepository(session).rebuild(
                    now=now, initial_capital=10_000.0, symbol="BTC-USD", modes=("paper-live",))

        restore = await rebuild()
        assert restore.complete is False, "a session run with unconfirmed writes cannot rebuild complete"
        assert "pl_short" in restore.error and "demo_short" not in restore.error
        assert restore.checks.get("session_runs_with_unconfirmed_writes") == ["pl_short"]

        async with state.database.session() as session:
            await RunRepository(session).acknowledge_persistence(
                "pl_short", actor="operator", reason="venue fills reconciled by hand", at=now)
        restore = await rebuild()
        assert restore.complete is True, "an operator's reconciliation is the door, and it is recorded"
        assert restore.checks.get("session_runs_acknowledged") == ["pl_short"]
    finally:
        await state.shutdown()


# 6 ------------------------------------------------------------------------------------


async def test_6_the_stop_stamp_and_its_persistence_mark_commit_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _state(tmp_path)
    try:
        await state.start_run(dict(RUN))
        engine = state.runtime
        await until(lambda: engine.counters.bars >= 3 or not engine.is_running)

        async def broken_mark(self: Any, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("store refused the mark")

        monkeypatch.setattr(RunRepository, "mark_persistence", broken_mark, raising=False)
        with pytest.raises(RuntimeError, match="refused the mark"):
            await state.stop_run()
        [(_run_id, stopped_at, notes)] = await _runs(state)
        assert stopped_at is None and mark_of(notes) is None, "neither the stamp nor the mark: one transaction"
    finally:
        await state.shutdown()


async def test_6_every_stamped_run_carries_its_mark_scenario_and_realtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _state(tmp_path)
    try:
        await state.start_run(dict(RUN))
        await until(lambda: state.runtime.counters.bars >= 3 or not state.runtime.is_running)
        await state.stop_run()
        gate = gate_writes(state, monkeypatch, after=0)  # before the start: the session binds the dispatcher
        await state.start_paper_realtime(actor="operator")
        state.live_runtime._flush_timeout_seconds = 0.2
        state.live_runtime._save("log", {"run_id": state.live_runtime.run_id, "level": "INFO",
                                         "component": "test", "message": "queued", "at": datetime.now(UTC)})
        answer = await state.stop_realtime_session(reason="operator")
        assert (answer.get("persistence_at_stop") or {}).get("status") == "incomplete", answer.get("persistence_at_stop")
        gate.set()
        rows = await _runs(state)
        assert len(rows) == 2
        for run_id, stopped_at, notes in rows:
            assert stopped_at is not None
            assert mark_of(notes) is not None, f"{run_id} is stamped without saying whether its writes landed"
    finally:
        await state.shutdown()


# 7 ------------------------------------------------------------------------------------


async def test_7_writes_abandoned_at_shutdown_are_cancelled_counted_and_never_read_as_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, _gate, answer = await incomplete_stop(tmp_path, monkeypatch)
    engine = state.runtime
    pending = answer["persistence_at_stop"]["pending"]
    state._shutdown_drain_seconds = 0.1
    await state.shutdown()
    assert all(task.done() for task in engine._persist_tasks), "no write task is left to die with the loop"
    monkeypatch.undo()
    fake_feed(monkeypatch)

    reborn = await _state(tmp_path)
    await reborn.startup()
    try:
        [(run_id, _stopped, notes)] = await _runs(reborn)
        mark = mark_of(notes) or {}
        assert mark.get("status") == "incomplete"
        assert 0 < mark.get("abandoned_at_shutdown", 0) <= pending
        assert run_id in reborn.persistence_status()["incomplete_runs"]
    finally:
        await reborn.shutdown()


async def test_7_a_loop_cancelled_at_stop_is_not_declared_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tia.runtime.engine import RuntimeEngine

    state = await _state(tmp_path)
    ticking = asyncio.Event()

    async def stuck(self: Any) -> None:
        ticking.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(RuntimeEngine, "_tick", stuck)  # the first bar never ends
    try:
        await state.start_run(dict(RUN))
        engine = state.runtime
        engine._stop_timeout_seconds = 0.1
        await asyncio.wait_for(ticking.wait(), timeout=10.0)
        answer = await state.stop_run()
        report = answer.get("persistence_at_stop") or {}
        assert report.get("status") == "incomplete" and report.get("loop_cancelled") is True, report
        [(_run_id, _stopped, notes)] = await _runs(state)
        assert (mark_of(notes) or {}).get("status") == "incomplete"
    finally:
        await state.shutdown()


async def test_7_a_process_that_dies_while_the_stop_drains_leaves_the_run_unconfirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stop's own record is written after the drain; a process killed during the drain
    (a container's grace period ending) never writes it. What it wrote before the drain
    must already say the run is not confirmed."""
    state = await _state(tmp_path)
    gate_writes(state, monkeypatch, after=40)
    await state.start_run(dict(TRADING_RUN))
    engine = state.runtime
    engine._flush_timeout_seconds = 60.0  # the drain outlives the process
    await until(lambda: not engine.is_running)
    stop = asyncio.create_task(state.stop_run())

    async def stopping_on_disk() -> bool:
        [(_r, _s, notes)] = await _runs(state)
        return (mark_of(notes) or {}).get("status") == "stopping"

    loop = asyncio.get_running_loop()
    deadline = loop.time() + 30
    while not await stopping_on_disk():
        assert loop.time() < deadline, "no record was written before the drain"
        await asyncio.sleep(0.01)
    stop.cancel()  # the process dies here: no stamp, no final record, no graceful shutdown
    with pytest.raises(asyncio.CancelledError):
        await stop
    engine.abandon_persistence()
    await state.database.close()
    monkeypatch.undo()
    fake_feed(monkeypatch)

    reborn = await _state(tmp_path)
    await reborn.startup()
    try:
        [(run_id, stopped_at, notes)] = await _runs(reborn)
        assert stopped_at is None
        assert (mark_of(notes) or {}).get("status") == "stopping"
        assert run_id in reborn.persistence_status()["incomplete_runs"]
    finally:
        await reborn.shutdown()


async def test_4_an_acknowledgement_needs_a_reason_and_an_unconfirmed_record(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    now = datetime.now(UTC)
    try:
        async with state.database.session() as session:
            repo = RunRepository(session)
            for run_id in ("clean", "short"):
                await repo.create(run_id=run_id, mode="paper-live", scenario="live", started_at=now,
                                  initial_capital=10_000.0, seed=0, symbols=["BTC-USD"])
            await repo.mark_persistence("clean", {"status": "complete", "pending": 0, "failed_writes": 0})
            await repo.mark_persistence("short", {"status": "incomplete", "pending": 4, "failed_writes": 0})
        for run_id, reason in (("short", "  "), ("clean", "reconciled"), ("missing", "reconciled")):
            with pytest.raises(ValueError):
                async with state.database.session() as session:
                    await RunRepository(session).acknowledge_persistence(run_id, actor="operator", reason=reason, at=now)
        async with state.database.session() as session:
            assert await RunRepository(session).unconfirmed_runs() == ["short"]
    finally:
        await state.shutdown()


async def test_6_a_shutdown_whose_record_cannot_be_written_still_releases_the_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The record and the lease release share a transaction; when the record cannot be
    written, the heartbeat is still released on its own (G9), as before R19."""
    from tia.runtime.session_limits import decode_heartbeat

    state = await _state(tmp_path)
    await state.start_paper_realtime(actor="operator")
    run_id = state.live_runtime.run_id
    for _ in range(200):  # let the session stamp its first heartbeat
        [(_r, _s, notes)] = await _runs(state)
        if decode_heartbeat(notes) is not None:
            break
        await asyncio.sleep(0.01)

    async def broken_mark(self: Any, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("store refused the mark")

    monkeypatch.setattr(RunRepository, "mark_persistence", broken_mark, raising=False)
    await state.shutdown()
    reader = await _state(tmp_path)
    try:
        [(seen, stopped_at, notes)] = await _runs(reader)
        assert seen == run_id and stopped_at is None, "a shutdown is not an operator stop: the boot resumes it"
        assert decode_heartbeat(notes) is None, "the lease was released even though the record was refused"
    finally:
        await reader.shutdown()
