"""R18 — an exit that does not happen must not leave the position without its stop, and the record
must say what is true (real paper engine; venue answers injected at the execution boundary).

``_close_position`` cancels the protective stop before it sends the exit (spot has no reduce-only
stop to leave in place). Before the fix, a rejected exit left the position with no stop until the
next closed bar while the incident said "the position remains and keeps its protection".
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.test_account_restore import build, open_position
from tests.integration.test_exit_guard import _book
from tests.integration.test_paper_cancellations import working
from tia.core.errors import OrderRejectedError, ReconciliationError
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


async def protected_position(saved_persist: Any = None):  # type: ignore[no-untyped-def]
    runtime, execution, market, clock = build(persist=saved_persist)
    await runtime.start()
    await open_position(runtime, market)
    market.advance()
    await runtime._cycle_once()
    assert len(await working(execution, OrderType.STOP)) == 1
    return runtime, execution, market, clock


def exits_answer(monkeypatch: pytest.MonkeyPatch, execution: Any, how: str, *, times: int = 1) -> list[Any]:
    """The next ``times`` MARKET exits: 'reject' (terminal, unfilled), 'raise' (an error), 'timeout'."""
    real = execution.submit_order
    seen: list[Any] = []
    left = {"n": times}

    async def submit(intent):  # type: ignore[no-untyped-def]
        if intent.order_type is OrderType.MARKET and intent.signal_id.startswith("exit:") and left["n"] > 0:
            left["n"] -= 1
            seen.append(intent)
            if how == "raise":
                raise OrderRejectedError("binance rejected /api/v3/order: HTTP 400 code=-2010 insufficient balance", code=-2010)
            if how == "timeout":
                raise ReconciliationError("POST /api/v3/order timed out; the order state at the venue is UNKNOWN")
            order = await real(intent)
            transition(order, OrderState.CANCEL_REQUESTED, at=order.updated_at)
            transition(order, OrderState.CANCELLED, at=order.updated_at, reason="simulated venue rejection")
            order.reject_reason = "simulated venue rejection"
            if order.order_id in execution._resting:
                execution._resting.remove(order.order_id)
            return order
        return await real(intent)

    monkeypatch.setattr(execution, "submit_order", submit)
    return seen


@pytest.mark.parametrize("reason", ["signal reversed", "time stop"])
async def test_a_rejected_exit_is_re_protected_at_once_and_the_record_says_so(monkeypatch: pytest.MonkeyPatch, reason: str) -> None:
    saved, persist = recorder()
    runtime, execution, _market, _ = await protected_position(persist)
    try:
        seen = exits_answer(monkeypatch, execution, "reject")
        assert await runtime._close_position(reason) is True
        assert runtime.counters["exits_rejected"] == 1
        qty, _ = await _book(execution)
        assert qty != 0.0, "the position is still there"
        assert len(await working(execution, OrderType.STOP)) == 1, "protected again before the next bar"
        assert status(runtime) == "confirmed"
        [incident] = incidents(saved, "exit_rejected")
        assert "keeps its protection" not in incident["reason"]
        assert seen[0].client_order_id in str(incident), "the exit is named"
        assert "confirmed" in incident["reason"]
    finally:
        await runtime.stop()


async def test_an_exit_that_raises_is_re_protected_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    saved, persist = recorder()
    runtime, execution, _market, _ = await protected_position(persist)
    try:
        exits_answer(monkeypatch, execution, "raise")
        assert await runtime._close_position("signal reversed") is False
        assert len(await working(execution, OrderType.STOP)) == 1
        assert status(runtime) == "confirmed"
        assert incidents(saved, "exit_submit_failed")
    finally:
        await runtime.stop()


async def test_an_exit_that_timed_out_and_never_arrived_is_re_protected_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    saved, persist = recorder()
    runtime, execution, _market, _ = await protected_position(persist)
    try:
        exits_answer(monkeypatch, execution, "timeout")

        async def absent(*, symbol: str, client_order_id: str):  # type: ignore[no-untyped-def]
            return None

        monkeypatch.setattr(execution, "resolve_unknown_order", absent, raising=False)
        assert await runtime._close_position("time stop") is False
        assert len(await working(execution, OrderType.STOP)) == 1
        assert status(runtime) == "confirmed"
        assert incidents(saved, "exit_not_accepted")
    finally:
        await runtime.stop()


async def test_an_exit_whose_outcome_cannot_be_resolved_is_unknown_until_the_venue_position_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps the existing contract of ``test_exit_guard`` (the venue's position read is what
    answers an unresolvable MARKET exit) and adds what R18 asks: the record says the
    protection is UNKNOWN in the gap, nothing claims it, and exactly one stop comes back."""
    saved, persist = recorder()
    runtime, execution, market, _ = await protected_position(persist)
    try:
        exits_answer(monkeypatch, execution, "timeout")

        async def cannot(*, symbol: str, client_order_id: str):  # type: ignore[no-untyped-def]
            raise ReconciliationError("the venue cannot be asked right now")

        monkeypatch.setattr(execution, "resolve_unknown_order", cannot, raising=False)
        await runtime._close_position("time stop")
        assert status(runtime) == "unknown" and runtime.machine.state is LiveState.HALT_NEW_ORDERS
        assert {"position_unverified", "protection_unverified"} <= set(runtime.entry_blocks)
        assert await working(execution, OrderType.STOP) == [], "nothing placed in the same cycle"
        assert incidents(saved, "protection_unknown")
        assert not any("keeps its protection" in str(p) for _k, p in saved)
        monkeypatch.undo()
        market.advance()
        await runtime._cycle_once()  # the venue still holds the leg: the exit did not execute
        assert len(await working(execution, OrderType.STOP)) == 1, "one stop, not two"
        assert status(runtime) == "confirmed"
        assert not {"position_unverified", "protection_unverified"} & set(runtime.entry_blocks)
    finally:
        await runtime.stop()


async def test_a_partially_filled_exit_that_ends_leaves_one_stop_sized_to_what_remains() -> None:
    saved, persist = recorder()
    runtime, execution, market, _ = await protected_position(persist)
    try:
        held = (await execution.get_positions())["BTC-USD"].quantity
        volume = market._candles[market.cursor].volume
        execution._config = execution._config.model_copy(
            update={"max_participation_rate": max(1e-6, abs(held) * 0.4 / max(volume, 1e-9))}
        )
        assert await runtime._close_position("time stop") is True
        runtime.halt_new_orders(reason="test: no fresh entries")
        pending_id = runtime._pending_exit["order_id"]
        market.advance()
        await runtime._cycle_once()  # a partial fill
        await execution.cancel_order(pending_id)  # the venue ends the exit with quantity left
        market.advance()
        await runtime._cycle_once()
        remaining = abs((await execution.get_positions())["BTC-USD"].quantity)
        stops = await working(execution, OrderType.STOP)
        assert 0 < remaining < abs(held)
        assert len(stops) == 1 and stops[0].quantity == pytest.approx(remaining)
        assert status(runtime) == "confirmed"
        assert incidents(saved, "exit_unfilled")
    finally:
        await runtime.stop()


async def test_two_exit_triggers_send_one_exit() -> None:
    runtime, execution, _market, _ = await protected_position(recorder()[1])
    try:
        assert await runtime._close_position("time stop") is True
        assert await runtime._close_position("signal reversed") is False
        exits = [o for o in await execution.get_orders() if o.signal_id.startswith("exit:")]
        assert len(exits) == 1
        assert status(runtime) == "released_for_exit", "the stop was cancelled on purpose; nothing claims protection"
    finally:
        await runtime.stop()


async def test_a_rejected_exit_whose_re_protection_also_fails_is_an_emergency(monkeypatch: pytest.MonkeyPatch) -> None:
    saved, persist = recorder()
    runtime, execution, _market, _ = await protected_position(persist)
    try:
        real = execution.submit_order

        async def everything_refused(intent):  # type: ignore[no-untyped-def]
            if intent.signal_id.startswith(("exit:", "protective:")):
                raise OrderRejectedError("refused", code=-2010)
            return await real(intent)

        monkeypatch.setattr(execution, "submit_order", everything_refused)
        await runtime._close_position("signal reversed")
        assert await working(execution, OrderType.STOP) == []
        assert status(runtime) == "failed" and "protection_failed" in runtime.entry_blocks
        assert runtime.machine.state is LiveState.HALT_NEW_ORDERS
        assert incidents(saved, "protection_failed")
        [incident] = incidents(saved, "exit_submit_failed")
        assert "failed" in incident["reason"]
    finally:
        await runtime.stop()
