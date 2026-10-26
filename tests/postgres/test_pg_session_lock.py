"""H11 (mission v3): one realtime session per store, across processes — PostgreSQL.

Production runs PostgreSQL. The exclusion is a session-level advisory lock held on a
connection of its own; the server releases it when that connection ends. Real processes
where the claim is about processes; a terminated backend for the loss of the exclusion;
two application states for the sessions (each its own engine, so its own connections:
for PostgreSQL that is what a second process is).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.postgres.support import PgDatabases
from tia.core.errors import LiveActivationError
from tia.persistence import Database, RunRepository

ROOT = Path(__file__).resolve().parents[2]

CHILD = r"""
import asyncio, json, sys, time
from tia.persistence import Database
from tia.persistence.session_lock import SessionSlotLock

async def main(url, hold, go_at):
    db = Database(url)
    lock = SessionSlotLock(db)
    while time.time() < go_at:
        await asyncio.sleep(0.001)
    got = await lock.acquire()
    print("RESULT " + json.dumps({"got": got, "at": time.time()}), flush=True)
    await asyncio.sleep(hold)
    await lock.release()
    await db.close()

asyncio.run(main(sys.argv[1], float(sys.argv[2]), float(sys.argv[3])))
"""


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TZ", "HTTP_PROXY", "HTTPS_PROXY")}
    env["PYTHONPATH"] = str(ROOT / "packages/tia/src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _children(url: str, n: int, *, hold: float) -> list[subprocess.Popen[str]]:
    go_at = time.time() + 3.0
    return [
        subprocess.Popen([sys.executable, "-c", CHILD, url, str(hold), str(go_at)], cwd=ROOT, env=_env(),  # noqa: S603
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(n)
    ]


def _result(text_out: str) -> dict[str, Any]:
    [line] = [x for x in text_out.splitlines() if x.startswith("RESULT ")]
    return json.loads(line[len("RESULT "):])


async def test_two_engines_exclude_each_other_and_release_hands_over(pg: PgDatabases) -> None:
    from tia.persistence.session_lock import SessionSlotLock

    url = pg.url()
    a, b = Database(url), Database(url)
    first, second = SessionSlotLock(a), SessionSlotLock(b)
    try:
        assert await first.acquire() is True
        assert await second.acquire() is False
        assert await first.still_held() is True
        await first.release()
        assert await second.acquire() is True
    finally:
        await first.release()
        await second.release()
        await a.close()
        await b.close()


async def test_the_holding_connection_is_not_left_idle_in_a_transaction(pg: PgDatabases) -> None:
    """Held for hours: it must not pin a snapshot (idle in transaction) on the server."""
    from tia.persistence.session_lock import SessionSlotLock

    url = pg.url()
    db, probe = Database(url), Database(url)
    lock = SessionSlotLock(db)
    try:
        assert await lock.acquire()
        async with probe.session() as session:
            states = [r[0] for r in (await session.execute(text(
                "SELECT a.state FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                "WHERE l.locktype = 'advisory' AND l.granted"))).all()]
        assert states == ["idle"], states
    finally:
        await lock.release()
        await db.close()
        await probe.close()


def test_of_four_processes_starting_at_the_same_instant_exactly_one_gets_the_slot(pg: PgDatabases) -> None:
    url = pg.url()
    procs = _children(url, 4, hold=3.0)
    results = []
    for p in procs:
        out, err = p.communicate(timeout=90)
        assert p.returncode == 0, err[-2000:]
        results.append(_result(out))
    assert sum(r["got"] for r in results) == 1, results


def test_a_holder_killed_with_sigkill_frees_the_slot_without_a_timeout(pg: PgDatabases) -> None:
    url = pg.url()
    [holder] = _children(url, 1, hold=600.0)
    assert holder.stdout is not None
    line = holder.stdout.readline()
    while not line.startswith("RESULT "):
        assert line, "the holder ended before reporting"
        line = holder.stdout.readline()
    assert _result(line)["got"] is True
    os.kill(holder.pid, signal.SIGKILL)
    holder.wait(timeout=30)
    killed_at = time.monotonic()
    got = False
    while not got and time.monotonic() - killed_at < 10.0:
        [after] = _children(url, 1, hold=0.0)
        out, _ = after.communicate(timeout=60)
        got = _result(out)["got"]
    assert got, "the server released the lock when the killed process's connection closed"


async def test_a_terminated_backend_is_reported_as_a_lost_exclusion(pg: PgDatabases) -> None:
    from tia.persistence.session_lock import SessionSlotLock

    url = pg.url()
    db, admin = Database(url), Database(url)
    lock = SessionSlotLock(db)
    try:
        assert await lock.acquire()
        async with admin.session() as session:
            await session.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_locks WHERE locktype = 'advisory' AND granted"))
        await asyncio.sleep(0.2)
        assert await lock.still_held() is False
        assert lock.held is False
        assert await lock.acquire() is True, "nobody else held it: taken again"
    finally:
        await lock.release()
        await db.close()
        await admin.close()


# ----------------------------------------------------------------------- the sessions


def _app(pg: PgDatabases, tmp_path: Path) -> Any:
    from tests.integration.test_live_api import _settings
    from tia.api.state import AppState

    return AppState(_settings(tmp_path).model_copy(update={"database_url": pg.url()}))


async def test_two_app_states_starting_together_end_with_one_session(
    pg: PgDatabases, tmp_path: Path, fake_public_feed: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tia.api.state import AppState

    first, second = _app(pg, tmp_path), _app(pg, tmp_path)
    await first.database.ensure_schema()
    barrier = asyncio.Barrier(2)
    real = AppState._load_account_restore

    async def after_the_lease_read(self: AppState, **kwargs: Any) -> Any:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(barrier.wait(), timeout=2.0)
        return await real(self, **kwargs)

    monkeypatch.setattr(AppState, "_load_account_restore", after_the_lease_read)
    try:
        results = await asyncio.gather(
            first.start_paper_realtime(actor="process-a"),
            second.start_paper_realtime(actor="process-b"),
            return_exceptions=True,
        )
        running = [s for s in (first, second) if s.live_runtime is not None and s.live_runtime.is_running]
        async with first.database.session() as session:
            open_runs = await RunRepository(session).open_sessions(mode="paper-live")
        refused = [r for r in results if isinstance(r, LiveActivationError)]
        assert len(running) == 1 and len(open_runs) == 1, {"results": results, "open_runs": open_runs}
        assert len(refused) == 1 and "session lock" in str(refused[0])
    finally:
        await first.shutdown()
        await second.shutdown()


async def test_two_boots_after_a_crash_resume_the_interrupted_run_at_most_once(
    pg: PgDatabases, tmp_path: Path, fake_public_feed: None, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redeploy that briefly runs two containers: both boot over a crash-interrupted run
    whose heartbeat is stale, both decide to resume it. One session, not two.

    Two barriers force the interleaving (without them the two boots happen to serialise and
    the test passed on the v2 tree, which has no exclusion): both boots read the unstopped
    row before either stamps it, and both read the lease before either writes its own."""
    from tests.postgres.test_pg_concurrency import _open_run
    from tia.api.state import AppState
    from tia.persistence import RunRepository as Runs

    first, second = _app(pg, tmp_path), _app(pg, tmp_path)
    await first.database.ensure_schema()
    await _open_run(first.database, "run_crashed")  # stopped_at NULL, no heartbeat: dead
    read_row, read_lease = asyncio.Barrier(2), asyncio.Barrier(2)
    calls = {"stop": 0, "restore": 0}
    real_stop, real_restore = Runs.stop, AppState._load_account_restore

    async def both_read_the_row(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls["stop"] += 1
        if calls["stop"] <= 2:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(read_row.wait(), timeout=2.0)
        return await real_stop(self, *args, **kwargs)

    async def both_read_the_lease(self: AppState, **kwargs: Any) -> Any:
        calls["restore"] += 1
        if calls["restore"] <= 2:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(read_lease.wait(), timeout=2.0)
        return await real_restore(self, **kwargs)

    monkeypatch.setattr(Runs, "stop", both_read_the_row)
    monkeypatch.setattr(AppState, "_load_account_restore", both_read_the_lease)
    try:
        await asyncio.gather(first.startup(), second.startup())
        running = [s for s in (first, second) if s.live_runtime is not None and s.live_runtime.is_running]
        async with first.database.session() as session:
            open_runs = await RunRepository(session).open_sessions(mode="paper-live")
        assert len(running) == 1 and len(open_runs) == 1, open_runs
    finally:
        await first.shutdown()
        await second.shutdown()
