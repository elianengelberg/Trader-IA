"""Helpers of the PostgreSQL suite: the server, per-test databases, Alembic, reuse.

Kept out of ``conftest.py`` so the test modules can import them by name.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from tia.persistence import Database

ENV_VAR = "TIA_TEST_DATABASE_URL"
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]


class PostgresServer:
    """The server ``TIA_TEST_DATABASE_URL`` names, and URLs to databases on it."""

    def __init__(self, raw: str) -> None:
        url = make_url(raw)
        if not url.drivername.startswith("postgresql"):
            raise pytest.UsageError(f"{ENV_VAR} must be a PostgreSQL URL, got {url.drivername!r}")
        self._url: URL = url
        self.maintenance_db = url.database or "postgres"

    def url(self, database: str, *, driver: str = "asyncpg") -> str:
        return self._url.set(drivername=f"postgresql+{driver}", database=database).render_as_string(
            hide_password=False
        )

    def engine(self, database: str | None = None, **kwargs: Any) -> Engine:
        """A synchronous psycopg2 engine without a pool: nothing outlives the caller."""
        return create_engine(
            self.url(database or self.maintenance_db, driver="psycopg2"), poolclass=NullPool, **kwargs
        )

    def admin(self, statement: str, **params: Any) -> None:
        engine = self.engine(isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                conn.execute(text(statement), params)
        finally:
            engine.dispose()

    def describe(self) -> dict[str, Any]:
        engine = self.engine()
        try:
            with engine.connect() as conn:
                return {
                    "version": conn.execute(text("SHOW server_version")).scalar_one(),
                    "timezone": conn.execute(text("SHOW timezone")).scalar_one(),
                    "createdb": conn.execute(
                        text("SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user")
                    ).scalar_one(),
                }
        finally:
            engine.dispose()


class PgDatabases:
    """One test's databases, by label: created on first use, dropped at teardown."""

    def __init__(self, server: PostgresServer) -> None:
        self.server = server
        self._tag = uuid.uuid4().hex[:10]
        self._names: dict[str, str] = {}

    def name(self, label: str = "main") -> str:
        if label not in self._names:
            name = f"r24_{self._tag}_{len(self._names)}"
            self.server.admin(f"CREATE DATABASE \"{name}\" TEMPLATE template0 ENCODING 'UTF8'")
            self._names[label] = name
        return self._names[label]

    def url(self, label: str = "main") -> str:
        """The application's (asyncpg) URL to database ``label``."""
        return self.server.url(self.name(label))

    def engine(self, label: str = "main") -> Engine:
        """A synchronous (psycopg2) engine on database ``label``; the caller disposes it."""
        return self.server.engine(self.name(label))

    @property
    def names(self) -> list[str]:
        return list(self._names.values())

    def drop_all(self) -> None:
        """Drop every database this test created.

        Not ``WITH (FORCE)``: that also has to terminate autovacuum workers, which a role
        without ``pg_signal_backend`` may not do. Instead the test role's own leftover
        sessions are terminated and a plain ``DROP DATABASE`` (which stops autovacuum
        itself) is retried while the last backends exit."""
        for name in self._names.values():
            for attempt in range(20):
                self.server.admin(
                    "SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity "
                    "WHERE datname = :name AND usename = current_user AND pid <> pg_backend_pid()",
                    name=name,
                )
                try:
                    self.server.admin(f'DROP DATABASE IF EXISTS "{name}"')
                    break
                except OperationalError:
                    if attempt == 19:
                        raise
                    time.sleep(0.25)
        self._names.clear()


class Redirect:
    """Point an existing SQLite-bound test module at this test's PostgreSQL databases.

    Those modules build their store through a module-level factory — ``_db(tmp_path,
    name=...)`` or ``_settings(tmp_path, ...)`` — looked up when the test runs, so
    replacing the factory is enough for the original test body to run unchanged here.
    The same name (or the same ``tmp_path``) gets the same database, as a restarted
    process gets the same file.
    """

    def __init__(self, pg: PgDatabases, monkeypatch: pytest.MonkeyPatch) -> None:
        self._pg = pg
        self._monkeypatch = monkeypatch

    def database_factory(self, *modules: ModuleType) -> None:
        def _db(tmp_path: Path, name: str = "default") -> Database:
            return Database(self._pg.url(f"db:{name}"))

        for module in modules:
            assert hasattr(module, "_db"), f"{module.__name__} has no _db factory to redirect"
            self._monkeypatch.setattr(module, "_db", _db)

    def settings_factory(self, *modules: ModuleType) -> None:
        for module in modules:
            original: Callable[..., Any] = module._settings

            def _settings(
                tmp_path: Path, *args: Any, _original: Callable[..., Any] = original, **kwargs: Any
            ) -> Any:
                settings = _original(tmp_path, *args, **kwargs)
                url = self._pg.url(f"settings:{tmp_path}")
                return settings.model_copy(update={"database_url": url})

            self._monkeypatch.setattr(module, "_settings", _settings)

    def assert_ran_on_postgresql(self, tmp_path: Path) -> None:
        """The redirected test really used PostgreSQL: a database was handed out, the
        application's schema is in it, and no SQLite file appeared beside the test."""
        assert self._pg.names, "the test never asked for a database: nothing was redirected"
        for name in self._pg.names:
            engine = self._pg.server.engine(name)
            try:
                with engine.connect() as conn:
                    assert conn.execute(text("SELECT to_regclass('public.runs')")).scalar() is not None, name
            finally:
                engine.dispose()
        assert not list(tmp_path.rglob("*.db")), "a SQLite file was written: the redirect leaked"


def alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    """``python -m alembic <args>`` from the repository root with ``TIA_DATABASE_URL=url``:
    the production command (``docker-compose.prod.yml``) against this test's database."""
    env = dict(os.environ, TIA_DATABASE_URL=url)
    return subprocess.run(  # noqa: S603 - fixed argv, test-owned inputs
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=180,
        check=False,
    )
