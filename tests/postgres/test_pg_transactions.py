"""Transactions on PostgreSQL: commit, rollback, and what an error does to a session.

``Database.session()`` commits on success and rolls back on any exception. On SQLite a
failed statement leaves the transaction usable; on PostgreSQL it aborts the transaction,
and every later statement in it fails until a rollback. The repositories never catch an
error inside a session, so the contract holds on both — this file pins it on the server
production runs, together with the one multi-write unit the runtime relies on (the
``account_events`` batch of ``AppState._persist``) and the pool setting that exists only
for servers (``pool_pre_ping``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from tests.postgres.support import PgDatabases
from tia.core.config import Environment, settings_for_env
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Fill, Order
from tia.events.envelope import EventEnvelope
from tia.persistence import (
    Database,
    EventRepository,
    FillRepository,
    OrderRepository,
    RunRepository,
)
from tia.portfolio.account_journal import EVENT_MARK, AccountMarkPayload

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


async def _run(session, run_id: str = "run_tx", mode: str = "paper-live") -> None:  # type: ignore[no-untyped-def]
    await RunRepository(session).create(
        run_id=run_id, mode=mode, scenario="realtime", started_at=AT, initial_capital=10_000.0,
        seed=1, symbols=("BTC-USD",),
    )


def _order(order_id: str = "ord_1", *, client_order_id: str = "coid_1") -> Order:
    return Order(
        order_id=order_id, client_order_id=client_order_id, intent_id="int", signal_id="sig",
        symbol="BTC-USD", side=Side.BUY, order_type=OrderType.MARKET, quantity=0.01,
        state=OrderState.FILLED, filled_quantity=0.01, average_fill_price=50_000.0, fees_paid=0.5,
        created_at=AT, updated_at=AT,
    )


def _mark(run_id: str, event_id: str, idempotency_key: str, price: float = 50_000.0) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id, event_type=EVENT_MARK, source="live", occurred_at=AT, ingestion_at=AT,
        recorded_at=AT, correlation_id=run_id, idempotency_key=idempotency_key,
        payload=AccountMarkPayload(symbol="BTC-USD", price=price, at=AT),
    )


async def _count(database: Database, table: str) -> int:
    async with database.session() as session:
        return int((await session.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one())  # noqa: S608


async def test_a_committed_session_is_visible_to_another_engine(pg_db: Database, pg_url: str) -> None:
    """Another engine — another pool, as another process would hold — reads the commit."""
    async with pg_db.session() as session:
        await _run(session)
        await OrderRepository(session).upsert("run_tx", _order())
    other = Database(pg_url)
    try:
        async with other.session() as session:
            row = await OrderRepository(session).get("ord_1")
        assert row is not None and row.run_id == "run_tx" and row.state == "filled"
    finally:
        await other.close()


async def test_an_exception_rolls_back_every_write_of_the_session(pg_db: Database) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with pg_db.session() as session:
            await _run(session)
            await OrderRepository(session).upsert("run_tx", _order())
            await EventRepository(session).append("run_tx", _mark("run_tx", "evt_1", "mark:1"))
            raise RuntimeError("boom")
    for table in ("runs", "orders", "events"):
        assert await _count(pg_db, table) == 0, f"{table} kept a write of a rolled-back session"


async def test_a_constraint_violation_rolls_back_the_writes_before_it(pg_db: Database) -> None:
    """The run and the first order were written in the same session as an order that
    reuses a client order id: the unique constraint refuses it and nothing survives."""
    with pytest.raises(IntegrityError, match="uq_orders_client_id"):
        async with pg_db.session() as session:
            await _run(session)
            await OrderRepository(session).upsert("run_tx", _order("ord_1"))
            await OrderRepository(session).upsert("run_tx", _order("ord_2"))  # same client id
    assert await _count(pg_db, "runs") == 0
    assert await _count(pg_db, "orders") == 0


async def test_after_an_error_postgresql_refuses_the_rest_of_the_transaction(pg_db: Database) -> None:
    """The dialect difference itself: a statement after a failed one, in the same
    transaction, is refused (SQLite would run it). Code that caught an error inside a
    session and carried on would lose every later write on PostgreSQL only."""
    async with pg_db.session() as session:
        await _run(session)
    with pytest.raises(DBAPIError, match="current transaction is aborted"):
        async with pg_db.session() as session:
            with pytest.raises(IntegrityError):
                await OrderRepository(session).upsert("run_missing", _order())  # FK: no such run
            await OrderRepository(session).upsert("run_tx", _order())
    assert await _count(pg_db, "orders") == 0


async def test_the_account_events_batch_commits_together_or_not_at_all(pg_url: str, tmp_path: Path) -> None:
    """``AppState._persist('account_events')`` writes a funding settlement and its plan in
    one session (Phase 1.8). The second envelope here collides on the primary key: the
    first must not land alone, and the failure is counted, not hidden."""
    from tia.api.state import AppState

    state = AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": pg_url}))
    await state.database.ensure_schema()
    try:
        async with state.database.session() as session:
            await _run(session)
        await state._persist(
            "account_events",
            {"run_id": "run_tx", "envelopes": [
                _mark("run_tx", "evt_a", "mark:a"),
                _mark("run_tx", "evt_a", "mark:b"),  # same event_id, other key: PK violation
            ]},
        )
        status = state.persistence_status()
        assert status["failures"] == 1 and status["writes"] == 0, status
        assert "IntegrityError" in (status["last_error"] or "")
        assert await _count(state.database, "events") == 0, "half a batch reached the journal"

        await state._persist("account_events", {"run_id": "run_tx", "envelopes": [
            _mark("run_tx", "evt_a", "mark:a"), _mark("run_tx", "evt_b", "mark:b"),
        ]})
        assert state.persistence_status()["writes"] == 1
        assert await _count(state.database, "events") == 2
    finally:
        await state.database.close()


async def test_a_fill_written_after_its_order_in_one_session_lands(pg_db: Database) -> None:
    """Within one transaction the foreign key sees the order written just before."""
    fill = Fill(fill_id="fill_1", order_id="ord_1", sequence=0, symbol="BTC-USD", side=Side.BUY,
                quantity=0.01, price=50_000.0, fee=0.5, filled_at=AT)
    async with pg_db.session() as session:
        await _run(session)
        await OrderRepository(session).upsert("run_tx", _order())
        await FillRepository(session).append("run_tx", fill)
    assert await _count(pg_db, "fills") == 1


async def test_a_pooled_connection_the_server_dropped_is_replaced_by_the_pre_ping(
    pg_db: Database, pg_url: str, pg: PgDatabases,
) -> None:
    """``pool_pre_ping`` is on only outside SQLite (database.py). A server restart or an
    idle timeout kills pooled connections; the pre-ping finds the dead one at checkout
    and reconnects. The same pool without it hands the dead connection to the caller."""
    from sqlalchemy.ext.asyncio import create_async_engine

    async def backend_pid(run) -> int:  # type: ignore[no-untyped-def]
        return int((await run(text("SELECT pg_backend_pid()"))).scalar_one())

    async with pg_db.session() as session:
        pid = await backend_pid(session.execute)
    pg.server.admin(f"SELECT pg_terminate_backend({pid}, 5000)")
    async with pg_db.session() as session:
        assert await backend_pid(session.execute) != pid, "the dead connection was reused"
    assert await pg_db.ping() is True

    without = create_async_engine(pg_url, pool_pre_ping=False)
    try:
        async with without.connect() as conn:
            pid = await backend_pid(conn.execute)
        pg.server.admin(f"SELECT pg_terminate_backend({pid}, 5000)")
        with pytest.raises(DBAPIError):
            async with without.connect() as conn:
                await conn.execute(text("SELECT 1"))
    finally:
        await without.dispose()
