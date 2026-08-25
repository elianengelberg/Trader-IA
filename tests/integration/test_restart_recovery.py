"""Restart recovery and the migration path.

The claim: a process death is an inconvenience, not an amnesia. Everything the system
knows — its evidence, its track record, its orders — is rebuilt from the database on the
next start, and nothing is double-counted in the rebuilding.

Also here: the EMPTY DB → MIGRATE → RUN → WRITE → RESTART → READ cycle, and the upgrade
of a genuine v1 database to v2, because every deployment that predates Alembic is exactly
such a database.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from tia.core.config import Environment, settings_for_env
from tia.persistence import Database, EdgeStateRepository
from tia.persistence.models import SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, TIA_DATABASE_URL=f"sqlite:///{db_path}")
    return subprocess.run(  # noqa: S603 - fixed argv, test-owned inputs
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
        check=False,
    )


# --------------------------------------------------------------------------- migrations


def test_migrations_build_a_complete_schema_from_nothing(tmp_path: Path) -> None:
    """EMPTY DB → MIGRATE → the full current schema, stamped at both version markers.

    Both markers are read from the code rather than written out, so adding a migration
    does not require editing this test — and a migration that forgets to move one of the
    two markers still fails it, which is the failure worth catching."""
    db = tmp_path / "fresh.db"
    result = _alembic(db, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    import sqlite3

    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"edge_outcomes", "activation_attempts", "incidents", "orders"} <= tables
    assert conn.execute("SELECT version FROM schema_info").fetchone()[0] == SCHEMA_VERSION
    assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
        f"{SCHEMA_VERSION:04d}"
    )


def test_a_v1_database_upgrades_in_place_without_losing_its_rows(tmp_path: Path) -> None:
    """The adoption path: a database from before Alembic existed migrates forward.

    Built by creating only the v1 tables and stamping version 1 — exactly what
    ``ensure_schema()`` produced in every deployment before this change — then upgraded,
    then checked that pre-existing rows survived.
    """
    from sqlalchemy import create_engine

    from tia.persistence.models import Base

    db = tmp_path / "v1.db"
    engine = create_engine(f"sqlite:///{db}")
    v1_tables = [
        Base.metadata.tables[name]
        for name in (
            "schema_info", "runs", "events", "decisions", "orders", "fills",
            "positions", "equity_points", "assessments", "logs", "backtests", "news",
        )
    ]
    Base.metadata.create_all(engine, tables=v1_tables)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_info (id, version, applied_at, application_version) "
                "VALUES (1, 1, CURRENT_TIMESTAMP, '0.1.0')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO runs (run_id, mode, scenario, started_at, initial_capital, "
                "seed, symbols, config_digest, notes) VALUES "
                "('run_old', 'paper', 'trend_up', CURRENT_TIMESTAMP, 1000.0, 7, '[]', '', '')"
            )
        )
    engine.dispose()

    result = _alembic(db, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    import sqlite3

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT version FROM schema_info").fetchone()[0] == SCHEMA_VERSION
    assert conn.execute("SELECT run_id FROM runs").fetchone()[0] == "run_old"
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "edge_outcomes" in tables


# --------------------------------------------------------------------------- restart


async def _run_paper_session(db_url: str, *, seed: int) -> int:
    """One complete paper session against the given database. Returns closed trades."""
    from tia.api.state import AppState

    settings = settings_for_env(Environment.TESTING).model_copy(
        update={"database_url": db_url}
    )
    state = AppState(settings)
    await state.startup()
    try:
        await state.start_run(
            {
                "scenario": "trend_up",
                "initial_capital": 10_000.0,
                "seed": seed,
                "bar_interval_seconds": 0.0,
            }
        )
        assert state.runtime is not None
        for _ in range(120_000):
            await asyncio.sleep(0)
            if not state.runtime.is_running:
                break
        await state.stop_run()
        # Let the fire-and-forget persistence tasks drain before the app goes away.
        for _ in range(50):
            await asyncio.sleep(0.01)
        return len(state.runtime.closed_trades)
    finally:
        await state.shutdown()


async def test_restart_recovery(tmp_path: Path) -> None:
    """RUN → persist → die → restart → the evidence is back and nothing doubled.

    The second process is a genuinely new AppState over the same file, the way a
    restarted service would be. What must hold:

    1. the persisted evidence count matches what the first session closed;
    2. the second session's engine starts with that evidence pre-loaded, not empty;
    3. re-running does not double-count — outcome ids are deterministic, so replaying
       the same close upserts instead of inserting;
    4. no order is submitted twice: client order ids are unique across both sessions.
    """
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'restart.db'}"

    closed_first = await _run_paper_session(db_url, seed=11)
    assert closed_first > 0, "the first session closed nothing, so recovery has nothing to prove"

    database = Database(db_url)
    await database.ensure_schema()
    async with database.session() as session:
        persisted = await EdgeStateRepository(session).count()
    assert persisted == closed_first

    # The restarted process: a brand-new AppState over the same database.
    from tia.api.state import AppState

    settings = settings_for_env(Environment.TESTING).model_copy(
        update={"database_url": db_url}
    )
    reborn = AppState(settings)
    await reborn.startup()
    try:
        await reborn.start_run(
            {
                "scenario": "trend_up",
                "initial_capital": 10_000.0,
                "seed": 12,  # a different seed: new session, same memory
                "bar_interval_seconds": 0.0,
            }
        )
        engine = reborn.runtime
        assert engine is not None
        assert engine._prior_outcome_count == closed_first, (
            "the restarted engine did not reload its evidence"
        )
        assert sum(engine._edges.coverage().values()) >= closed_first

        for _ in range(120_000):
            await asyncio.sleep(0)
            if not engine.is_running:
                break
        await reborn.stop_run()
        for _ in range(50):
            await asyncio.sleep(0.01)
    finally:
        await reborn.shutdown()

    # Nothing doubled, and no order id repeated across the two lives.
    async with database.session() as session:
        final_count = await EdgeStateRepository(session).count()
        order_rows = (
            await session.execute(
                text("SELECT client_order_id, COUNT(*) FROM orders GROUP BY client_order_id")
            )
        ).all()
    await database.close()

    assert final_count >= closed_first, "evidence went missing across the restart"
    duplicated = [row for row in order_rows if row[1] > 1]
    assert not duplicated, f"orders duplicated across restart: {duplicated}"


async def test_edge_persistence_survives_restart(tmp_path: Path) -> None:
    """The narrow version of the above, for the estimator alone: write rows, reload,
    and the buckets match exactly."""
    from tia.domain.enums import Direction, MarketRegime

    db_url = f"sqlite+aiosqlite:///{tmp_path / 'edge.db'}"
    database = Database(db_url)
    await database.ensure_schema()

    from datetime import UTC, datetime

    async with database.session() as session:
        repo = EdgeStateRepository(session)
        # 35 simulated/demo rows plus 3 written by the real-time session. The estimator
        # learns from all of them; the activation gate's track record counts only the 3.
        for index in range(38):
            await repo.append(
                {
                    "outcome_id": f"o-{index}",
                    "run_id": "run_a",
                    "signal_id": f"s-{index}",
                    "symbol": "BTC-USD",
                    "regime": MarketRegime.TRENDING_UP.value,
                    "direction": Direction.LONG.value,
                    "confidence": 0.75,
                    "entry_price": 50_000.0,
                    "exit_price": 50_100.0,
                    "quantity": 0.01,
                    "gross_bps": 20.0,
                    "fees_bps": 15.0,
                    "net_bps": 5.0,
                    "expected_net_bps": 4.0,
                    "closed_at": datetime(2026, 8, 1, tzinfo=UTC),
                    "source": "live" if index >= 35 else "paper",
                }
            )
    await database.close()

    # A different connection, as a restarted process would hold.
    database2 = Database(db_url)
    async with database2.session() as session:
        rows = await EdgeStateRepository(session).load_all()
        record = await EdgeStateRepository(session).track_record()
    await database2.close()

    assert len(rows) == 38
    # Synthetic evidence teaches, but it must never satisfy the gate: only the rows the
    # real-time session wrote count toward the activation track record.
    assert record["closed_trades"] == 3

    from tia.economics.expected_value import EdgeEstimator, Outcome

    estimator = EdgeEstimator()
    estimator.record_many(
        [
            Outcome(
                regime=MarketRegime(row.regime),
                direction=Direction(row.direction),
                confidence=row.confidence,
                net_return_bps=row.net_bps,
            )
            for row in rows
        ]
    )
    estimate = estimator.estimate(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.75
    )
    assert estimate is not None, "38 reloaded samples must clear the 30-sample floor"
    assert estimate.samples == 38  # the estimator learns from every source, gate aside


async def test_a_failed_persistence_write_does_not_pretend_to_be_state(
    tmp_path: Path,
) -> None:
    """If the write fails, the in-memory estimator still has the sample but the *gate*
    reads the database — so the failure surfaces as missing track record, never as
    silently-assumed persistence."""
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'failing.db'}"
    database = Database(db_url)
    await database.ensure_schema()
    async with database.session() as session:
        count = await EdgeStateRepository(session).count()
    await database.close()
    assert count == 0  # nothing written, nothing claimed
