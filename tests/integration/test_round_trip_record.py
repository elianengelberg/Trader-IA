"""R15 — a round trip is written in separate commits (order, fill, journal event, outcome).

Definition (new review, row R15): "persistencia no atómica: orden, fill y resultado van en
commits separados; la detección es parcial". What the code does: ``LiveRuntime._save``
schedules one write per artefact, each in its own session (``AppState._persist``). A write
the store refuses is absorbed and counted, and a process that dies between two commits
leaves the earlier ones on disk.

What is shown here, on a real paper engine and a real SQLite store:

* a session whose fill and journal writes were both refused rebuilds *complete* in the base
  (``test_account_restore`` asserts exactly that: "the store never saw the fill"); with the
  R19 stop record, the session's own count of refused writes reaches the run row, and the
  next rebuild is incomplete — the gap is detected, not repaired;
* a process that dies after a round trip's fill and journal event committed and before its
  outcome did used to leave a journal that rebuilt complete and a track record one trade short
  (a strict xfail until R15's fix); the journal event now names the outcome it closes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

from tests.integration.test_account_restore import (
    _db,
    build,
    open_position,
    persister,
    rebuild,
    register_run,
    settle,
)
from tia.persistence import RunRepository


async def test_r15_writes_refused_during_a_session_leave_the_next_rebuild_incomplete(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime, _engine, market, _clock = build(persist=persister(db, drop={"fill", "account_event"}))
        await register_run(db, runtime.run_id)
        await runtime.start()
        await open_position(runtime, market)
        await settle(runtime)
        await runtime.stop()
        await settle(runtime)
        report = runtime.persistence_report()  # what AppState._record_stop writes beside the stamp (R19)
        assert report["status"] == "writes_failed" and report["failed_writes"] >= 2, report
        async with db.session() as session:
            await RunRepository(session).stop(runtime.run_id, datetime.now(UTC))
            await RunRepository(session).mark_persistence(runtime.run_id, report)
        restore = await rebuild(db)
        assert restore.complete is False, "the base rebuilds complete over a fill the store never saw"
        assert runtime.run_id in restore.error
    finally:
        await db.close()


# R15 (fixed): was a strict xfail — a crash between a round trip's commits was not detected. The
# closing fill's journal event now names its outcome and the rebuild holds the journal against
# edge_outcomes; the systematic sweep over every commit boundary is test_r15_crash_recovery.py.
async def test_r15_a_round_trip_whose_outcome_was_lost_in_a_crash_is_not_read_as_complete(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        # The outcome never lands, exactly what a process killed between those commits leaves
        # behind (the harness writes outcomes since R15's fix; ``lose`` keeps this one away).
        runtime, _engine, market, _clock = build(persist=persister(db, lose={"edge_outcome"}))
        await register_run(db, runtime.run_id)
        await runtime.start()
        await open_position(runtime, market)
        if await runtime._close_position("time stop") is not True:
            raise RuntimeError("precondition: the exit was not sent")
        for _ in range(20):
            market.advance()
            await runtime._cycle_once()
            if runtime._open_trade is None:
                break
        if runtime.counters["round_trips"] != 1:
            raise RuntimeError("precondition: the round trip did not close")
        await settle(runtime)
        # the process dies here: no stop, no record
        restore = await rebuild(db)
        async with db.session() as session:
            outcomes = int((await session.execute(text("SELECT COUNT(*) FROM edge_outcomes"))).scalar() or 0)
        if outcomes != 0:
            raise RuntimeError("precondition: an outcome landed")
        # Preconditions raise RuntimeError, so only this assertion can satisfy the xfail.
        assert restore.complete is False, "a closed round trip with no outcome on disk is read as a complete record"
    finally:
        await runtime.stop()
        await db.close()
