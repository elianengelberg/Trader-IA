"""Schema and migrations on PostgreSQL.

Production boots with ``python -m alembic upgrade head && python -m tia.api.main``
(``docker-compose.prod.yml``); the CI applies the migrations to SQLite only. What is
pinned here, on a real server:

* the migrations build the complete schema from an empty database, at both version
  markers, and what they build is what the models declare (no drift);
* ``Database.ensure_schema`` (the path every other test takes) and Alembic (the path
  production takes) build the same tables, columns, keys and indexes;
* the boot order (Alembic, then ``ensure_schema``), the adoption of a database that
  ``ensure_schema`` created before Alembic existed, the refusal of a mismatched version,
  the v1 in-place upgrade, the v7 backfill and a full downgrade/upgrade round trip.

The two upgrade tests are the SQLite ones of ``tests/integration/test_restart_recovery.py``
with the SQL written for PostgreSQL.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from tests.postgres.support import PgDatabases, alembic
from tia.core.errors import ConfigurationError
from tia.persistence import Database, EdgeStateRepository, RunRepository
from tia.persistence.models import SCHEMA_VERSION, Base

MODEL_TABLES = set(Base.metadata.tables)


def _upgrade(pg: PgDatabases, label: str = "main", target: str = "head") -> None:
    result = alembic(pg.url(label), "upgrade", target)
    assert result.returncode == 0, result.stderr


def _markers(engine: Engine) -> tuple[int, str]:
    with engine.connect() as conn:
        return (
            conn.execute(text("SELECT version FROM schema_info")).scalar_one(),
            conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one(),
        )


def _structure(engine: Engine) -> dict[str, Any]:
    """Tables, columns (type, nullability), primary keys, foreign keys, unique
    constraints and indexes, as PostgreSQL reports them."""
    shape: dict[str, Any] = {}
    with engine.connect() as conn:
        inspector = inspect(conn)
        for table in sorted(inspector.get_table_names()):
            if table == "alembic_version":
                continue
            shape[table] = {
                "columns": {
                    c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)
                },
                "pk": tuple(inspector.get_pk_constraint(table)["constrained_columns"]),
                "fks": sorted(
                    (
                        tuple(fk["constrained_columns"]),
                        fk["referred_table"],
                        tuple(fk["referred_columns"]),
                        (fk.get("options") or {}).get("ondelete"),
                    )
                    for fk in inspector.get_foreign_keys(table)
                ),
                "uniques": sorted(
                    (u["name"], tuple(u["column_names"])) for u in inspector.get_unique_constraints(table)
                ),
                "indexes": sorted(
                    (i["name"], tuple(i["column_names"]), bool(i["unique"]))
                    for i in inspector.get_indexes(table)
                ),
            }
    return shape


def test_alembic_upgrade_head_builds_the_full_schema_from_an_empty_database(pg: PgDatabases) -> None:
    """EMPTY → ``alembic upgrade head`` with the production URL form (``+asyncpg``)."""
    _upgrade(pg)
    engine = pg.engine()
    try:
        with engine.connect() as conn:
            tables = set(inspect(conn).get_table_names())
        assert tables == MODEL_TABLES | {"alembic_version"}
        assert _markers(engine) == (SCHEMA_VERSION, f"{SCHEMA_VERSION:04d}")
    finally:
        engine.dispose()


def test_the_migrated_schema_has_no_drift_from_the_models(pg: PgDatabases) -> None:
    """Alembic's own comparison of the migrated database against ``Base.metadata``:
    a column, type, nullability, index or key a migration got wrong is listed here."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    _upgrade(pg)
    engine = pg.engine()
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            diffs = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
    assert diffs == [], "migrations and models disagree on PostgreSQL:\n" + "\n".join(map(str, diffs))


#: The constraints and indexes the idempotent writes and the hot reads stand on.
HOT_PATH_INDEXES = {
    ("events", "uq_events_idempotency", ("idempotency_key",), True),
    ("events", "ix_events_run_seq", ("run_id", "sequence"), False),
    ("orders", "uq_orders_client_id", ("client_order_id",), True),
    ("orders", "ix_orders_run_created", ("run_id", "created_at"), False),
    ("fills", "ix_fills_run_time", ("run_id", "filled_at"), False),
    ("positions", "uq_positions_run_symbol", ("run_id", "symbol"), True),
    ("edge_outcomes", "ix_edge_outcomes_ingested_at", ("ingested_at",), False),
    ("edge_outcomes", "ix_edge_outcomes_source", ("source",), False),
    ("mm_journal", "ix_mm_journal_run_t", ("run_id", "t_ms"), False),
}


def test_the_constraints_and_indexes_the_hot_paths_rely_on_exist(pg: PgDatabases) -> None:
    _upgrade(pg)
    engine = pg.engine()
    try:
        with engine.connect() as conn:
            found = {
                (row.tablename, row.indexname)
                for row in conn.execute(text("SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public'"))
            }
        shape = _structure(engine)
    finally:
        engine.dispose()
    for table, name, columns, unique in HOT_PATH_INDEXES:
        assert (table, name) in found, f"{table}.{name} is missing"
        declared = {i[0]: i[1:] for i in shape[table]["indexes"]} | {
            u[0]: (u[1], True) for u in shape[table]["uniques"]
        }
        assert declared[name] == (columns, unique), (table, name, declared[name])
    fks = {(t, fk[0], fk[1], fk[3]) for t, s in shape.items() for fk in s["fks"]}
    assert ("fills", ("order_id",), "orders", "CASCADE") in fks
    assert ("fills", ("run_id",), "runs", "CASCADE") in fks
    assert ("orders", ("run_id",), "runs", "CASCADE") in fks
    assert ("events", ("run_id",), "runs", "CASCADE") in fks


async def test_ensure_schema_and_alembic_build_the_same_schema(pg: PgDatabases) -> None:
    """Every other suite builds its store with ``ensure_schema`` (``create_all``);
    production builds it with Alembic. On PostgreSQL both must be the same schema, or
    the tests exercise a database production never has."""
    _upgrade(pg, "migrated")
    database = Database(pg.url("created"))
    await database.ensure_schema()
    await database.close()
    migrated, created = pg.engine("migrated"), pg.engine("created")
    try:
        left, right = _structure(migrated), _structure(created)
    finally:
        migrated.dispose()
        created.dispose()
    assert set(left) == set(right) == MODEL_TABLES
    differing = {table: {"alembic": left[table], "ensure_schema": right[table]}
                 for table in left if left[table] != right[table]}
    assert not differing, differing


async def test_the_production_boot_order_alembic_then_ensure_schema(pg: PgDatabases) -> None:
    """The container runs Alembic, then the application calls ``ensure_schema``: it
    accepts the migrated database, inserts no second version row, and is idempotent."""
    _upgrade(pg)
    database = Database(pg.url())
    try:
        assert database.dialect == "postgresql"
        assert await database.ensure_schema() == SCHEMA_VERSION
        assert await database.ensure_schema() == SCHEMA_VERSION
        assert await database.ping() is True
        async with database.session() as session:
            rows = (await session.execute(text("SELECT id, version FROM schema_info"))).all()
        assert [tuple(r) for r in rows] == [(1, SCHEMA_VERSION)]
    finally:
        await database.close()


async def test_a_database_created_by_ensure_schema_adopts_alembic_and_keeps_its_rows(
    pg: PgDatabases,
) -> None:
    """Every deployment before Alembic: tables from ``create_all``, no ``alembic_version``.
    The upgrade adopts it in place (the migrations are guarded by inspection)."""
    from datetime import UTC, datetime

    database = Database(pg.url())
    await database.ensure_schema()
    async with database.session() as session:
        await RunRepository(session).create(
            run_id="run_before_alembic", mode="paper-live", scenario="realtime",
            started_at=datetime(2026, 10, 1, tzinfo=UTC), initial_capital=10_000.0, seed=1,
            symbols=("BTC-USD",),
        )
        await EdgeStateRepository(session).append({
            "outcome_id": "o-before", "run_id": "run_before_alembic", "signal_id": "s",
            "symbol": "BTC-USD", "regime": "trending_up", "direction": "long", "confidence": 0.7,
            "entry_price": 50_000.0, "exit_price": 50_100.0, "quantity": 0.01, "gross_bps": 20.0,
            "fees_bps": 10.0, "net_bps": 10.0, "closed_at": datetime(2026, 10, 1, 1, tzinfo=UTC),
            "source": "live",
        })
    await database.close()

    _upgrade(pg)
    engine = pg.engine()
    try:
        assert _markers(engine) == (SCHEMA_VERSION, f"{SCHEMA_VERSION:04d}")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT run_id FROM runs")).scalars().all() == ["run_before_alembic"]
            assert conn.execute(text("SELECT outcome_id FROM edge_outcomes")).scalars().all() == ["o-before"]
    finally:
        engine.dispose()
    again = alembic(pg.url(), "upgrade", "head")
    assert again.returncode == 0, again.stderr


async def test_ensure_schema_refuses_a_database_of_another_schema_version(pg_db: Database) -> None:
    async with pg_db.session() as session:
        await session.execute(text("UPDATE schema_info SET version = :v"), {"v": SCHEMA_VERSION + 1})
    with pytest.raises(ConfigurationError, match="schema version does not match"):
        await pg_db.ensure_schema()


def test_a_v1_database_upgrades_in_place_without_losing_its_rows(pg: PgDatabases) -> None:
    """The v1 adoption path of the SQLite suite, on PostgreSQL."""
    engine = pg.engine()
    v1 = ("schema_info", "runs", "events", "decisions", "orders", "fills",
          "positions", "equity_points", "assessments", "logs", "backtests", "news")
    try:
        Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in v1])
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO schema_info (id, version, applied_at, application_version) "
                "VALUES (1, 1, CURRENT_TIMESTAMP, '0.1.0')"
            ))
            conn.execute(text(
                "INSERT INTO runs (run_id, mode, scenario, started_at, initial_capital, seed, "
                "symbols, config_digest, notes) VALUES "
                "('run_old', 'paper', 'trend_up', CURRENT_TIMESTAMP, 1000.0, 7, '[]', '', '')"
            ))
        _upgrade(pg)
        assert _markers(engine)[0] == SCHEMA_VERSION
        with engine.connect() as conn:
            assert conn.execute(text("SELECT run_id FROM runs")).scalar_one() == "run_old"
            assert "edge_outcomes" in inspect(conn).get_table_names()
    finally:
        engine.dispose()


def test_v7_backfills_provenance_from_what_the_rows_already_say(pg: PgDatabases) -> None:
    """The v6 → v7 backfill of the SQLite suite, on PostgreSQL, then the downgrade."""
    _upgrade(pg, target="0006")
    engine = pg.engine()
    rows = [
        ("o_sim", "run_sim", "sim"),
        ("o_paper", "run_demo", "paper"),
        ("o_pl", "run_pl", "live"),
        ("o_lv", "run_lv", "live"),
        ("o_orphan", "run_gone", "live"),
    ]
    try:
        with engine.begin() as conn:
            for column in ("market_data", "execution_mode", "strategy_version"):
                conn.execute(text(f"ALTER TABLE edge_outcomes DROP COLUMN {column}"))
            conn.execute(text(
                "INSERT INTO runs (run_id, mode, scenario, started_at, initial_capital, seed, "
                "symbols, config_digest, notes) VALUES "
                "('run_pl', 'paper-live', 'live', CURRENT_TIMESTAMP, 10000.0, 0, '[]', '', ''), "
                "('run_lv', 'live', 'live', CURRENT_TIMESTAMP, 100.0, 0, '[]', '', ''), "
                "('run_demo', 'paper', 'trend_up', CURRENT_TIMESTAMP, 10000.0, 7, '[]', '', '')"
            ))
            for outcome_id, run_id, source in rows:
                conn.execute(
                    text(
                        "INSERT INTO edge_outcomes (outcome_id, run_id, signal_id, symbol, regime, "
                        "direction, confidence, entry_price, exit_price, quantity, gross_bps, "
                        "fees_bps, net_bps, exploratory, expected_net_bps, closed_at, source, "
                        "exit_reason, strategy_id) VALUES (:o, :r, 'sig', 'BTC-USD', 'trending_up', "
                        "'long', 0.6, 100.0, 101.0, 1.0, 100.0, 10.0, 90.0, false, 5.0, "
                        "CURRENT_TIMESTAMP, :s, 'target reached', 'trend_following')"
                    ),
                    {"o": outcome_id, "r": run_id, "s": source},
                )
        _upgrade(pg)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version FROM schema_info")).scalar_one() == SCHEMA_VERSION == 8  # head is v8 since 0008 (R24-H1)
            got = {
                r[0]: tuple(r[1:])
                for r in conn.execute(text(
                    "SELECT outcome_id, market_data, execution_mode, strategy_version, source, "
                    "strategy_id, net_bps FROM edge_outcomes"
                ))
            }
        assert len(got) == len(rows)
        assert got["o_sim"][:2] == ("synthetic", "simulated")
        assert got["o_paper"][:2] == ("synthetic", "simulated")
        assert got["o_pl"][:2] == ("real", "simulated")
        assert got["o_lv"][:2] == ("real", "real")
        assert got["o_orphan"][:2] == ("real", None)
        for values in got.values():
            assert values[2] is None
            assert values[4:] == ("trend_following", 90.0)

        result = alembic(pg.url(), "downgrade", "0006")
        assert result.returncode == 0, result.stderr
        with engine.connect() as conn:
            columns = {c["name"] for c in inspect(conn).get_columns("edge_outcomes")}
            assert not {"market_data", "execution_mode", "strategy_version"} & columns
            assert conn.execute(text("SELECT COUNT(*) FROM edge_outcomes")).scalar_one() == len(rows)
            assert conn.execute(text("SELECT version FROM schema_info")).scalar_one() == 6
    finally:
        engine.dispose()


def test_downgrade_to_base_and_upgrade_again(pg: PgDatabases) -> None:
    """Transactional DDL on PostgreSQL: the whole chain down and back up again."""
    _upgrade(pg)
    down = alembic(pg.url(), "downgrade", "base")
    assert down.returncode == 0, down.stderr
    engine = pg.engine()
    try:
        with engine.connect() as conn:
            assert set(inspect(conn).get_table_names()) == {"alembic_version"}
        _upgrade(pg)
        assert _markers(engine) == (SCHEMA_VERSION, f"{SCHEMA_VERSION:04d}")
    finally:
        engine.dispose()
