"""The PostgreSQL integration suite (R24).

Production runs PostgreSQL (``docker-compose.prod.yml``); every other suite runs SQLite.
This one runs against a real server, and only when it is told where one is:

* ``TIA_TEST_DATABASE_URL`` unset or empty: every test here is **skipped** at collection,
  with the reason; no fixture runs and nothing is dialled.
* set: it names a PostgreSQL server and a role with ``CREATEDB``. The database in the URL
  is only the maintenance connection and is never written to. Each test gets databases
  of its own — ``CREATE DATABASE`` on first use, ``DROP DATABASE ... WITH (FORCE)`` at
  teardown — so no test reads another's rows and a failed test cannot poison the next.

Any driver suffix is accepted (``postgresql://``, ``+asyncpg``, ``+psycopg2``): the
application gets ``postgresql+asyncpg`` URLs, Alembic the same URL the production command
passes it (``infra/migrations/env.py`` strips ``+asyncpg`` and runs on psycopg2), and the
fixtures' own administration uses psycopg2. Helpers live in :mod:`tests.postgres.support`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

# The integration suite's guard against real venue sockets applies here too: these
# tests drive the same runtimes, and the guard is the contract, not the settings.
from tests.integration.conftest import _no_real_websockets  # noqa: F401
from tests.postgres.support import ENV_VAR, HERE, PgDatabases, PostgresServer, Redirect
from tia.persistence import Database

SKIP_REASON = (
    f"{ENV_VAR} is not set: the PostgreSQL suite needs a server "
    "(postgresql://user:password@host:port/maintenance_db, a role with CREATEDB)"
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(ENV_VAR, "").strip():
        return
    skip = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        if HERE in Path(str(item.path)).resolve().parents:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def pg_server() -> PostgresServer:
    server = PostgresServer(os.environ[ENV_VAR])
    try:
        facts = server.describe()
    except Exception as exc:  # the variable is set: an unusable server is a failure, not a skip
        pytest.fail(f"{ENV_VAR} is set but the server cannot be used: {type(exc).__name__}: {exc}")
    if not facts["createdb"]:
        pytest.fail(f"the role in {ENV_VAR} needs CREATEDB: each test creates its own databases")
    return server


@pytest.fixture
def pg(pg_server: PostgresServer) -> Iterator[PgDatabases]:
    databases = PgDatabases(pg_server)
    try:
        yield databases
    finally:
        databases.drop_all()


@pytest.fixture
def pg_url(pg: PgDatabases) -> str:
    return pg.url()


@pytest.fixture
async def pg_db(pg_url: str) -> AsyncIterator[Database]:
    """A ``Database`` over a fresh PostgreSQL database, schema created by ensure_schema."""
    database = Database(pg_url)
    await database.ensure_schema()
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def redirect(pg: PgDatabases, monkeypatch: pytest.MonkeyPatch) -> Redirect:
    return Redirect(pg, monkeypatch)


@pytest.fixture
def fake_public_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The venue's public feed replaced by the synthetic one the session tests use."""
    import tia.data.providers.binance_public as binance_public
    from tests.integration.test_live_api import _FakePublicFeed

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)
