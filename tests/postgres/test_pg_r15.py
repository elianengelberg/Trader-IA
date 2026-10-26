"""R15 on PostgreSQL: the commit-boundary sweep, and two writers of one round trip's rows.

The sweep is ``tests/integration/test_r15_crash_recovery.py`` run unchanged against PostgreSQL
(its store factory redirected, as ``Redirect`` does for the other reused suites). The writers:
two sessions upserting the same outcome and the same fill at once — the matrix's point 9. Both
upserts name their primary key as the conflict target, so PostgreSQL makes the second wait for
the first and turns it into an update: one row, no error. The window is widened with the same
sleeping-index instrumentation as R24-H3, so the overlap is certain rather than likely.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.integration import test_r15_crash_recovery as r15
from tests.integration.test_account_restore import _fill
from tests.postgres.support import PgDatabases
from tia.core.config import Environment, settings_for_env
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Order
from tia.persistence import (
    Database,
    EdgeStateRepository,
    FillRepository,
    OrderRepository,
    RunRepository,
)

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def on_postgresql(pg: PgDatabases, monkeypatch: pytest.MonkeyPatch) -> PgDatabases:
    from tia.api.state import AppState

    def _state(tmp_path: Path, name: str = "r15.db") -> Any:
        return AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": pg.url(name)}))

    monkeypatch.setattr(r15, "_state", _state)
    return pg


async def test_the_commit_boundary_sweep_holds_on_postgresql(on_postgresql: PgDatabases, tmp_path: Path) -> None:
    await r15.test_at_every_commit_boundary_complete_means_consistent_and_consistent_means_complete(tmp_path)
    assert len(on_postgresql.names) > 10, "every boundary ran on a database of its own"


async def test_the_missing_outcome_is_named_on_postgresql(on_postgresql: PgDatabases, tmp_path: Path) -> None:
    await r15.test_a_round_trip_the_journal_closed_without_its_outcome_is_named_and_blocks_the_next_session(tmp_path)


def _slow_index(table: str, column: str) -> tuple[str, ...]:
    return (
        "CREATE OR REPLACE FUNCTION r15_slow(value text) RETURNS text LANGUAGE plpgsql IMMUTABLE AS "
        "$$ BEGIN PERFORM pg_sleep(0.4); RETURN value; END $$",
        f"CREATE INDEX r15_slow_{table} ON {table} (r15_slow({column}))",
    )


def _outcome() -> dict[str, Any]:
    return {
        "outcome_id": "edge_once", "run_id": "live_r15", "signal_id": "sig", "symbol": "BTC-USD",
        "regime": "trending_up", "direction": "long", "confidence": 0.7, "entry_price": 50_000.0,
        "exit_price": 50_100.0, "quantity": 0.01, "gross_bps": 20.0, "fees_bps": 10.0, "net_bps": 10.0,
        "closed_at": AT, "source": "live",
    }


async def _two_writers(url: str, write: Any) -> list[str]:
    a, b = Database(url), Database(url)
    try:
        for database in (a, b):
            assert await database.ping()

        async def one(database: Database) -> None:
            async with database.session() as session:
                await write(session)

        first = asyncio.create_task(one(a))
        await asyncio.sleep(0.15)
        results = await asyncio.gather(first, one(b), return_exceptions=True)
        return [f"{type(r).__name__}: {str(r).splitlines()[0][:160]}" for r in results if isinstance(r, Exception)]
    finally:
        await a.close()
        await b.close()


async def _setup(url: str, table: str, column: str) -> Database:
    db = Database(url)
    await db.ensure_schema()
    async with db.session() as session:
        await RunRepository(session).create(run_id="live_r15", mode="paper-live", scenario="realtime", started_at=AT,
                                            initial_capital=10_000.0, seed=1, symbols=("BTC-USD",))
        for statement in _slow_index(table, column):
            await session.execute(text(statement))
    return db


async def test_two_writers_of_one_outcome_leave_one_row_and_no_error(pg_url: str) -> None:
    db = await _setup(pg_url, "edge_outcomes", "outcome_id")
    try:
        errors = await _two_writers(pg_url, lambda s: EdgeStateRepository(s).append(_outcome()))
        async with db.session() as session:
            rows = (await session.execute(text("SELECT COUNT(*) FROM edge_outcomes"))).scalar_one()
    finally:
        await db.close()
    assert errors == [] and rows == 1, (errors, rows)


async def test_two_writers_of_one_fill_leave_one_row_and_no_error(pg_url: str) -> None:
    db = await _setup(pg_url, "fills", "fill_id")
    try:
        fill = _fill("fill_once", Side.BUY, 0.01, 50_000.0, 0.1, AT, "ord_1")
        order = Order(order_id="ord_1", client_order_id="coid_1", intent_id="int", signal_id="sig", symbol="BTC-USD",
                      side=Side.BUY, order_type=OrderType.MARKET, quantity=0.01, state=OrderState.FILLED,
                      filled_quantity=0.01, average_fill_price=50_000.0, fees_paid=0.1, created_at=AT, updated_at=AT, fills=[fill])
        async with db.session() as session:
            await OrderRepository(session).upsert("live_r15", order)
        errors = await _two_writers(pg_url, lambda s: FillRepository(s).append("live_r15", fill))
        async with db.session() as session:
            rows = (await session.execute(text("SELECT COUNT(*) FROM fills"))).scalar_one()
    finally:
        await db.close()
    assert errors == [] and rows == 1, (errors, rows)
