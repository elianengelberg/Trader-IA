"""P0 — safety invariants of the protective stop in ``LiveRuntime`` (real paper engine; failures
injected at the execution boundary exactly as the Binance adapter raises them; no network).

Invariants under test:
* a position is never declared protected because a stop was *requested*: only a working order the
  venue acknowledged counts, and the state says which one;
* a protection failure is never swallowed: it is counted, recorded as an incident with the order's
  correlation ids, blocks new entries and halts new orders (an operator must resume);
* an unknown outcome stays UNKNOWN (no second stop on top of one that may rest) until the venue is
  asked; a retry reuses the same client order id;
* a restart that finds an order nobody tracks does not place a second stop over it;
* entries that need a stop are refused when the venue cannot hold one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.test_account_restore import (
    _db,
    build,
    open_position,
    persister,
    rebuild,
    register_run,
    settle,
)
from tests.integration.test_paper_cancellations import working
from tia.core.errors import (
    ExecutionError,
    OrderRejectedError,
    ProviderUnavailableError,
    ReconciliationError,
)
from tia.domain.enums import OrderState, OrderType
from tia.execution.state_machine import transition
from tia.runtime.states import LiveState


def recorder() -> tuple[list[tuple[str, Any]], Any]:
    saved: list[tuple[str, Any]] = []
    return saved, (lambda kind, payload: saved.append((kind, payload)))


def incidents(saved: list[tuple[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [p for k, p in saved if k == "incident" and p.get("kind") == kind]


def status(runtime: Any) -> str | None:
    report = getattr(runtime, "protection_status", None)
    return report.get("status") if isinstance(report, dict) else None


def fail_stops(monkeypatch: pytest.MonkeyPatch, execution: Any, error: Exception | None, *, times: int = 10_000) -> list[Any]:
    """Make the next ``times`` STOP submissions fail with ``error`` (or come back rejected when
    ``error`` is None). Returns the list of STOP intents seen."""
    real = execution.submit_order
    seen: list[Any] = []
    left = {"n": times}

    async def submit(intent):  # type: ignore[no-untyped-def]
        if intent.order_type is OrderType.STOP and left["n"] > 0:
            seen.append(intent)
            left["n"] -= 1
            if error is not None:
                raise error
            order = await real(intent)
            transition(order, OrderState.CANCEL_REQUESTED, at=order.updated_at)
            transition(order, OrderState.CANCELLED, at=order.updated_at, reason="venue rejected")
            order.reject_reason = "venue rejected"
            if order.order_id in execution._resting:
                execution._resting.remove(order.order_id)
            return order
        if intent.order_type is OrderType.STOP:
            seen.append(intent)
        return await real(intent)

    monkeypatch.setattr(execution, "submit_order", submit)
    return seen


# ------------------------------------------------------- definite refusal (#2, #5, the old adapter)
@pytest.mark.parametrize("error", [
    OrderRejectedError("binance rejected /api/v3/order: HTTP 400 code=-1013 Stop loss orders are not supported for this symbol.", code=-1013),
    ExecutionError("order type stop is not supported by this adapter; it is not in the documented spot order-type set"),
    None,  # the venue answers with a terminal, unfilled order
], ids=["venue_rejects", "adapter_refuses", "terminal_unfilled"])
async def test_a_refused_protective_stop_is_an_emergency_not_a_warning(monkeypatch: pytest.MonkeyPatch, error: Any) -> None:
    saved, persist = recorder()
    runtime, execution, market, _ = build(persist=persist)
    await runtime.start()
    try:
        seen = fail_stops(monkeypatch, execution, error)
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        assert seen, "the runtime tried to protect the position"
        assert await working(execution, OrderType.STOP) == []
        assert "protection_failed" in runtime.entry_blocks, runtime.entry_blocks
        assert runtime.machine.state is LiveState.HALT_NEW_ORDERS, "new exposure stops; an operator resumes"
        [incident] = incidents(saved, "protection_failed")[:1] or [None]
        assert incident is not None and seen[0].client_order_id in str(incident), "correlatable record"
        assert runtime.counters.get("protection_failures", 0) >= 1
        assert status(runtime) == "failed"
        assert runtime._open_trade is not None, "the position is not closed behind anyone's back"
    finally:
        await runtime.stop()


# ------------------------------------------------- unknown outcome (#3 network, #4 timeout, #11 retry)
@pytest.mark.parametrize("error", [
    ReconciliationError("POST /api/v3/order timed out; the order state at the venue is UNKNOWN"),
    ProviderUnavailableError("binance transport error on POST /api/v3/order: reset", provider="binance-spot-testnet"),
], ids=["timeout", "transport"])
async def test_an_unknown_stop_outcome_stays_unknown_and_is_resolved_before_any_resend(
    monkeypatch: pytest.MonkeyPatch, error: Exception,
) -> None:
    saved, persist = recorder()
    runtime, execution, market, _ = build(persist=persist)
    await runtime.start()
    try:
        await open_position(runtime, market)
        seen = fail_stops(monkeypatch, execution, error, times=1)
        asked: list[str] = []

        async def resolve(*, symbol: str, client_order_id: str):  # type: ignore[no-untyped-def]
            asked.append(client_order_id)
            return  # the venue confirms it never arrived

        monkeypatch.setattr(execution, "resolve_unknown_order", resolve, raising=False)
        market.advance()
        await runtime._cycle_once()
        assert status(runtime) == "unknown"
        assert "protection_unverified" in runtime.entry_blocks
        assert runtime.machine.state is LiveState.HALT_NEW_ORDERS
        assert incidents(saved, "protection_unknown")
        market.advance()
        await runtime._cycle_once()
        assert asked == [seen[0].client_order_id], "the venue is asked by the same id before anything is resent"
        stops = await working(execution, OrderType.STOP)
        assert len(stops) == 1 and stops[0].client_order_id == seen[0].client_order_id, "retry reuses the id"
        assert status(runtime) == "confirmed" and "protection_unverified" not in runtime.entry_blocks
    finally:
        await runtime.stop()


async def test_an_unknown_stop_the_venue_does_hold_is_adopted_not_duplicated(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, execution, market, _ = build(persist=recorder()[1])
    await runtime.start()
    try:
        await open_position(runtime, market)
        real = execution.submit_order
        held: dict[str, Any] = {}

        async def submit_then_time_out(intent):  # type: ignore[no-untyped-def]
            if intent.order_type is OrderType.STOP and not held:
                held["order"] = await real(intent)  # the venue took it; the answer was lost
                raise ReconciliationError("timed out; state UNKNOWN")
            return await real(intent)

        async def resolve(*, symbol: str, client_order_id: str):  # type: ignore[no-untyped-def]
            return held["order"] if held["order"].client_order_id == client_order_id else None

        monkeypatch.setattr(execution, "submit_order", submit_then_time_out)
        monkeypatch.setattr(execution, "resolve_unknown_order", resolve, raising=False)
        market.advance()
        await runtime._cycle_once()
        assert status(runtime) == "unknown" and len(await working(execution, OrderType.STOP)) == 1
        market.advance()
        await runtime._cycle_once()
        assert len(await working(execution, OrderType.STOP)) == 1, "no second stop on top of the one that rests"
        assert status(runtime) == "confirmed" and runtime._protective["order_id"] == held["order"].order_id
    finally:
        await runtime.stop()


# ------------------------------------------------------------ the status read fails (#7)
async def test_a_failed_read_of_the_stop_makes_protection_unknown_and_places_nothing_on_top(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, execution, market, _ = build(persist=recorder()[1])
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        assert status(runtime) in (None, "confirmed") and len(await working(execution, OrderType.STOP)) == 1
        real_get = execution.get_order

        async def broken(order_id):  # type: ignore[no-untyped-def]
            raise ProviderUnavailableError("read failed", provider="paper")

        monkeypatch.setattr(execution, "get_order", broken)
        market.advance()
        await runtime._cycle_once()
        assert len(await working(execution, OrderType.STOP)) == 1
        assert "protection_unverified" in runtime.entry_blocks and status(runtime) == "unknown"
        monkeypatch.setattr(execution, "get_order", real_get)
        market.advance()
        await runtime._cycle_once()
        assert status(runtime) == "confirmed" and "protection_unverified" not in runtime.entry_blocks
    finally:
        await runtime.stop()


# ---------------------------------------- acknowledged, then unknown to the venue (#6)
async def test_a_stop_the_venue_stops_knowing_is_unknown_until_given_up_then_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, execution, market, _ = build(persist=recorder()[1])
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        [stop] = await working(execution, OrderType.STOP)
        real_get = execution.get_order

        async def forgets(order_id):  # type: ignore[no-untyped-def]
            if order_id in (stop.order_id, stop.client_order_id):
                return None
            return await real_get(order_id)

        monkeypatch.setattr(execution, "get_order", forgets)
        market.advance()
        await runtime._cycle_once()
        assert status(runtime) == "unknown"
        assert runtime.entry_blocks, "entries wait while the stop's fate is unknown"
    finally:
        await runtime.stop()


# ------------------------------------- restart with a stop nobody tracks (#8)
async def test_a_restart_does_not_place_a_second_stop_over_an_untracked_one(tmp_path: Path) -> None:
    db = _db(tmp_path)
    await db.create_schema()
    try:
        runtime_a, engine, market, clock = build(persist=persister(db))
        await register_run(db, runtime_a.run_id)
        await runtime_a.start()
        await open_position(runtime_a, market)
        market.advance()
        await runtime_a._cycle_once()
        assert len(await working(engine, OrderType.STOP)) == 1
        await settle(runtime_a)
        runtime_a._task.cancel() if runtime_a._task else None  # the process dies: no orderly stop
        await settle()
        restore = await rebuild(db)
        assert restore.complete and restore.has_position
        # The new process talks to the same venue, where the dead session's stop still rests.
        runtime_b, _, _, _ = build(persist=persister(db), account=restore, engine=engine, clock=clock, market=market)
        await register_run(db, runtime_b.run_id)
        await runtime_b.start()
        try:
            market.advance()
            await runtime_b._cycle_once()
            assert len(await working(engine, OrderType.STOP)) == 1, "no second stop on top of the dead session's"
            assert status(runtime_b) == "unknown"
            assert "protection_unverified" in runtime_b.entry_blocks
        finally:
            await runtime_b.stop()
    finally:
        await db.close()


# ---------------------------------------------- closing while protection fails (#9)
async def test_a_close_while_protection_fails_is_sent_and_never_claims_protection(monkeypatch: pytest.MonkeyPatch) -> None:
    _saved, persist = recorder()
    runtime, execution, market, _ = build(persist=persist)
    await runtime.start()
    try:
        fail_stops(monkeypatch, execution, OrderRejectedError("rejected", code=-1013))
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        assert status(runtime) == "failed"
        assert await runtime._close_position("time stop") is True
        market.advance()
        await runtime._cycle_once()
        assert runtime._open_trade is None and await execution.get_positions() == {}
        assert status(runtime) == "none" and "protection_failed" not in runtime.entry_blocks
        assert runtime.machine.state is LiveState.HALT_NEW_ORDERS, "still an operator's call to resume"
    finally:
        await runtime.stop()


# ---------------------------------------------- replacing a stop (#12)
async def test_a_replacement_that_cannot_be_placed_after_the_cancel_is_an_emergency(monkeypatch: pytest.MonkeyPatch) -> None:
    saved, persist = recorder()
    runtime, execution, market, _ = build(persist=persist)
    await runtime.start()
    try:
        await open_position(runtime, market)
        market.advance()
        await runtime._cycle_once()
        assert len(await working(execution, OrderType.STOP)) == 1
        fail_stops(monkeypatch, execution, OrderRejectedError("rejected", code=-1013))
        runtime._planned_exit["stop"] = float(runtime._planned_exit["stop"]) * 1.001  # a tightened level
        market.advance()
        await runtime._cycle_once()
        assert await working(execution, OrderType.STOP) == [], "the old stop was cancelled, the new one refused"
        assert status(runtime) == "failed" and "protection_failed" in runtime.entry_blocks
        assert incidents(saved, "protection_failed")
    finally:
        await runtime.stop()


# --------------------------------------- no entry that needs a stop the venue cannot hold
async def test_entries_needing_a_stop_are_refused_when_the_venue_cannot_hold_stops() -> None:
    runtime, execution, market, _ = build(persist=recorder()[1])
    execution._capabilities = execution.capabilities.model_copy(update={"supports_stop_orders": False})
    await runtime.start()
    try:
        with pytest.raises(AssertionError, match="no position was opened"):
            await open_position(runtime, market)
        assert runtime.counters.get("protection_unavailable_rejected", 0) > 0
    finally:
        await runtime.stop()
