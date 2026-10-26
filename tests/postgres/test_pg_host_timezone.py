"""The host's own time zone must not move a stamp (mission v2).

asyncpg encodes a naive ``datetime`` bound to a ``timestamptz`` parameter in the *client
process's* local zone (``datetime.astimezone``), not in UTC. The store's convention is the
opposite: every writer stamps UTC, and a naive stamp read back from SQLite *is* UTC
(``tia.risk.restore._as_utc``). So on a host whose ``TZ`` was not UTC, the same naive value
landed hours away on PostgreSQL from where SQLite keeps it, and a naive bound in a query
selected a different window: ``test_pg_types.py::test_a_naive_datetime_is_stored_as_utc``
failed with ``TZ=America/Argentina/Buenos_Aires`` (12:00 stored as 15:00 UTC) and passed
with ``TZ=UTC``. These tests set the process zone themselves, so they say the same thing on
any host. Aware stamps were never affected; they are pinned too.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from tests.postgres.support import PgDatabases
from tia.persistence import Database, RunRepository
from tia.persistence.models import RunRecord

ZONES = ["UTC", "America/Argentina/Buenos_Aires", "Asia/Kathmandu"]
NOON = datetime(2026, 10, 22, 12, 0)  # naive: by the store's convention, 12:00 UTC


@pytest.fixture
def host_zone() -> Iterator[Callable[[str], None]]:
    """Set the process's local zone (``TZ`` + ``tzset``) and put the original back."""
    before = os.environ.get("TZ")

    def set_zone(name: str) -> None:
        os.environ["TZ"] = name
        time.tzset()

    try:
        yield set_zone
    finally:
        if before is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = before
        time.tzset()


def _url(dialect: str, pg: PgDatabases, tmp_path: Path) -> str:
    return pg.url() if dialect == "postgresql" else f"sqlite+aiosqlite:///{tmp_path / 'host_zone.db'}"


def _as_utc(value: datetime) -> datetime:
    """What every reader in the code base does with a stamp from the store."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _run(database: Database, run_id: str, started_at: datetime) -> None:
    async with database.session() as session:
        await RunRepository(session).create(
            run_id=run_id, mode="paper-live", scenario="realtime", started_at=started_at,
            initial_capital=10_000.0, seed=1, symbols=("BTC-USD",),
        )


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
async def test_a_naive_stamp_is_utc_whatever_the_host_zone(
    dialect: str, zone: str, pg: PgDatabases, tmp_path: Path, host_zone: Callable[[str], None],
) -> None:
    host_zone(zone)
    database = Database(_url(dialect, pg, tmp_path))
    await database.ensure_schema()
    try:
        await _run(database, "run_naive", NOON)
        async with database.session() as session:
            row = await session.get(RunRecord, "run_naive")
    finally:
        await database.close()
    assert row is not None
    assert _as_utc(row.started_at) == NOON.replace(tzinfo=UTC), (dialect, zone, row.started_at)


@pytest.mark.parametrize("zone", ZONES)
async def test_an_aware_stamp_is_the_same_instant_whatever_the_host_zone(
    zone: str, pg: PgDatabases, tmp_path: Path, host_zone: Callable[[str], None],
) -> None:
    host_zone(zone)
    instant = datetime(2026, 10, 22, 9, 0, 0, 1, tzinfo=timezone(timedelta(hours=-3)))
    database = Database(pg.url())
    await database.ensure_schema()
    try:
        await _run(database, "run_aware", instant)
        async with database.session() as session:
            row = await session.get(RunRecord, "run_aware")
    finally:
        await database.close()
    assert row is not None and row.started_at == instant and row.started_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("zone", ZONES)
@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
async def test_a_naive_bound_selects_the_same_window_whatever_the_host_zone(
    dialect: str, zone: str, pg: PgDatabases, tmp_path: Path, host_zone: Callable[[str], None],
) -> None:
    """The bound side of a query: rows stamped 11:59 and 12:00 UTC, asked for ``>= 12:00``
    with a naive bound. One row, on both dialects, in every zone."""
    host_zone(zone)
    database = Database(_url(dialect, pg, tmp_path))
    await database.ensure_schema()
    try:
        await _run(database, "run_before", datetime(2026, 10, 22, 11, 59, tzinfo=UTC))
        await _run(database, "run_at", datetime(2026, 10, 22, 12, 0, tzinfo=UTC))
        async with database.session() as session:
            count = (await session.execute(
                select(func.count()).select_from(RunRecord).where(RunRecord.started_at >= NOON)
            )).scalar_one()
    finally:
        await database.close()
    assert count == 1, (dialect, zone, count)
