"""R24-H1 on PostgreSQL: no valid incident is lost to the width of ``incidents.kind``.

Before: ``VARCHAR(32)``; ``entries_blocked:protection_unverified`` (37), ``…position_unverified``
(35), ``…orders_unverified`` (33) and ``…protection_failed`` (33) were refused with SQLSTATE 22001
(``StringDataRightTruncation``), the dispatcher absorbed the error, and the incident existed only
in memory and in the alert. After: ``VARCHAR(INCIDENT_KIND_MAX_LENGTH)`` (migration ``0008``), the
repository checks the same limit on every dialect, and a refused incident is named, not claimed.

The kinds tested are the ones the code writes, found by reading the code
(``tests/unit/test_incident_kind_contract.py``), not a list kept by hand.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

from tests.integration import test_account_restore as account
from tests.integration.test_protection_invariants import fail_stops
from tests.postgres.support import REPO_ROOT, PgDatabases, alembic
from tests.unit.test_incident_kind_contract import incident_kinds, invalid_kind, limit
from tia.core.config import Environment, settings_for_env
from tia.core.errors import OrderRejectedError, ReconciliationError
from tia.persistence import Database, IncidentRepository
from tia.persistence.models import SCHEMA_VERSION, IncidentRow

KINDS = sorted(incident_kinds()[0])
ENTRIES_BLOCKED = [k for k in KINDS if k.startswith("entries_blocked:")]
AT = datetime(2026, 10, 25, 21, 30, 15, 123456, tzinfo=UTC)  # 18:30 in Buenos Aires: the server's zone


def _state(url: str) -> Any:
    from tia.api.state import AppState

    return AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": url}))


def _incident(incident_id: str, kind: object, **extra: Any) -> dict[str, Any]:
    return {"incident_id": incident_id, "at": AT, "kind": kind, "actor": "system", "reason": "pg test",
            "run_id": "live_pg", "detail": {"client_order_id": "coid_X", "n": 1.5, "nested": {"a": [1, 2]}}, **extra}


async def _write_and_read(db: Database, values: dict[str, Any]) -> IncidentRow:
    async with db.session() as session:
        await IncidentRepository(session).record(values)
    async with db.session() as session:
        return (await session.execute(select(IncidentRow).where(IncidentRow.incident_id == values["incident_id"]))).scalar_one()


def _same(row: IncidentRow, values: dict[str, Any]) -> None:
    assert (row.kind, row.actor, row.reason, row.run_id, row.detail) == (
        values["kind"], values["actor"], values["reason"], values["run_id"], values["detail"])
    assert row.at == values["at"], "the instant survives the server's own time zone"


async def test_the_schema_holds_the_contract_width(pg_db: Database) -> None:
    async with pg_db.engine.connect() as conn:
        width = (await conn.execute(text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name = 'incidents' AND column_name = 'kind'"))).scalar_one()
    assert width == limit() >= max(len(k) for k in KINDS)


async def test_a_short_incident_is_stored_and_read_back_unchanged(pg_db: Database) -> None:
    values = _incident("inc_short", "safe_mode")
    _same(await _write_and_read(pg_db, values), values)


async def test_the_longest_kind_the_code_writes_is_stored_unchanged(pg_db: Database) -> None:
    longest = max(KINDS, key=len)
    assert len(longest) > 32, "the case that was lost"
    values = _incident("inc_longest", longest)
    _same(await _write_and_read(pg_db, values), values)


async def test_a_kind_at_the_exact_limit_is_stored_unchanged(pg_db: Database) -> None:
    values = _incident("inc_limit", "x" * limit())
    _same(await _write_and_read(pg_db, values), values)


@pytest.mark.parametrize("kind", ENTRIES_BLOCKED)
async def test_every_entries_blocked_kind_is_stored_unchanged(pg_db: Database, kind: str) -> None:
    values = _incident(f"inc_{kind.split(':')[1]}", kind)
    _same(await _write_and_read(pg_db, values), values)


async def test_every_kind_the_code_writes_is_stored_unchanged(pg_db: Database) -> None:
    refused: dict[str, str] = {}
    for i, kind in enumerate(KINDS):
        values = _incident(f"inc_all_{i:03d}", kind)
        try:
            _same(await _write_and_read(pg_db, values), values)
        except Exception as exc:
            refused[kind] = f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
    assert refused == {}, refused


@pytest.mark.parametrize("scenario", ["stop_refused", "stop_unknown"])
async def test_the_two_p0_incidents_reach_postgresql_through_the_runtime(
    pg: PgDatabases, monkeypatch: pytest.MonkeyPatch, scenario: str,
) -> None:
    """The real path: the live runtime fails to protect a position, blocks entries, and the
    dispatcher writes the incidents. Both P0 kinds were lost here before 0008."""
    state = _state(pg.url())
    await state.database.ensure_schema()
    try:
        runtime, execution, market, _ = account.build(persist=state._persist)
        runtime._poll_interval = 3600.0
        await account.register_run(state.database, runtime.run_id)
        await runtime.start()
        try:
            if scenario == "stop_refused":
                fail_stops(monkeypatch, execution, OrderRejectedError("code=-1013 Stop loss orders are not supported for this symbol.", code=-1013))
                await account.open_position(runtime, market)
                expected = {"entries_blocked:protection_failed", "protection_failed", "halt_new_orders"}
            else:
                await account.open_position(runtime, market)
                fail_stops(monkeypatch, execution, ReconciliationError("POST /api/v3/order timed out; UNKNOWN"), times=1)

                async def still_unknown(*, symbol: str, client_order_id: str) -> None:
                    raise ReconciliationError("the venue does not answer")

                monkeypatch.setattr(execution, "resolve_unknown_order", still_unknown, raising=False)
                expected = {"entries_blocked:protection_unverified", "protection_unknown", "halt_new_orders"}
            market.advance()
            await runtime._cycle_once()
            await account.settle(runtime)
            assert await runtime.flush_persistence(timeout_seconds=10)
        finally:
            await runtime.stop()
        record = await state._record_stop(runtime, stamp=True, release_lease=True)
        async with state.database.session() as session:
            kinds = {r.kind for r in (await session.execute(select(IncidentRow).where(IncidentRow.run_id == runtime.run_id))).scalars()}
        assert expected <= kinds, kinds
        assert runtime.persist_failed_writes == 0
        assert state.persistence_status()["failures"] == 0 and state.persistence_status()["incident_failures"] == 0
        assert record["status"] == "complete" and record["failed_writes"] == 0
    finally:
        await state.database.close()


async def test_incidents_survive_a_new_process_and_reach_the_reports(pg: PgDatabases) -> None:
    """A restart: a new process, a new engine, the same database. The incident list and the
    daily report see what the previous process wrote, long kinds included."""
    url = pg.url()
    first = Database(url)
    await first.ensure_schema()
    written = [_incident(f"inc_restart_{i}", kind) for i, kind in enumerate([*ENTRIES_BLOCKED, "safe_mode"])]
    for values in written:
        await _write_and_read(first, values)
    await first.close()

    state = _state(url)
    await state.database.ensure_schema()
    try:
        await state._load_unconfirmed_runs()
        async with state.database.session() as session:
            recent = {r.incident_id: r for r in await IncidentRepository(session).recent(limit=100)}
        for values in written:
            _same(recent[values["incident_id"]], values)
        spec = importlib.util.spec_from_file_location("daily_report", REPO_ROOT / "scripts" / "daily_report.py")
        daily = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(daily)  # type: ignore[union-attr]
        report = await daily.build_report(state.database, AT - timedelta(hours=1), AT + timedelta(hours=1))
        assert {k: report["incidents"].get(k) for k in ENTRIES_BLOCKED} == dict.fromkeys(ENTRIES_BLOCKED, 1)
    finally:
        await state.database.close()


async def test_a_refused_incident_write_rolls_back_and_is_named_not_claimed(pg: PgDatabases) -> None:
    state = _state(pg.url())
    await state.database.ensure_schema()
    try:
        assert await state._persist("incident", _incident("inc_dup", "protection_failed")) is True
        assert await state._persist("incident", _incident("inc_dup", "entries_blocked:protection_failed", reason="second")) is False
        async with state.database.session() as session:
            rows = [(r.incident_id, r.kind, r.reason) for r in (await session.execute(select(IncidentRow))).scalars()]
        assert rows == [("inc_dup", "protection_failed", "pg test")], "nothing half-written"
        status = state.persistence_status()
        assert status["incident_failures"] == 1 and status["last_failed_incident"]["kind"] == "entries_blocked:protection_failed"
        assert "UniqueViolation" in status["last_failed_incident"]["error"] or "IntegrityError" in status["last_failed_incident"]["error"]
    finally:
        await state.database.close()


@pytest.mark.parametrize("kind", ["too_long", "", "Not Valid"], ids=["too_long", "empty", "bad_chars"])
async def test_an_invalid_kind_is_stored_explicitly_with_the_original_kept(pg_db: Database, kind: str) -> None:
    if kind == "too_long":
        kind = "x" * (limit() + 1)
    async with pg_db.session() as session:
        await IncidentRepository(session).record(_incident("inc_invalid", kind))
    async with pg_db.session() as session:
        row = (await session.execute(select(IncidentRow))).scalar_one()
    assert row.kind == invalid_kind() and row.detail["invalid_kind"] == repr(kind)
    assert row.detail["client_order_id"] == "coid_X", "the producer's detail is kept"


# ------------------------------------------------------------------ migration 0008


OLD_ROWS = [
    ("inc_old_1", "safe_mode", '{"a": 1}'),
    ("inc_old_2", "halt_new_orders", '{"divergences": [1, 2]}'),
    ("inc_old_3", "x" * 32, "{}"),  # the old maximum
]


def _old_shape_with_rows(pg: PgDatabases) -> Any:
    """A database as the previous release left it: migrated to 0007 with ``incidents.kind``
    VARCHAR(32), and incidents already in it. 0002 builds tables from the current models, so
    the old width is put back by hand: the only column 0008 changes."""
    result = alembic(pg.url(), "upgrade", "0007")
    assert result.returncode == 0, result.stderr
    engine = pg.engine()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE incidents ALTER COLUMN kind TYPE VARCHAR(32)"))
        for iid, kind, detail in OLD_ROWS:
            conn.execute(text("INSERT INTO incidents (incident_id, at, kind, actor, reason, run_id, detail) "
                              "VALUES (:i, :at, :k, 'system', 'old', 'live_old', CAST(:d AS JSON))"), {"i": iid, "at": AT, "k": kind, "d": detail})
    return engine


def _state_of(engine: Any) -> tuple[Any, ...]:
    with engine.connect() as conn:
        width = conn.execute(text("SELECT character_maximum_length FROM information_schema.columns "
                                  "WHERE table_name = 'incidents' AND column_name = 'kind'")).scalar_one()
        rows = [tuple(r) for r in conn.execute(text("SELECT incident_id, at, kind, actor, reason, run_id, CAST(detail AS TEXT) FROM incidents ORDER BY incident_id"))]
        markers = (conn.execute(text("SELECT version FROM schema_info")).scalar_one(),
                   conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())
        indexed = conn.execute(text("SELECT count(*) FROM pg_indexes WHERE tablename = 'incidents' AND indexdef LIKE '%(kind)%'")).scalar_one()
    return width, rows, markers, indexed


def test_0008_widens_the_column_and_keeps_every_old_row(pg: PgDatabases) -> None:
    engine = _old_shape_with_rows(pg)
    try:
        width, before, markers, indexed = _state_of(engine)
        assert (width, markers, indexed) == (32, (7, "0007"), 1)
        result = alembic(pg.url(), "upgrade", "head")
        assert result.returncode == 0, result.stderr
        width, after, markers, indexed = _state_of(engine)
        assert width == limit() and markers == (SCHEMA_VERSION, f"{SCHEMA_VERSION:04d}") == (8, "0008")
        assert after == before, "no old row changed"
        assert indexed == 1, "the index on kind is still there"
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO incidents (incident_id, at, kind, actor, reason, run_id, detail) "
                              "VALUES ('inc_new', now(), 'entries_blocked:protection_unverified', 'system', '', '', '{}')"))
    finally:
        engine.dispose()


def test_0008_refuses_to_narrow_back_over_rows_that_would_not_fit(pg: PgDatabases) -> None:
    engine = _old_shape_with_rows(pg)
    try:
        assert alembic(pg.url(), "upgrade", "head").returncode == 0
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO incidents (incident_id, at, kind, actor, reason, run_id, detail) "
                              "VALUES ('inc_long', now(), 'entries_blocked:protection_unverified', 'system', '', '', '{}')"))
        before = _state_of(engine)
        down = alembic(pg.url(), "downgrade", "0007")
        assert down.returncode != 0 and "longer than 32" in (down.stderr + down.stdout)
        assert _state_of(engine) == before, "a refused downgrade changes nothing"
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM incidents WHERE incident_id = 'inc_long'"))
        down = alembic(pg.url(), "downgrade", "0007")
        assert down.returncode == 0, down.stderr
        width, rows, markers, _ = _state_of(engine)
        assert (width, markers) == (32, (7, "0007")) and [r[0] for r in rows] == [r[0] for r in OLD_ROWS]
    finally:
        engine.dispose()
