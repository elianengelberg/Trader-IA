"""One session per account across *processes* (Phase 1.3, G9).

The application lock closes the F5 race inside one process. A second container over the
same store, or a stale deploy still running, is invisible to it; what makes it visible is
the heartbeat the running session stamps into its run row. These tests drive ``AppState``
over a temporary store and write the "other process" heartbeat by hand.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from tests.integration.test_live_api import _FakePublicFeed, _settings
from tia.api.state import AppState
from tia.core.errors import LiveActivationError
from tia.persistence import RunRepository
from tia.runtime.session_limits import LEASE_SECONDS, decode_heartbeat, encode_heartbeat


@pytest.fixture(autouse=True)
def _feed(monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.data.providers.binance_public as binance_public

    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)


async def _state(tmp_path: Path, *, probe_seconds: float = 0.05) -> AppState:
    state = AppState(_settings(tmp_path))
    state._lease_probe_seconds = probe_seconds
    alerts: list[dict[str, Any]] = []
    state._dispatch_alert = alerts.append  # type: ignore[method-assign]
    state._alerts = alerts  # type: ignore[attr-defined]
    return state


async def _other_process_row(state: AppState, *, run_id: str, beat_age_seconds: float) -> None:
    """A paper-live run another process is running: open, with a heartbeat."""
    await state.database.ensure_schema()
    now = datetime.now(UTC)
    async with state.database.session() as session:
        await RunRepository(session).create(
            run_id=run_id, mode="paper-live", scenario="realtime", started_at=now - timedelta(hours=1),
            initial_capital=10_000.0, seed=1, symbols=("BTC-USD",),
            notes=encode_heartbeat("", at=now - timedelta(seconds=beat_age_seconds)),
        )


async def _row(state: AppState, run_id: str) -> tuple[str, Any]:
    async with state.database.session() as session:
        row = (
            await session.execute(text("SELECT notes, stopped_at FROM runs WHERE run_id = :r"), {"r": run_id})
        ).first()
    assert row is not None
    return str(row[0] or ""), row[1]


async def _wait_probe(state: AppState) -> None:
    task = state._lease_probe_task
    assert task is not None, "the boot deferred its decision to a probe"
    await asyncio.wait_for(task, timeout=5.0)


# ------------------------------------------------------------- a start over a held lease


async def test_a_start_is_refused_while_another_process_heartbeats_the_account(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    await _other_process_row(state, run_id="run_other", beat_age_seconds=5.0)
    # No boot-time resume here: startup is what reads the row; this is an operator's
    # start request arriving at a process that holds nothing.
    with pytest.raises(LiveActivationError, match="another process holds an active paper session"):
        await state.start_paper_realtime(actor="operator")
    assert state.live_runtime is None
    notes, stopped_at = await _row(state, "run_other")
    assert stopped_at is None and decode_heartbeat(notes) is not None, "the other run's row is untouched"
    await state.shutdown()


async def test_a_start_proceeds_once_the_other_heartbeat_is_stale(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    await _other_process_row(state, run_id="run_dead", beat_age_seconds=LEASE_SECONDS + 5)
    snapshot = await state.start_paper_realtime(actor="operator")
    assert state.live_runtime is not None and state.live_runtime.is_running
    assert snapshot["run_id"] != "run_dead"
    await state.shutdown()


# ------------------------------------------------------------- the boot's decision


async def test_a_boot_does_not_resume_or_stamp_a_run_whose_heartbeat_keeps_advancing(tmp_path: Path) -> None:
    state = await _state(tmp_path, probe_seconds=0.2)
    await _other_process_row(state, run_id="run_live_elsewhere", beat_age_seconds=1.0)

    async def other_process_keeps_beating() -> None:
        for _ in range(3):
            await asyncio.sleep(0.05)
            async with state.database.session() as session:
                await RunRepository(session).heartbeat("run_live_elsewhere", datetime.now(UTC))

    beater = asyncio.create_task(other_process_keeps_beating())
    await state.startup()
    assert state.live_runtime is None, "nothing resumed at boot"
    await beater
    await _wait_probe(state)
    assert state.live_runtime is None, "nor after the probe: the heartbeat advanced"
    _notes, stopped_at = await _row(state, "run_live_elsewhere")
    assert stopped_at is None, "the other process's row was not stamped"
    kinds = [a["kind"] for a in state._alerts]  # type: ignore[attr-defined]
    assert "paper_session_held_by_other_process" in kinds
    await state.shutdown()


async def test_a_boot_resumes_a_run_whose_fresh_heartbeat_does_not_advance_after_the_probe(tmp_path: Path) -> None:
    """A hard crash seconds before the restart: the heartbeat is fresh but its writer is
    gone. After the probe the boot stamps the dead run and resumes, as it always has."""
    state = await _state(tmp_path, probe_seconds=0.1)
    await _other_process_row(state, run_id="run_crashed", beat_age_seconds=3.0)
    await state.startup()
    assert state.live_runtime is None, "not yet: the heartbeat is fresh"
    await _wait_probe(state)
    assert state.live_runtime is not None and state.live_runtime.is_running
    _notes, stopped_at = await _row(state, "run_crashed")
    assert stopped_at is not None, "the dead run was stamped"
    assert state.live_runtime.run_id != "run_crashed"
    assert not [a for a in state._alerts if a["kind"] == "paper_session_held_by_other_process"]  # type: ignore[attr-defined]
    await state.shutdown()


async def test_a_boot_resumes_a_run_without_a_heartbeat_at_once(tmp_path: Path) -> None:
    """The row a pre-1.3 process (or a clean shutdown) leaves: no heartbeat, no wait."""
    state = await _state(tmp_path)
    await state.database.ensure_schema()
    async with state.database.session() as session:
        await RunRepository(session).create(
            run_id="run_old", mode="paper-live", scenario="realtime", started_at=datetime.now(UTC) - timedelta(hours=1),
            initial_capital=10_000.0, seed=1, symbols=("BTC-USD",),
        )
    await state.startup()
    assert state.live_runtime is not None and state.live_runtime.is_running
    assert state._lease_probe_task is None
    _notes, stopped_at = await _row(state, "run_old")
    assert stopped_at is not None
    await state.shutdown()


# ------------------------------------------------------------- the session's own heartbeat


async def test_a_running_session_stamps_its_heartbeat_and_a_clean_shutdown_releases_it(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    await state.startup()
    snapshot = await state.start_paper_realtime(actor="operator")
    run_id = snapshot["run_id"]
    runtime = state.live_runtime
    assert runtime is not None
    await runtime._cycle_once()
    assert await runtime.flush_persistence(timeout_seconds=10.0)
    notes, stopped_at = await _row(state, run_id)
    beat = decode_heartbeat(notes)
    assert beat is not None and abs((datetime.now(UTC) - beat).total_seconds()) < 60
    assert stopped_at is None

    await state.shutdown()  # a redeploy's SIGTERM: not an operator stop
    notes, stopped_at = await _row(state, run_id)
    assert stopped_at is None, "unstamped: the next boot resumes it"
    assert decode_heartbeat(notes) is None, "but the lease is released, so it resumes at once"

    # And it does — without a probe.
    again = await _state(tmp_path)
    await again.startup()
    assert again.live_runtime is not None and again.live_runtime.is_running
    assert again._lease_probe_task is None
    await again.shutdown()


async def test_the_sessions_own_run_is_not_a_foreign_lease(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    await state.startup()
    await state.start_paper_realtime(actor="operator")
    runtime = state.live_runtime
    await runtime._cycle_once()
    assert await runtime.flush_persistence(timeout_seconds=10.0)
    assert await state._foreign_session_lease(mode="paper-live") is None
    with pytest.raises(LiveActivationError, match="already active"):
        await state.start_paper_realtime(actor="operator")
    await state.shutdown()
