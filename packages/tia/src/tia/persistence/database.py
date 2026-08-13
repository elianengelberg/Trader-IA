"""Database engine, sessions and schema creation.

**On migrations, honestly.** This project uses `create_all` plus a `schema_info` version
guard rather than Alembic. That is a real limitation and it is stated rather than hidden:
a clean install creates the schema correctly, but there is **no automated upgrade path
from an older database**. `ensure_schema()` refuses to open a database whose version does
not match instead of misreading it, so the failure is loud. Adding Alembic is the right
move the first time a schema change has to survive existing data; today the demo's data
is disposable and pretending otherwise would be ceremony.

SQLite is the default, deliberately: the demo must run with no daemon, no credential and
no external service. PostgreSQL works by changing one URL and is exercised by the same
tests when a server is reachable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tia.core.clock import Clock, SystemClock
from tia.core.errors import ConfigurationError
from tia.core.logging import get_logger
from tia.persistence.models import SCHEMA_VERSION, Base, SchemaInfo

_log = get_logger("persistence.database")


class Database:
    """Owns the engine and hands out sessions."""

    def __init__(self, url: str, *, echo: bool = False, clock: Clock | None = None) -> None:
        self._url = url
        self._clock = clock or SystemClock()
        self._is_sqlite = url.startswith("sqlite")

        if self._is_sqlite:
            self._prepare_sqlite_path(url)

        self._engine: AsyncEngine = create_async_engine(
            url,
            echo=echo,
            future=True,
            # SQLite's default pool serialises writers anyway; keeping the pool small
            # avoids "database is locked" under the runtime's concurrent writers.
            pool_pre_ping=not self._is_sqlite,
        )
        if self._is_sqlite:
            self._enable_sqlite_pragmas()

        self._sessions = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    @property
    def url(self) -> str:
        """Safe to log: the password, if any, is masked."""
        return _mask(self._url)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def dialect(self) -> str:
        return "sqlite" if self._is_sqlite else self._url.split("+")[0].split(":")[0]

    @staticmethod
    def _prepare_sqlite_path(url: str) -> None:
        _, _, tail = url.partition(":///")
        if not tail or tail == ":memory:":
            return
        Path(tail).expanduser().parent.mkdir(parents=True, exist_ok=True)

    def _enable_sqlite_pragmas(self) -> None:
        """WAL and foreign keys.

        SQLite has foreign keys **off by default**, which would silently accept an
        orphaned fill pointing at no order — precisely the integrity failure the schema's
        foreign keys exist to prevent. WAL lets the API read while the runtime writes.
        """

        @event.listens_for(self._engine.sync_engine, "connect")
        def _set_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session that commits on success and rolls back on any exception."""
        async with self._sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_schema(self, *, application_version: str = "0.1.0") -> None:
        """Create every table. Idempotent — safe on an existing database."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self.session() as session:
            existing = (await session.execute(select(SchemaInfo))).scalars().first()
            if existing is None:
                session.add(
                    SchemaInfo(
                        id=1,
                        version=SCHEMA_VERSION,
                        applied_at=self._clock.now(),
                        application_version=application_version,
                    )
                )
        _log.info("schema_created", version=SCHEMA_VERSION, dialect=self.dialect)

    async def ensure_schema(self, *, application_version: str = "0.1.0") -> int:
        """Create the schema if absent, and refuse to run against a mismatched one.

        A version mismatch raises. Reading a database written by a different schema is how
        a dashboard ends up showing numbers that are wrong in a way nobody notices.
        """
        await self.create_schema(application_version=application_version)

        async with self.session() as session:
            info = (await session.execute(select(SchemaInfo))).scalars().first()
            if info is None:  # pragma: no cover - create_schema just inserted it
                raise ConfigurationError("schema_info row is missing after creation")
            if info.version != SCHEMA_VERSION:
                raise ConfigurationError(
                    "database schema version does not match this build; there is no "
                    "automated migration path (see persistence/database.py)",
                    database_version=info.version,
                    expected=SCHEMA_VERSION,
                )
            return info.version

    async def drop_all(self) -> None:
        """Destructive. Used by tests and by the explicit 'reset paper account' action."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        _log.warning("schema_dropped", dialect=self.dialect)

    async def ping(self) -> bool:
        """Cheap liveness check for the health endpoint."""
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            _log.warning("database_ping_failed", error=str(exc)[:200])
            return False

    async def close(self) -> None:
        await self._engine.dispose()


def _mask(url: str) -> str:
    """Hide the password in a connection URL before it reaches a log or an API response."""
    if "://" not in url or "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    creds, _, host = rest.rpartition("@")
    if ":" not in creds:
        return url
    user, _, _password = creds.partition(":")
    return f"{scheme}://{user}:***@{host}"


def utcnow_column_default(clock: Clock) -> datetime:  # pragma: no cover - helper
    return clock.now()


__all__ = ["Database"]
