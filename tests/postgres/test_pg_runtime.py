"""Runtimes over PostgreSQL: persistence at stop, restart recovery, and books that agree.

Every write here goes through ``AppState._persist`` — the production dispatcher, every
kind — so a value PostgreSQL refuses shows up where production would show it: as an
absorbed, counted failure in ``persistence_status()``, not as an exception.

The consistency checks run on both dialects (``sqlite`` is the control): the same
session, the same assertions. A PostgreSQL-only failure is the difference between them.

Reused rather than rewritten: ``_run_paper_session`` (test_restart_recovery) and the
live-session plumbing of test_account_restore (``build``, ``open_position``,
``register_run``, ``settle``, ``rebuild``, ``engine_for``).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, text

from tests.integration import test_account_restore as account
from tests.integration.test_live_runtime import FakeMarketData, live_settings
from tests.integration.test_restart_recovery import _run_paper_session
from tests.postgres.support import PgDatabases
from tia.core.clock import SimulatedClock
from tia.core.config import Environment, settings_for_env
from tia.persistence import Database, EdgeStateRepository, IncidentRepository, RiskStateRepository
from tia.persistence.models import EquityPoint, FillRow, OrderRow, PositionRow, RunRecord

DIALECTS = ["postgresql", "sqlite"]

#: R24-H1 (fixed, migration 0008): incidents.kind was VARCHAR(32) and the live runtime writes
#: 'entries_blocked:position_unverified' (35) and 'entries_blocked:orders_unverified' (33);
#: SQLite stored them, PostgreSQL refused them (StringDataRightTruncation) and the dispatcher
#: absorbed the failure. The two tests below were strict xfails on PostgreSQL until the fix;
#: tests/postgres/test_pg_incidents.py covers every kind the code writes.


def _url(dialect: str, pg: PgDatabases, tmp_path: Path) -> str:
    if dialect == "sqlite":
        return f"sqlite+aiosqlite:///{tmp_path / 'control.db'}"
    return pg.url()


def _app_state(url: str) -> Any:
    from tia.api.state import AppState

    return AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": url}))


def _driven_by_hand(runtime: Any) -> Any:
    """``build`` starts the background loop with a zero poll interval, and with every
    kind persisted that loop writes a reconciliation per spin — tens of thousands a
    minute, a backlog no flush drains. Production polls every ten seconds; here the loop
    runs once at start and then waits, and the test drives the cycles."""
    runtime._poll_interval = 3600.0
    return runtime


def _record_persistence(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """What each AppState's dispatcher absorbed, read just before it shuts down."""
    from tia.api.state import AppState

    seen: list[dict[str, Any]] = []
    real = AppState.shutdown

    async def shutdown(self: AppState) -> None:
        seen.append(self.persistence_status())
        await real(self)

    monkeypatch.setattr(AppState, "shutdown", shutdown)
    return seen


# ----------------------------------------------------------------------- restart recovery


async def test_restart_recovery(pg_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``test_restart_recovery`` of the SQLite suite, over PostgreSQL: RUN → persist →
    die → restart → the evidence is back and nothing doubled; plus the dispatcher's
    count of absorbed write failures, which the SQLite test does not read."""
    from tia.api.state import AppState

    absorbed = _record_persistence(monkeypatch)
    closed_first = await _run_paper_session(pg_url, seed=11)
    assert closed_first > 0, "the first session closed nothing, so recovery has nothing to prove"

    database = Database(pg_url)
    await database.ensure_schema()
    async with database.session() as session:
        assert await EdgeStateRepository(session).count() == closed_first

    reborn = AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": pg_url}))
    await reborn.startup()
    try:
        await reborn.start_run({"scenario": "trend_up", "initial_capital": 10_000.0, "seed": 12,
                                "bar_interval_seconds": 0.0})
        engine = reborn.runtime
        assert engine is not None
        assert engine._prior_outcome_count == closed_first, "the restarted engine did not reload its evidence"
        assert sum(engine._edges.coverage().values()) >= closed_first
        for _ in range(120_000):
            await asyncio.sleep(0)
            if not engine.is_running:
                break
        await reborn.stop_run()
        assert engine.persistence_flushed is True
    finally:
        await reborn.shutdown()

    async with database.session() as session:
        final_count = await EdgeStateRepository(session).count()
        order_rows = (await session.execute(
            text("SELECT client_order_id, COUNT(*) FROM orders GROUP BY client_order_id")
        )).all()
        runs = (await session.execute(select(RunRecord.run_id, RunRecord.stopped_at))).all()
    await database.close()
    assert final_count >= closed_first, "evidence went missing across the restart"
    assert not [row for row in order_rows if row[1] > 1], "orders duplicated across restart"
    assert len(runs) == 2 and all(stopped is not None for _, stopped in runs), runs
    assert [status["failures"] for status in absorbed] == [0, 0], absorbed


# ------------------------------------------------------------------- persistence at stop


@pytest.mark.parametrize("dialect", DIALECTS)
async def test_a_stopped_scenario_run_has_every_write_on_disk(dialect: str, pg: PgDatabases, tmp_path: Path) -> None:
    """``stop_run`` returns after the engine's flush: right then — no sleeping — the
    store holds every fill, every order a fill references, the closed round trips, an
    equity curve, positions that agree with the fills, and the run stamped."""
    state = _app_state(_url(dialect, pg, tmp_path))
    await state.startup()
    try:
        await state.start_run({"scenario": "trend_up", "initial_capital": 10_000.0, "seed": 11,
                               "bar_interval_seconds": 0.0})
        engine = state.runtime
        assert engine is not None
        for _ in range(120_000):
            await asyncio.sleep(0)
            if not engine.is_running:
                break
        await state.stop_run()
        assert engine.persistence_flushed is True, engine.last_error
        assert not [t for t in engine._persist_tasks if not t.done()]

        async with state.database.session() as session:
            fills = (await session.execute(select(FillRow).where(FillRow.run_id == engine.run_id))).scalars().all()
            orders = {o.order_id: o for o in (await session.execute(
                select(OrderRow).where(OrderRow.run_id == engine.run_id))).scalars()}
            positions = {p.symbol: p for p in (await session.execute(
                select(PositionRow).where(PositionRow.run_id == engine.run_id))).scalars()}
            equity = (await session.execute(
                select(EquityPoint).where(EquityPoint.run_id == engine.run_id))).scalars().all()
            run = await session.get(RunRecord, engine.run_id)
            outcomes = await EdgeStateRepository(session).count()
        status = state.persistence_status()
    finally:
        await state.shutdown()

    assert status["failures"] == 0, status
    assert len(fills) == engine.counters.fills > 0
    assert outcomes == len(engine.closed_trades) > 0
    assert run is not None and run.stopped_at is not None
    assert equity, "no equity curve persisted"
    by_order: dict[str, list[FillRow]] = defaultdict(list)
    for fill in fills:
        by_order[fill.order_id].append(fill)
    for order_id, its_fills in by_order.items():
        order = orders[order_id]
        assert order.filled_quantity == pytest.approx(sum(f.quantity for f in its_fills), rel=1e-12)
        assert order.fees_paid == pytest.approx(sum(f.fee for f in its_fills), rel=1e-9, abs=1e-12)
    net: dict[str, float] = defaultdict(float)
    for fill in fills:
        net[fill.symbol] += fill.quantity if fill.side == "buy" else -fill.quantity
    held = {s: p.quantity for s, p in engine.execution.portfolio.positions.items()}
    for symbol, quantity in net.items():
        assert held.get(symbol, 0.0) == pytest.approx(quantity, abs=1e-9), (symbol, held, net)
        if symbol in positions:
            # The table is synced on the equity tick; a fill after the last tick is the
            # only way it may lag, and then it lags the fills, never disagrees in sign.
            assert positions[symbol].quantity == pytest.approx(quantity, abs=1e-9) or (
                positions[symbol].updated_at <= max(f.filled_at for f in fills if f.symbol == symbol)
            ), (symbol, positions[symbol].quantity, quantity)


async def test_a_stop_while_the_server_holds_the_writes_says_so_and_a_later_flush_lands_them(
    pg: PgDatabases,
) -> None:
    """The stop contract against a real lock instead of a fake persister: another
    session holds ``equity_points`` in EXCLUSIVE mode (reads allowed, writes wait), the
    engine's sequenced writes queue behind it, and ``stop`` returns at its flush timeout
    saying the record may be incomplete. Released, a later flush lands every write."""
    state = _app_state(pg.url())
    await state.startup()
    holder = pg.engine().connect()
    try:
        transaction = holder.begin()
        holder.execute(text("LOCK TABLE equity_points IN EXCLUSIVE MODE"))
        await state.start_run({"scenario": "trend_up", "initial_capital": 10_000.0, "seed": 11,
                               "bar_interval_seconds": 0.0})
        engine = state.runtime
        assert engine is not None
        engine._flush_timeout_seconds = 0.5
        for _ in range(120_000):
            await asyncio.sleep(0)
            if not engine.is_running:
                break
        await state.stop_run()
        assert engine.persistence_flushed is False
        assert "still in flight" in (engine.last_error or "")
        transaction.commit()
        assert await engine.flush_persistence(timeout_seconds=60.0) is True
        async with state.database.session() as session:
            fills = (await session.execute(
                select(func.count()).select_from(FillRow).where(FillRow.run_id == engine.run_id)
            )).scalar_one()
            points = (await session.execute(
                select(func.count()).select_from(EquityPoint).where(EquityPoint.run_id == engine.run_id)
            )).scalar_one()
        assert fills == engine.counters.fills > 0
        assert points > 0
        assert state.persistence_status()["failures"] == 0
    finally:
        holder.close()
        await state.shutdown()


@pytest.mark.parametrize("dialect", DIALECTS)
async def test_a_live_session_s_books_agree_across_orders_fills_journal_and_engine(
    dialect: str, pg: PgDatabases, tmp_path: Path,
) -> None:
    """One paper-live round trip over ``AppState._persist``, stopped, then read back:
    orders, fills, the account journal, the risk rebuild, the evidence and the engine
    tell the same story."""
    state = _app_state(_url(dialect, pg, tmp_path))
    await state.database.ensure_schema()
    try:
        runtime, engine, market, _clock = account.build(persist=state._persist)
        _driven_by_hand(runtime)
        await account.register_run(state.database, runtime.run_id)
        await runtime.start()
        try:
            await account.open_position(runtime, market)
            for _ in range(3):
                market.advance()
                await runtime._cycle_once()
            assert await runtime._close_position("time stop") is True
            market.advance()
            await runtime._cycle_once()
            assert runtime._open_trade is None and runtime.counters["round_trips"] == 1
            await account.settle(runtime)
        finally:
            await runtime.stop()
        assert runtime.persistence_flushed is True

        status = state.persistence_status()
        portfolio = await engine.get_portfolio()
        engine_orders = {o.order_id: o for o in await engine.get_orders()}
        async with state.database.session() as session:
            orders = {o.order_id: o for o in (await session.execute(
                select(OrderRow).where(OrderRow.run_id == runtime.run_id))).scalars()}
            fills = (await session.execute(
                select(FillRow).where(FillRow.run_id == runtime.run_id))).scalars().all()
            risk = await RiskStateRepository(session).rebuild(now=datetime.now(UTC))
            outcomes = await EdgeStateRepository(session).load_all()
            run = await session.get(RunRecord, runtime.run_id)
        restore = await account.rebuild(state.database)
    finally:
        await state.database.close()

    assert status["failures"] == 0, status
    assert set(orders) == set(engine_orders), "an order the engine holds is not in the store, or the reverse"
    for order_id, row in orders.items():
        held = engine_orders[order_id]
        assert row.state == held.state.value and row.filled_quantity == held.filled_quantity
        its = [f for f in fills if f.order_id == order_id]
        assert row.filled_quantity == pytest.approx(sum(f.quantity for f in its), rel=1e-12)
    assert len(fills) == runtime.counters["fills"] >= 2
    assert restore.complete, restore.error
    assert not restore.has_position and runtime._open_trade is None
    assert restore.cash == pytest.approx(portfolio.cash, abs=1e-9)
    assert restore.fees_paid == pytest.approx(portfolio.fees_paid, abs=1e-12)
    assert restore.fills_seen == len(fills)
    assert risk.complete and risk.orders_seen == len(orders) and risk.fills_seen == len(fills)
    assert [o.run_id for o in outcomes] == [runtime.run_id] and outcomes[0].exit_reason == "time stop"
    # The runtime's own stop leaves the stamp to its owner (AppState.stop_realtime_session).
    assert run is not None and run.mode == "paper-live"


# ----------------------------------------------------------------------- finding R24-H1


@pytest.mark.parametrize(
    "dialect",
    ["postgresql", "sqlite"],  # R24-H1 fixed by migration 0008: no longer an expected failure
)
async def test_every_incident_kind_the_live_runtime_writes_fits_the_incidents_table(
    dialect: str, pg: PgDatabases, tmp_path: Path,
) -> None:
    """The kinds ``LiveRuntime._block_entries`` writes, through the repository."""
    database = Database(_url(dialect, pg, tmp_path))
    await database.ensure_schema()
    refused: dict[str, str] = {}
    try:
        for key in ("account_state", "orders_unverified", "position_unverified"):
            kind = f"entries_blocked:{key}"
            try:
                async with database.session() as session:
                    await IncidentRepository(session).record({
                        "incident_id": f"inc_{key}", "at": datetime.now(UTC), "kind": kind,
                        "actor": "system", "reason": "test", "run_id": "live_x", "detail": {},
                    })
            except Exception as exc:
                refused[f"{kind} ({len(kind)} chars)"] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
    finally:
        await database.close()
    assert refused == {}, refused


@pytest.mark.parametrize(
    "dialect",
    ["postgresql", "sqlite"],  # R24-H1 fixed by migration 0008: no longer an expected failure
)
async def test_an_untracked_position_at_restart_is_recorded_as_an_incident(
    dialect: str, pg: PgDatabases, tmp_path: Path,
) -> None:
    """The path that writes it: session A dies holding a leg; session B's engine holds
    the position but B tracks no round trip (``test_adverse_recovery``'s second act). B
    blocks entries and must leave the incident in the record."""
    state = _app_state(_url(dialect, pg, tmp_path))
    await state.database.ensure_schema()
    try:
        runtime_a, engine_a, market_a, clock_a = account.build(persist=state._persist)
        _driven_by_hand(runtime_a)
        await account.register_run(state.database, runtime_a.run_id)
        await runtime_a.start()
        await account.open_position(runtime_a, market_a)
        await account.settle(runtime_a)
        runtime_a._stop_requested = True
        await runtime_a._finalize_stop()  # the process dies
        await account.settle(runtime_a)

        clock_b = SimulatedClock(clock_a.now())
        market_b = FakeMarketData(market_a._candles, clock_b)
        market_b.cursor = market_a.cursor
        engine_b = account.engine_for(clock_b, live_settings())
        engine_b.restore_portfolio(await engine_a.get_portfolio())
        runtime_b, _, _, _ = account.build(persist=state._persist, engine=engine_b, clock=clock_b, market=market_b)
        _driven_by_hand(runtime_b)
        await account.register_run(state.database, runtime_b.run_id)
        await runtime_b.start()
        try:
            market_b.advance()
            await runtime_b._cycle_once()
            assert "position_unverified" in runtime_b.entry_blocks
            await account.settle(runtime_b)
        finally:
            await runtime_b.stop()
        async with state.database.session() as session:
            kinds = [row.kind for row in await IncidentRepository(session).recent(limit=500)]
        status = state.persistence_status()
    finally:
        await state.database.close()
    assert "entries_blocked:position_unverified" in kinds and status["failures"] == 0, {
        "persistence": status, "incident_kinds": kinds,
    }
