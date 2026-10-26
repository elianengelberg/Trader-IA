"""Two sessions at once, on PostgreSQL.

SQLite serialises writers on one file lock; PostgreSQL runs them concurrently under READ
COMMITTED, with row locks only where two writers touch the same row. What that changes
for the code that reads and writes shared rows:

* the session lease (``RunRepository.open_sessions`` / ``heartbeat``): a heartbeat is
  seen by another process exactly when it commits, never before;
* idempotent upserts racing on one key serialise on the row instead of erroring — when
  the key is the conflict target; ``events`` also repeats its primary key, and two
  overlapping writers of one event make the second fail (finding R24-H3, below);
* the heartbeat lease detects another process but does not exclude it (H11 in
  ``docs/PHASE_1_4_SYSTEM_AUDIT_REPORT.md``) — reproduced here with two ``AppState``\\ s
  over one database, which the audit could not do on SQLite;
* ``edge_outcomes.ingested_at`` defaults to ``CURRENT_TIMESTAMP``, which PostgreSQL
  evaluates at the *start* of the writing transaction, not at commit: a row committed
  after a newer one carries the older stamp (finding R24-H2, below).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.integration.test_live_api import _settings
from tests.postgres.support import PgDatabases
from tia.core.config import Environment, settings_for_env
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Order
from tia.events.envelope import EventEnvelope
from tia.persistence import (
    Database,
    EdgeStateRepository,
    EventRepository,
    OrderRepository,
    RunRepository,
)
from tia.portfolio.account_journal import EVENT_MARK, AccountMarkPayload
from tia.runtime.session_limits import decode_heartbeat, lease_is_held

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


async def _open_run(database: Database, run_id: str, *, notes: str = "") -> None:
    async with database.session() as session:
        await RunRepository(session).create(
            run_id=run_id, mode="paper-live", scenario="realtime",
            started_at=datetime.now(UTC) - timedelta(minutes=5), initial_capital=10_000.0, seed=1,
            symbols=("BTC-USD",), notes=notes,
        )


def _order(state: OrderState, filled: float) -> Order:
    return Order(
        order_id="ord_race", client_order_id="coid_race", intent_id="int", signal_id="sig",
        symbol="BTC-USD", side=Side.BUY, order_type=OrderType.LIMIT, quantity=0.02, limit_price=50_000.0,
        state=state, filled_quantity=filled, average_fill_price=50_000.0 if filled else 0.0,
        fees_paid=0.0, created_at=AT, updated_at=AT,
    )


def _outcome(outcome_id: str, run_id: str) -> dict[str, Any]:
    return {
        "outcome_id": outcome_id, "run_id": run_id, "signal_id": outcome_id, "symbol": "BTC-USD",
        "regime": "trending_up", "direction": "long", "confidence": 0.7, "entry_price": 50_000.0,
        "exit_price": 50_100.0, "quantity": 0.01, "gross_bps": 20.0, "fees_bps": 10.0,
        "net_bps": 10.0, "closed_at": AT, "source": "sim",
    }


# --------------------------------------------------------------------------- the lease


async def test_another_process_sees_a_heartbeat_when_it_commits_and_not_before(pg_db: Database, pg_url: str) -> None:
    """Process A stamps its heartbeat; process B (its own engine) runs the lease read of
    a start (``open_sessions`` + ``lease_is_held``) while A's transaction is open and
    again after it commits."""
    await _open_run(pg_db, "run_a")
    other = Database(pg_url)
    try:
        async with pg_db.session() as session_a:
            await RunRepository(session_a).heartbeat("run_a", datetime.now(UTC))
            await session_a.flush()
            async with other.session() as session_b:
                (run_id, notes), = await RunRepository(session_b).open_sessions(mode="paper-live")
            assert run_id == "run_a" and decode_heartbeat(notes) is None, "an uncommitted beat is invisible"
            assert not lease_is_held(notes, now=datetime.now(UTC))
        async with other.session() as session_b:
            (run_id, notes), = await RunRepository(session_b).open_sessions(mode="paper-live")
        assert lease_is_held(notes, now=datetime.now(UTC)), "a committed beat holds the lease"
    finally:
        await other.close()


async def test_a_second_app_state_reads_the_first_ones_lease(pg_url: str, tmp_path: Path) -> None:
    """``AppState._foreign_session_lease`` — the read a start does before claiming the
    account — over another engine, against a heartbeat another engine committed."""
    from tia.api.state import AppState

    writer = Database(pg_url)
    await writer.ensure_schema()
    await _open_run(writer, "run_elsewhere")
    reader = AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": pg_url}))
    try:
        assert await reader._foreign_session_lease(mode="paper-live") is None, "no beat yet"
        async with writer.session() as session:
            await RunRepository(session).heartbeat("run_elsewhere", datetime.now(UTC) - timedelta(seconds=7))
        held = await reader._foreign_session_lease(mode="paper-live")
        assert held is not None and held[0] == "run_elsewhere" and 6.0 <= held[1] < 60.0
        async with writer.session() as session:
            await RunRepository(session).release_lease("run_elsewhere")
        assert await reader._foreign_session_lease(mode="paper-live") is None, "released"
    finally:
        await reader.database.close()
        await writer.close()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "known limit H11 (docs/PHASE_1_4_SYSTEM_AUDIT_REPORT.md): the heartbeat lease detects "
        "another process but does not exclude two starting in the same window — reproduced "
        "on PostgreSQL with two AppStates over one database"
    ),
)
async def test_two_processes_starting_together_end_with_at_most_one_session(
    pg: PgDatabases, tmp_path: Path, fake_public_feed: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tia.api.state import AppState

    settings = _settings(tmp_path).model_copy(update={"database_url": pg.url()})
    first, second = AppState(settings), AppState(settings)
    await first.database.ensure_schema()
    # Both read the lease before either writes its run row: the interleaving two
    # processes can produce and the in-process lock cannot see.
    barrier = asyncio.Barrier(2)
    real = AppState._load_account_restore

    async def after_the_lease_read(self: AppState, **kwargs: Any) -> Any:
        await asyncio.wait_for(barrier.wait(), timeout=10.0)
        return await real(self, **kwargs)

    monkeypatch.setattr(AppState, "_load_account_restore", after_the_lease_read)
    try:
        results = await asyncio.gather(
            first.start_paper_realtime(actor="process-a"),
            second.start_paper_realtime(actor="process-b"),
            return_exceptions=True,
        )
        running = [s for s in (first, second) if s.live_runtime is not None and s.live_runtime.is_running]
        async with first.database.session() as session:
            open_runs = await RunRepository(session).open_sessions(mode="paper-live")
        assert len(running) <= 1 and len(open_runs) <= 1, {"results": results, "open_runs": open_runs}
    finally:
        await first.shutdown()
        await second.shutdown()


# ------------------------------------------------------------------- racing upserts


async def test_two_upserts_of_one_order_serialise_on_the_row(pg_db: Database, pg_url: str) -> None:
    """Session A upserts the order and holds its transaction; session B's upsert of the
    same order waits on the row lock (no error, no second row) and lands after A."""
    await _open_run(pg_db, "run_race")
    other = Database(pg_url)
    try:
        async with pg_db.session() as session_a:
            await OrderRepository(session_a).upsert("run_race", _order(OrderState.ACKNOWLEDGED, 0.0))

            async def b_upserts() -> None:
                async with other.session() as session_b:
                    await OrderRepository(session_b).upsert("run_race", _order(OrderState.FILLED, 0.02))

            b = asyncio.create_task(b_upserts())
            await asyncio.sleep(0.3)
            assert not b.done(), "B did not wait for A's row"
        await asyncio.wait_for(b, timeout=10.0)
        async with pg_db.session() as session:
            rows = (await session.execute(text("SELECT state, filled_quantity FROM orders"))).all()
        assert [tuple(r) for r in rows] == [("filled", 0.02)]
    finally:
        await other.close()


#: R24-H3 (fixed): EventRepository.append upserts ON CONFLICT (idempotency_key), but a
#: redelivered envelope also repeats the primary key event_id; PostgreSQL arbitrates only the
#: conflict-target index, so a writer that overlapped another writer of the same event failed
#: with UniqueViolation on events_pkey. The append now retries once in a savepoint on exactly
#: that conflict (tests/postgres/test_pg_events_race.py). This test was a strict xfail until then.

#: Test instrumentation, PostgreSQL only: an extra index whose expression sleeps, created
#: (and the conflict-target constraint re-created after it) so that it is maintained
#: between the primary key and ``uq_events_idempotency``. It widens a microsecond window
#: to a fixed 0.4 s without changing what the statements do; without it the same race
#: was measured at 5 to 11 rounds in 100 (five writers per round) and 0 in 100 on SQLite.
_WIDEN_THE_WINDOW = (
    "CREATE FUNCTION r24_slow(value text) RETURNS text LANGUAGE plpgsql IMMUTABLE AS "
    "$$ BEGIN PERFORM pg_sleep(0.4); RETURN value; END $$",
    "CREATE INDEX r24_slow_ix ON events (r24_slow(event_id))",
    "ALTER TABLE events DROP CONSTRAINT uq_events_idempotency",
    "ALTER TABLE events ADD CONSTRAINT uq_events_idempotency UNIQUE (idempotency_key)",
)


@pytest.mark.parametrize(
    "dialect",
    ["postgresql", "sqlite"],  # R24-H3 fixed (savepoint + one retry on events_pkey): no longer an expected failure
)
async def test_two_writers_of_one_redelivered_event_store_it_once_without_errors(
    dialect: str, pg: PgDatabases, tmp_path: Path,
) -> None:
    """Writer B appends an account event while writer A is still writing the same one.
    ``EventRepository.append`` says the database resolves that race ("two writers racing
    the same redelivered event ... only one survives the constraint"): one row, and no
    writer sees an error — under ``AppState._persist`` an error is a counted persistence
    failure and, for an ``account_events`` batch, the whole batch is rolled back."""
    url = pg.url() if dialect == "postgresql" else f"sqlite+aiosqlite:///{tmp_path / 'control.db'}"
    setup = Database(url)
    await setup.ensure_schema()
    await _open_run(setup, "run_events")
    if dialect == "postgresql":
        async with setup.session() as session:
            for statement in _WIDEN_THE_WINDOW:
                await session.execute(text(statement))
    envelope: EventEnvelope[Any] = EventEnvelope(
        event_id="evt_once", event_type=EVENT_MARK, source="live", occurred_at=AT, ingestion_at=AT,
        recorded_at=AT, correlation_id="run_events", idempotency_key="mark:once",
        payload=AccountMarkPayload(symbol="BTC-USD", price=50_000.0, at=AT),
    )
    writer_a, writer_b = Database(url), Database(url)
    try:
        for database in (writer_a, writer_b):
            assert await database.ping()

        async def append(database: Database) -> None:
            async with database.session() as session:
                await EventRepository(session).append("run_events", envelope)

        first = asyncio.create_task(append(writer_a))
        await asyncio.sleep(0.15)
        results = await asyncio.gather(first, append(writer_b), return_exceptions=True)
        async with setup.session() as session:
            stored = (await session.execute(text("SELECT COUNT(*) FROM events"))).scalar_one()
        errors = [f"{type(r).__name__}: {str(r).splitlines()[0][:200]}" for r in results if isinstance(r, Exception)]
        assert stored == 1, stored
        assert errors == [], errors
    finally:
        for database in (writer_a, writer_b, setup):
            await database.close()


# ------------------------------------------------------- the evidence refresher's clock


@pytest.mark.parametrize(
    "dialect",
    [
        "postgresql",
        pytest.param("sqlite", marks=pytest.mark.xfail(strict=True, reason=(
            "side observation R24-O1 (SQLite, not PostgreSQL): CURRENT_TIMESTAMP is stored as "
            "'YYYY-MM-DD HH:MM:SS' text and the bound watermark carries '.000000', so the "
            "text comparison makes the 'inclusive' boundary exclusive"
        ))),
    ],
)
async def test_load_since_is_inclusive_of_its_watermark(dialect: str, pg: PgDatabases, tmp_path: Path) -> None:
    """``load_since`` promises an inclusive boundary ("two rows can share a timestamp"):
    the row the watermark was read from is returned again, and de-duplicated by id."""
    url = pg.url() if dialect == "postgresql" else f"sqlite+aiosqlite:///{tmp_path / 'control.db'}"
    database = Database(url)
    await database.ensure_schema()
    try:
        async with database.session() as session:
            await EdgeStateRepository(session).append(_outcome("o-1", "run_a"))
        async with database.session() as session:
            rows = await EdgeStateRepository(session).load_since(None)
            watermark = max(row.ingested_at for row in rows)
            again = await EdgeStateRepository(session).load_since(watermark)
    finally:
        await database.close()
    assert [row.outcome_id for row in again] == ["o-1"], (watermark, [r.ingested_at for r in rows])


class _RunningSession:
    """The two attributes and one method ``refresh_session_evidence`` uses."""

    run_id = "live_session"
    is_running = True

    def __init__(self) -> None:
        self.absorbed: list[str] = []

    def absorb_evidence(self, *, outcomes: Any, reviews: Any) -> dict[str, Any]:
        self.absorbed.extend(review["signal_id"] for review in reviews)
        return {}


# R24-H2 (fixed): on PostgreSQL CURRENT_TIMESTAMP is the writing transaction's start, so a row
# committed after the refresher's watermark can carry an older ingested_at and load_since(watermark)
# never returns it. The refresher now checks the table's count against what the session holds and
# resolves a mismatch by id (tests/integration/test_evidence_refresh_completeness.py). This test was
# a strict xfail until then.
async def test_evidence_committed_after_a_newer_row_still_reaches_the_running_session(
    pg_url: str,
) -> None:
    """A training batch's transaction (T1) inserts a row and is still open when the
    session's own trade (T2) commits; the refresher runs; then T1 commits. The batch's
    row must reach the session on the next refresh."""
    from tia.api.state import AppState

    state = AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": pg_url}))
    await state.database.ensure_schema()
    session = _RunningSession()
    state.live_runtime = session
    batch, own = Database(pg_url), Database(pg_url)
    try:
        assert (await state.refresh_session_evidence())["absorbed"] == 0
        async with batch.session() as t1:
            await EdgeStateRepository(t1).append(_outcome("train-1", "train_batch"))
            await asyncio.sleep(0.05)
            async with own.session() as t2:
                await EdgeStateRepository(t2).append(_outcome("own-1", "live_session"))
            first = await state.refresh_session_evidence()
        second = await state.refresh_session_evidence()
        async with state.database.session() as db:
            stamps = dict((await db.execute(text("SELECT outcome_id, ingested_at FROM edge_outcomes"))).all())
        assert "train-1" in session.absorbed, {
            "first_refresh": first, "second_refresh": second, "watermark": state._evidence_watermark,
            "ingested_at": stamps, "absorbed": session.absorbed,
        }
    finally:
        state.live_runtime = None
        await batch.close()
        await own.close()
        await state.database.close()
