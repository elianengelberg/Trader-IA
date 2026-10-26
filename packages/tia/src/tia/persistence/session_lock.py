"""Cross-process exclusion of the realtime session slot (H11, mission v3).

The heartbeat lease (Phase 1.3, G9) *detects* another process that is running a session
over the same store; it cannot *exclude* two processes that both read "no lease" in the
same window and then both start (H11, reproduced on PostgreSQL). This lock is the
exclusion: only the process that holds it may run a realtime session (paper-live or live)
over this store. It is taken before anything else of a start and is never queued: a second
process is refused at once.

* **PostgreSQL**: a session-level advisory lock (``pg_try_advisory_lock``) held on a
  connection of its own for as long as the session runs. The server releases it when that
  connection ends: a clean stop, a process killed with SIGKILL, a container that is gone.
  There is no timeout to wait out and nothing to clean up.
* **SQLite** (one host by construction): an exclusive ``flock`` on
  ``<database file>.session.lock``, held through an open descriptor. The kernel releases it
  when the process dies. The holder writes its pid and the time into the file, so a refused
  start can say who holds it.
* **SQLite in memory**: no other process can open that store; the lock is process-local.

``still_held()`` answers whether the exclusion still stands (the connection is alive; the
lock file is still the file this process locked). A session that finds it gone must stop
taking new entries: another process may now be running the same account.
"""

from __future__ import annotations

import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from tia.core.clock import SystemClock
from tia.core.logging import get_logger

_log = get_logger("persistence.session_lock")

#: The one realtime session slot of a store (paper-live and live share it, as they share
#: ``AppState.live_runtime``).
REALTIME_SESSION = "tia.realtime-session"

#: Process-local holders for stores no other process can open (SQLite in memory).
_LOCAL_HOLDERS: dict[str, int] = {}
_LOCAL_GUARD = threading.Lock()


def advisory_key(name: str) -> int:
    """A stable signed 64-bit key for ``pg_try_advisory_lock`` from a lock name."""
    return int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)


def sqlite_path(url: str) -> Path | None:
    """The database file of a SQLite URL, or ``None`` for an in-memory store."""
    _, _, tail = url.partition(":///")
    if not tail or tail.startswith(":memory:") or "mode=memory" in tail:
        return None
    return Path(tail.split("?", 1)[0]).expanduser().resolve()


class SessionSlotLock:
    """Non-blocking, re-entrant per instance, released by the operating system or the server
    when the holding process ends."""

    def __init__(self, database: Any, name: str = REALTIME_SESSION) -> None:
        self._database = database
        self._name = name
        self._key = advisory_key(name)
        self._conn: AsyncConnection | None = None  # PostgreSQL
        self._fd: int | None = None  # SQLite file
        self._file: Path | None = None
        self._inode: tuple[int, int] | None = None
        self._local = False  # SQLite in memory
        self._since: datetime | None = None
        self._mutex = asyncio.Lock()

    # ------------------------------------------------------------------ state

    @property
    def held(self) -> bool:
        return self._conn is not None or self._fd is not None or self._local

    def describe(self) -> dict[str, Any]:
        backend = "postgresql" if self._database.dialect != "sqlite" else (
            "sqlite-memory" if sqlite_path(self._raw_url()) is None else "sqlite-file")
        return {
            "name": self._name, "backend": backend, "held": self.held,
            "since": self._since.isoformat() if self._since else None,
            "file": str(self._file) if self._file else None,
        }

    def _now(self) -> datetime:
        """The store's own clock (``Database`` carries one): this package never reads the wall
        clock directly (``tests/unit/test_scope_boundary.py``)."""
        clock = getattr(self._database, "_clock", None)
        return clock.now() if clock is not None else SystemClock().now()

    def _raw_url(self) -> str:
        return str(self._database.engine.url.render_as_string(hide_password=False))

    # ------------------------------------------------------------------ acquire / release

    async def acquire(self) -> bool:
        """Take the slot. ``True`` if this instance holds it (now or already); ``False`` if
        another holder has it. Errors reaching the store propagate: an unreadable store is
        not a free slot."""
        async with self._mutex:
            if self.held:
                return True
            if self._database.dialect == "sqlite":
                ok = self._acquire_sqlite()
            else:
                ok = await self._acquire_postgres()
            if ok:
                self._since = self._now()
                _log.info("session_lock_acquired", **self.describe())
            return ok

    async def release(self) -> None:
        async with self._mutex:
            await self._release_unlocked()

    async def _release_unlocked(self) -> None:
        was = self.held
        if self._conn is not None:
            conn, self._conn = self._conn, None
            try:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": self._key})
                await conn.commit()
            except Exception as exc:  # the connection's end releases it anyway
                _log.warning("session_lock_unlock_failed", error=str(exc)[:200])
            finally:
                with contextlib.suppress(Exception):
                    await conn.close()
        if self._fd is not None:
            fd, self._fd = self._fd, None
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            with contextlib.suppress(OSError):
                os.close(fd)
            self._inode = None
        if self._local:
            self._local = False
            with _LOCAL_GUARD:
                if _LOCAL_HOLDERS.get(self._local_key()) == id(self):
                    del _LOCAL_HOLDERS[self._local_key()]
        if was:
            _log.info("session_lock_released", name=self._name)
        self._since = None

    async def still_held(self) -> bool:
        """Whether the exclusion still stands. PostgreSQL: the holding connection answers
        (a session-level lock lives exactly as long as its connection). SQLite: the path
        still names the file this process locked (a deleted or replaced lock file would let
        a second process lock a different file)."""
        async with self._mutex:
            if self._conn is not None:
                try:
                    await self._conn.execute(text("SELECT 1"))
                    await self._conn.commit()
                    return True
                except Exception as exc:
                    _log.error("session_lock_connection_lost", error=str(exc)[:200])
                    with contextlib.suppress(Exception):
                        await self._conn.close()
                    self._conn = None
                    return False
            if self._fd is not None and self._file is not None:
                try:
                    st = self._file.stat()
                except OSError:
                    return False
                return (st.st_dev, st.st_ino) == self._inode
            return self._local

    # ------------------------------------------------------------------ backends

    async def _acquire_postgres(self) -> bool:
        conn = await self._database.engine.connect()
        try:
            got = (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": self._key})).scalar()
            # Session-level: it outlives the transaction. Commit so the connection is not
            # left idle in a transaction for the life of the session.
            await conn.commit()
        except BaseException:
            with contextlib.suppress(Exception):
                await conn.close()
            raise
        if got:
            self._conn = conn
            return True
        await conn.close()
        return False

    def _acquire_sqlite(self) -> bool:
        path = sqlite_path(self._raw_url())
        if path is None:
            with _LOCAL_GUARD:
                holder = _LOCAL_HOLDERS.get(self._local_key())
                if holder is not None and holder != id(self):
                    return False
                _LOCAL_HOLDERS[self._local_key()] = id(self)
            self._local = True
            return True
        lock_file = path.with_name(path.name + ".session.lock")
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        except BaseException:
            os.close(fd)
            raise
        st = os.fstat(fd)
        self._fd, self._file, self._inode = fd, lock_file, (st.st_dev, st.st_ino)
        with contextlib.suppress(OSError):
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps({"pid": os.getpid(), "since": self._now().isoformat(),
                                     "name": self._name}).encode())
        return True

    def _local_key(self) -> str:
        return f"{self._raw_url()}#{self._name}"

    def holder_hint(self) -> str:
        """Who holds the slot, as far as this store can tell (for a refusal message)."""
        if self._database.dialect == "sqlite":
            path = sqlite_path(self._raw_url())
            if path is None:
                return "another holder in this process"
            lock_file = path.with_name(path.name + ".session.lock")
            with contextlib.suppress(OSError, ValueError):
                info = json.loads(lock_file.read_text() or "{}")
                return f"process {info.get('pid')} since {info.get('since')} ({lock_file})"
            return f"the holder of {lock_file}"
        return "another connection to this PostgreSQL database (pg_locks, advisory)"


__all__ = ["REALTIME_SESSION", "SessionSlotLock", "advisory_key", "sqlite_path"]
