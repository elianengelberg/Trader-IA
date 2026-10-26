"""H11 (mission v3): one realtime session per store, across processes — SQLite.

The heartbeat lease detects another live process but cannot exclude two that start in the
same window. ``SessionSlotLock`` is the exclusion. These tests use real operating-system
processes where the claim is about processes (an in-process mutex would pass them by
construction), and the application path (``AppState``) where the claim is about sessions.
The PostgreSQL side is ``tests/postgres/test_pg_session_lock.py``.
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

from tests.integration.test_live_api import _FakePublicFeed
from tests.integration.test_run_lifecycle import _state
from tia.core.errors import LiveActivationError
from tia.persistence import Database, RunRepository

ROOT = Path(__file__).resolve().parents[2]

#: A child process: open the store, try the slot, report, hold it until told (or killed).
CHILD = r"""
import asyncio, json, sys, time
from tia.persistence import Database
from tia.persistence.session_lock import SessionSlotLock

async def main(url, hold, go_at):
    db = Database(url)
    lock = SessionSlotLock(db)
    while time.time() < go_at:          # every child tries at the same instant
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
    go_at = time.time() + 2.0
    return [
        subprocess.Popen([sys.executable, "-c", CHILD, url, str(hold), str(go_at)], cwd=ROOT, env=_env(),  # noqa: S603
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(n)
    ]


def _result(text: str) -> dict[str, Any]:
    """The child's verdict line (its log lines share stdout)."""
    [line] = [x for x in text.splitlines() if x.startswith("RESULT ")]
    return json.loads(line[len("RESULT "):])


def _url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'store.db'}"


async def test_two_locks_on_one_store_exclude_each_other_and_release_hands_over(tmp_path: Path) -> None:
    from tia.persistence.session_lock import SessionSlotLock

    a, b = Database(_url(tmp_path)), Database(_url(tmp_path))
    first, second = SessionSlotLock(a), SessionSlotLock(b)
    try:
        assert await first.acquire() is True
        assert await first.acquire() is True, "re-entrant for its holder"
        assert await second.acquire() is False, "a second holder is refused, not queued"
        assert "process" in second.holder_hint() and str(os.getpid()) in second.holder_hint()
        await first.release()
        assert await second.acquire() is True, "released: the next one gets it"
        assert await second.still_held() is True
    finally:
        await first.release()
        await second.release()
        await a.close()
        await b.close()


async def test_a_deleted_lock_file_is_reported_as_a_lost_exclusion(tmp_path: Path) -> None:
    """A deleted (or replaced) lock file would let a second process lock a different file."""
    from tia.persistence.session_lock import SessionSlotLock

    db = Database(_url(tmp_path))
    lock = SessionSlotLock(db)
    try:
        assert await lock.acquire()
        await asyncio.to_thread(Path(lock.describe()["file"]).unlink)
        assert await lock.still_held() is False
    finally:
        await lock.release()
        await db.close()


async def test_a_replaced_lock_file_is_reported_as_a_lost_exclusion(tmp_path: Path) -> None:
    """The threat the inode check is for: the file is removed and another process creates and
    locks a new one at the same path. Both would believe they hold the slot."""
    from tia.persistence.session_lock import SessionSlotLock

    a, b = Database(_url(tmp_path)), Database(_url(tmp_path))
    first, second = SessionSlotLock(a), SessionSlotLock(b)
    try:
        assert await first.acquire()
        await asyncio.to_thread(Path(first.describe()["file"]).unlink)
        assert await second.acquire() is True, "a new file at the same path is a new, free lock"
        assert await first.still_held() is False, "the first holder must learn it lost the exclusion"
        assert await second.still_held() is True
    finally:
        await first.release()
        await second.release()
        await a.close()
        await b.close()


def test_of_four_processes_starting_at_the_same_instant_exactly_one_gets_the_slot(tmp_path: Path) -> None:
    url = _url(tmp_path)
    procs = _children(url, 4, hold=3.0)
    results = []
    for p in procs:
        out, err = p.communicate(timeout=60)
        assert p.returncode == 0, err[-2000:]
        results.append(_result(out))
    assert sum(r["got"] for r in results) == 1, results


def test_a_holder_killed_with_sigkill_frees_the_slot_at_once(tmp_path: Path) -> None:
    url = _url(tmp_path)
    [holder] = _children(url, 1, hold=600.0)
    assert holder.stdout is not None
    line = holder.stdout.readline()
    while not line.startswith("RESULT "):
        assert line, "the holder ended before reporting"
        line = holder.stdout.readline()
    assert _result(line)["got"] is True, line
    [refused] = _children(url, 1, hold=0.0)
    out, _ = refused.communicate(timeout=60)
    assert _result(out)["got"] is False, "held while the holder lives"
    os.kill(holder.pid, signal.SIGKILL)
    holder.wait(timeout=30)
    [after] = _children(url, 1, hold=0.0)
    out, _ = after.communicate(timeout=60)
    assert _result(out)["got"] is True, "the kernel released it with the process"


# ----------------------------------------------------------------------- the sessions


@pytest.fixture(autouse=True)
def _feed(monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)


async def test_two_app_states_starting_together_end_with_one_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The H11 interleaving on SQLite: both read the lease before either writes its row."""
    from tia.api.state import AppState

    first, second = await _state(tmp_path), await _state(tmp_path)
    barrier = asyncio.Barrier(2)
    real = AppState._load_account_restore

    async def after_the_lease_read(self: AppState, **kwargs: Any) -> Any:
        # Without the exclusion both get here and pass together; with it, the winner waits
        # the barrier out alone (the loser was refused before this point).
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
        assert len(refused) == 1 and "session lock" in str(refused[0]), results
    finally:
        await first.shutdown()
        await second.shutdown()


async def test_a_stopped_session_hands_the_slot_to_the_next_process(tmp_path: Path) -> None:
    first, second = await _state(tmp_path), await _state(tmp_path)
    try:
        await first.start_paper_realtime(actor="a")
        with pytest.raises(LiveActivationError, match="session lock"):
            await second.start_paper_realtime(actor="b")
        await first.stop_realtime_session(reason="operator stop")
        assert first._session_slot.held is False, "an operator stop releases the slot"
        await second.start_paper_realtime(actor="b")
        assert second.live_runtime is not None and second.live_runtime.is_running
    finally:
        await first.shutdown()
        await second.shutdown()


async def test_a_session_in_safe_mode_keeps_the_slot_through_a_refused_second_start(tmp_path: Path) -> None:
    """SAFE_MODE is not "running" for trading, but the session still owns its positions. A
    second start in the same process is refused, and that refusal must not hand the slot to
    another process (found in review: the first idleness test was ``is_running``)."""
    from tia.runtime.states import LiveState

    first, second = await _state(tmp_path), await _state(tmp_path)
    try:
        await first.start_paper_realtime(actor="a")
        live = first.live_runtime
        assert live is not None
        live.machine.transition(LiveState.SAFE_MODE, reason="test: something is unknown")
        with pytest.raises(LiveActivationError):
            await first.start_paper_realtime(actor="a-again")
        assert first._session_slot.held, "the slot stays with the session in safe mode"
        with pytest.raises(LiveActivationError, match="session lock"):
            await second.start_paper_realtime(actor="b")
    finally:
        await first.shutdown()
        await second.shutdown()


async def test_a_session_in_safe_mode_is_stopped_recorded_and_released_at_shutdown(tmp_path: Path) -> None:
    """The shutdown stopped only a session that was trading (``is_running``): one in SAFE_MODE
    kept its heartbeat lease and got no stop record (found in review, mission v3)."""
    import json

    from sqlalchemy import text

    from tia.runtime.states import LiveState

    state = await _state(tmp_path)
    url = state.settings.database_url
    await state.start_paper_realtime(actor="a")
    live = state.live_runtime
    assert live is not None
    run_id = live.run_id
    live.machine.transition(LiveState.SAFE_MODE, reason="test: something is unknown")
    await state.shutdown()
    assert live.machine.state.is_terminal, "stopped by the shutdown"
    db = Database(url)
    try:
        async with db.session() as session:
            notes = (await session.execute(text("SELECT notes FROM runs WHERE run_id = :r"), {"r": run_id})).scalar()
    finally:
        await db.close()
    doc = json.loads(notes or "{}")
    assert (doc.get("persistence") or {}).get("status") == "complete", doc
    assert doc.get("heartbeat_at") is None, "the lease was released for the next boot"


async def test_a_start_that_fails_after_the_claim_releases_the_slot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tia.api.state import AppState

    state = await _state(tmp_path)

    async def broken(self: AppState, **kwargs: Any) -> Any:
        raise RuntimeError("the store went away mid-start")

    monkeypatch.setattr(AppState, "_load_account_restore", broken)
    try:
        with pytest.raises(RuntimeError, match="went away"):
            await state.start_paper_realtime(actor="a")
        assert state._session_slot.held is False, "no session, no slot"
    finally:
        await state.shutdown()


async def test_a_shutdown_releases_the_slot_for_the_next_boot(tmp_path: Path) -> None:
    first = await _state(tmp_path)
    await first.start_paper_realtime(actor="a")
    await first.shutdown()
    assert first._session_slot.held is False
    second = await _state(tmp_path)
    try:
        assert await second._session_slot.acquire() is True
    finally:
        await second._session_slot.release()
        await second.shutdown()


async def test_a_lost_exclusion_blocks_new_entries_and_records_an_incident(tmp_path: Path) -> None:
    from sqlalchemy import text

    state = await _state(tmp_path)
    try:
        await state.start_paper_realtime(actor="a")
        live = state.live_runtime
        assert live is not None
        await asyncio.to_thread(Path(state._session_slot.describe()["file"]).unlink)  # the exclusion is gone
        assert await state._verify_session_slot() is False
        assert "session_lock_lost" in live.entry_blocks, "no new entries without the exclusion"
        await live.flush_persistence(timeout_seconds=10.0)
        async with state.database.session() as session:
            kinds = [r[0] for r in (await session.execute(text("SELECT kind FROM incidents"))).all()]
        assert "entries_blocked:session_lock_lost" in kinds, kinds
    finally:
        await state.shutdown()
