"""The live path starts a session the way the paper path does (Phase 1.3, G10).

Nothing here reaches a venue: the shared helper is driven with a stub runtime over the
real store, and the live arming path is driven with the gate and the runtime builder
replaced, so what is tested is the *ordering* the two paths now share — the run row
before the loop, a stamped row after a failed start, no orphan stamping of a real
venue's orders.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from tests.integration.test_live_api import _settings
from tia.api.state import AppState
from tia.core.errors import LiveActivationError
from tia.domain.enums import OrderState, OrderType, Side
from tia.domain.orders import Order
from tia.persistence import OrderRepository, RunRepository


class _StubRuntime:
    def __init__(self, run_id: str, *, fail: Exception | None = None, state: AppState | None = None) -> None:
        self.run_id = run_id
        self.session_deadline = None
        self._fail = fail
        self._state = state
        self.row_seen_at_start: bool | None = None
        self.started = False

    @property
    def state(self):  # type: ignore[no-untyped-def]
        class _S:
            value = "running"

        return _S()

    async def start(self) -> None:
        if self._state is not None:
            async with self._state.database.session() as session:
                self.row_seen_at_start = (await RunRepository(session).get(self.run_id)) is not None
        if self._fail is not None:
            raise self._fail
        self.started = True


async def _state(tmp_path: Path) -> AppState:
    state = AppState(_settings(tmp_path))
    await state.database.ensure_schema()
    return state


async def _rows(state: AppState) -> list[tuple[str, str, str | None, Any]]:
    async with state.database.session() as session:
        rows = (await session.execute(text("SELECT run_id, mode, notes, stopped_at FROM runs ORDER BY started_at"))).all()
    return [(str(r[0]), str(r[1]), r[2], r[3]) for r in rows]


async def test_the_shared_helper_writes_the_row_before_it_starts_the_loop(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    runtime = _StubRuntime("run_live_1", state=state)
    orphaned = await state._start_session_with_run_row(
        runtime, mode="live", scenario="live", initial_capital=500.0, seed=0, symbols=("BTC-USD",),
        notes="", orphan_earlier_orders=False,
    )
    assert runtime.started and runtime.row_seen_at_start is True
    assert orphaned == 0
    rows = await _rows(state)
    assert [(r[0], r[1], r[3]) for r in rows] == [("run_live_1", "live", None)]
    await state.database.close()


async def test_a_failed_start_leaves_a_stamped_annotated_row_and_re_raises(tmp_path: Path) -> None:
    state = await _state(tmp_path)
    runtime = _StubRuntime("run_live_2", fail=LiveActivationError("clock skew 2400 ms"), state=state)
    with pytest.raises(LiveActivationError, match="clock skew"):
        await state._start_session_with_run_row(
            runtime, mode="live", scenario="live", initial_capital=500.0, seed=0, symbols=("BTC-USD",),
            orphan_earlier_orders=False,
        )
    assert runtime.row_seen_at_start is True
    (run_id, _mode, notes, stopped_at), = await _rows(state)
    assert run_id == "run_live_2" and stopped_at is not None
    assert notes and "start_failed" in notes and "clock skew" in notes
    await state.database.close()


async def test_a_row_that_cannot_be_written_starts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tia.persistence import repositories as repositories_module

    state = await _state(tmp_path)

    async def broken(self: RunRepository, **kwargs: Any) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(repositories_module.RunRepository, "create", broken)
    runtime = _StubRuntime("run_live_3", state=state)
    with pytest.raises(LiveActivationError, match="run row could not be persisted"):
        await state._start_session_with_run_row(
            runtime, mode="live", scenario="live", initial_capital=500.0, seed=0, symbols=("BTC-USD",),
            orphan_earlier_orders=False,
        )
    assert runtime.started is False and runtime.row_seen_at_start is None
    await state.database.close()


async def test_a_live_start_does_not_stamp_an_earlier_runs_open_orders_as_orphaned(tmp_path: Path) -> None:
    """A real venue keeps its orders across our restarts; only a paper engine loses them.
    The paper path stamps earlier paper orders; the live path stamps nothing."""
    state = await _state(tmp_path)
    now = datetime.now(UTC)
    async with state.database.session() as session:
        await RunRepository(session).create(
            run_id="run_live_old", mode="live", scenario="live", started_at=now, initial_capital=500.0,
            seed=0, symbols=("BTC-USD",),
        )
        await RunRepository(session).create(
            run_id="run_paper_old", mode="paper-live", scenario="realtime", started_at=now, initial_capital=10_000.0,
            seed=1, symbols=("BTC-USD",),
        )
        for run_id, coid in (("run_live_old", "coid_live_resting"), ("run_paper_old", "coid_paper_resting")):
            await OrderRepository(session).upsert(
                run_id,
                Order(
                    order_id=f"ord_{coid}", client_order_id=coid, intent_id="i", signal_id="protective:BTC-USD",
                    symbol="BTC-USD", side=Side.SELL, order_type=OrderType.STOP, quantity=0.01, stop_price=1.0,
                    state=OrderState.ACKNOWLEDGED, created_at=now, updated_at=now,
                ),
            )

    async def states() -> dict[str, str]:
        async with state.database.session() as session:
            rows = (await session.execute(text("SELECT client_order_id, state FROM orders"))).all()
        return {str(r[0]): str(r[1]) for r in rows}

    live_runtime = _StubRuntime("run_live_new")
    orphaned = await state._start_session_with_run_row(
        live_runtime, mode="live", scenario="live", initial_capital=500.0, seed=0, symbols=("BTC-USD",),
        orphan_earlier_orders=False,
    )
    assert orphaned == 0
    assert (await states()) == {"coid_live_resting": "acknowledged", "coid_paper_resting": "acknowledged"}

    paper_runtime = _StubRuntime("run_paper_new")
    orphaned = await state._start_session_with_run_row(
        paper_runtime, mode="paper-live", scenario="realtime", initial_capital=10_000.0, seed=1, symbols=("BTC-USD",),
        orphan_earlier_orders=True,
    )
    assert orphaned == 1, "only the earlier paper order: the live one is the venue's"
    assert (await states()) == {"coid_live_resting": "acknowledged", "coid_paper_resting": "cancelled"}
    await state.database.close()


async def test_the_live_arming_path_goes_through_the_shared_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With the gate and the venue builder replaced (nothing here can reach Binance), the
    arming path must write the run row before it starts the runtime and stamp it when the
    start fails — the same contract the paper path has had since 1.2."""
    from pydantic import SecretStr

    from tia.core.config import LiveConfig
    from tia.live import gate as gate_module

    live = LiveConfig(enabled=True, max_live_capital=500.0, binance_api_key=SecretStr("k"), binance_api_secret=SecretStr("s"))
    state = AppState(_settings(tmp_path, live=live))
    await state.database.ensure_schema()

    class _Report:
        failures: ClassVar[list[Any]] = []

        def as_dict(self) -> dict[str, Any]:
            return {"passed": True}

    class _Token:
        report = _Report()

        def as_dict(self) -> dict[str, Any]:
            return {"fingerprint": "test"}

    monkeypatch.setattr(gate_module.LiveActivationGate, "arm", lambda self, *a, **k: _Token())
    monkeypatch.setattr(state, "_gate_inputs", _async_empty)
    monkeypatch.setattr("tia.api.gate_probes.build_probes", lambda *a, **k: {})
    monkeypatch.setattr("tia.api.state._hash_token", lambda token: "hashed", raising=False)

    stub = _StubRuntime("run_live_armed", fail=LiveActivationError("clock skew 2400 ms"), state=state)

    async def build(token: Any) -> Any:
        return stub

    monkeypatch.setattr(state, "_build_live_runtime", build)
    with pytest.raises(LiveActivationError):
        await state._arm_live_locked(operator="operator", confirmation="x")
    assert stub.row_seen_at_start is True, "the row existed when the runtime was asked to start"
    rows = await _rows(state)
    assert [(r[0], r[1]) for r in rows] == [("run_live_armed", "live")]
    assert rows[0][3] is not None and "start_failed" in (rows[0][2] or "")
    assert state.live_runtime is None
    await state.database.close()


async def _async_empty() -> dict[str, Any]:
    return {}
