"""Order hygiene of the backtest engine under rejections and partial fills (D1-D3).

The other backtest tests switch rejections and partial fills off, which is exactly where
the three defects found on real data (E1, 2026-10-19) hid:

* D1 — an exit or a protective stop retried after a rejection or a cancel reused its
  client id and was suppressed as a duplicate: the position kept no stop, or never closed.
* D2 — break-even and trailing moved the leg's stop but not the order in the book.
* D3 — the remainder of a partially filled entry, still resting when the close was sent,
  filled while it was in flight: the close covered only the old size, the rest of the
  position stayed open, and the leg waited forever for a close that had already finished.

Each test drives the engine through an instrumented subclass that checks, after every
bar, the invariant the defect broke. Where the fix has several layers (D1 for exits and
for stops; D3 on the close, when flat, and as a safety net) each layer has a scenario that
only that layer handles, so removing any one of them fails a test on behaviour, not on a
counter. The live session (``tia.runtime.live``) already behaves this way; these tests
hold the backtest to the same rules.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import ClassVar

import pytest

import tia.backtest.engine as engine_module
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.enums import OrderState, OrderType
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.market import Candle
from tia.execution.paper import PaperExecutionProvider
from tia.execution.state_machine import transition

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
SERIES: list[Candle] = asyncio.run(
    CsvReplayProvider(FIXTURES).get_candles("BTC-USD", "1h", limit=700)
)
MAX_BARS_UNPROTECTED = 8  # with a 20 % rejection rate, 8 rejections in a row is ~3e-6
TIME_STOP_BARS = 6


class _Instrumented(BacktestEngine):
    """The engine with its per-bar invariants checked from the outside."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.violations: dict[str, list[str]] = {
            "d1_stop": [], "d1_exit": [], "d2": [], "d3": [], "d3_stuck": [], "d3_added": [], "d3_reopened": [],
        }
        self.unprotected_streak = 0
        self.exit_requested_at: dict[str, int] = {}
        self.size_when_close_requested: dict[str, float] = {}
        self.closed_signals: set[str] = set()
        self.previous_signal: str | None = None
        self.bar = 0

    def _request_exit(self, provider, leg, reason, stop_order_id, candle, counts):  # type: ignore[no-untyped-def]
        self.exit_requested_at.setdefault(leg.signal_id, self.bar)
        self.size_when_close_requested.setdefault(leg.signal_id, leg.quantity)
        return super()._request_exit(provider, leg, reason, stop_order_id, candle, counts)

    def _sync_protective_stop(self, provider, leg, current_id, counts, **kwargs):  # type: ignore[no-untyped-def]
        self.bar += 1
        # D3 on the close, seen before the engine reacts: a close that filled in full and
        # left position means something was added to the position while it was in flight.
        if leg is not None and leg.exit_pending is not None and leg.exit_order_id:
            close = asyncio.run(provider.get_order(leg.exit_order_id))
            if close is not None and close.state is OrderState.FILLED and leg.quantity > 0:
                self.violations["d3_added"].append(
                    f"bar {self.bar}: the close filled in full and {leg.quantity} is still held"
                )
        stop_id = super()._sync_protective_stop(provider, leg, current_id, counts, **kwargs)
        symbol = leg.symbol if leg is not None else SERIES[0].symbol
        position = provider.portfolio.positions.get(symbol)
        held = 0.0 if position is None or position.is_flat else abs(position.quantity)
        expected = 0.0 if leg is None else leg.quantity
        if abs(held - expected) > max(expected * 1e-6, 1e-9):
            self.violations["d3"].append(f"bar {self.bar}: venue holds {held}, engine tracks {expected}")
        if leg is not None and leg.exit_pending is not None and leg.exit_order_id:
            close = asyncio.run(provider.get_order(leg.exit_order_id))
            if close is not None and close.state.is_terminal:
                self.violations["d3_stuck"].append(
                    f"bar {self.bar}: {leg.quantity} still held, waiting on a close that is {close.state.value}"
                )
        # D3 on the close: once a close is asked for, nothing may add to the position.
        if leg is not None and leg.signal_id in self.size_when_close_requested:
            asked = self.size_when_close_requested[leg.signal_id]
            if leg.quantity > asked * (1 + 1e-9) + 1e-12:
                self.violations["d3_added"].append(f"bar {self.bar}: {leg.signal_id} grew from {asked} to {leg.quantity}")
        # D3 when flat: a signal whose position closed never opens again.
        if leg is None and self.previous_signal is not None:
            self.closed_signals.add(self.previous_signal)
        if leg is not None and (leg.signal_id in self.closed_signals or not leg.signal_id):
            self.violations["d3_reopened"].append(f"bar {self.bar}: position for {leg.signal_id!r} after it closed")
        self.previous_signal = leg.signal_id if leg is not None else None
        if leg is not None and leg.stop_price is not None and leg.exit_pending is None:
            order = asyncio.run(provider.get_order(stop_id)) if stop_id else None
            if order is None or order.state.is_terminal:
                self.unprotected_streak += 1
                if self.unprotected_streak > MAX_BARS_UNPROTECTED:
                    self.violations["d1_stop"].append(f"bar {self.bar}: {self.unprotected_streak} bars without a stop")
            else:
                self.unprotected_streak = 0
                if abs(float(order.stop_price or 0.0) - float(leg.stop_price)) > 1e-9 * float(leg.stop_price):
                    self.violations["d2"].append(
                        f"bar {self.bar}: leg stop {leg.stop_price}, order in the book {order.stop_price}"
                    )
        else:
            self.unprotected_streak = 0
        open_ids = {leg.signal_id} if leg is not None else set()
        for signal_id, since in self.exit_requested_at.items():
            if signal_id in open_ids and self.bar - since > MAX_BARS_UNPROTECTED:
                self.violations["d1_exit"].append(f"{signal_id}: exit asked at bar {since}, still open at {self.bar}")
        return stop_id


class _RejectsFirstClose(PaperExecutionProvider):
    """A venue that rejects the first attempt of every close (one per exit reason and leg)."""

    rejected: ClassVar[set[str]] = set()  # reset by the test; shared because the engine builds the provider

    def _should_reject(self, order):  # type: ignore[no-untyped-def]
        if order.reduce_only and order.order_type is OrderType.MARKET and order.signal_id not in self.rejected:
            self.rejected.add(order.signal_id)
            return True
        return super()._should_reject(order)


class _ImmediateOrCancelCloses(PaperExecutionProvider):
    """A venue whose closes are immediate-or-cancel: whatever does not fill at once expires."""

    def _try_fill(self, order, candle):  # type: ignore[no-untyped-def]
        fill = super()._try_fill(order, candle)
        if order.reduce_only and order.order_type is OrderType.MARKET and not order.state.is_terminal:
            transition(order, OrderState.EXPIRED, at=candle.close_time, reason="immediate-or-cancel: the rest expired")
        return fill


class _StopLevelsStripped(_Instrumented):
    """Every leg loses its stop level before the engine syncs the protective stop."""

    def _sync_protective_stop(self, provider, leg, current_id, counts, **kwargs):  # type: ignore[no-untyped-def]
        if leg is not None:
            leg.stop_price = None
        return super()._sync_protective_stop(provider, leg, current_id, counts, **kwargs)


def _run(*, reject: float, partial: float, engine: type[_Instrumented] = _Instrumented, **config: object) -> _Instrumented:
    instrumented = engine(
        BacktestConfig(
            dataset="fixtures",
            timeframe="1h",
            warmup_bars=120,
            execution=ExecutionSimConfig(reject_probability=reject, partial_fill_probability=partial),
            **config,
        ),
        DEFAULT_UNIVERSE,
    )
    instrumented.result = instrumented.run(SERIES)  # type: ignore[attr-defined]
    return instrumented


def test_stops_and_exits_survive_rejections() -> None:
    """D1: a rejected stop or exit is retried under a fresh id and goes through."""
    engine = _run(reject=0.2, partial=0.0)
    assert engine.exit_requested_at, "the scenario must exercise exits"
    assert not engine.violations["d1_stop"], engine.violations["d1_stop"][:3]
    assert not engine.violations["d1_exit"], engine.violations["d1_exit"][:3]


def test_a_rejected_close_is_sent_again_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    """D1 for exits: after a rejection the same close is asked for again on the next bar
    under a new client id. With the old id the retry was suppressed as a duplicate of the
    rejected order and the time stop never executed."""
    monkeypatch.setattr(engine_module, "PaperExecutionProvider", _RejectsFirstClose)
    monkeypatch.setattr(_RejectsFirstClose, "rejected", set())
    engine = _run(reject=0.0, partial=0.0, max_holding_bars=TIME_STOP_BARS)
    assert any(key.startswith("exit:time-stop:") for key in _RejectsFirstClose.rejected), "no time stop was rejected"
    trades = engine.result.trades  # type: ignore[attr-defined]
    timed = [t for t in trades if t.exit_reason == "time stop"]
    assert timed, "no rejected time stop was ever sent again: the retry was suppressed as a duplicate"
    late = [t for t in trades if t.bars_held > TIME_STOP_BARS + 2]
    assert not late, [(t.signal_id, t.bars_held, t.exit_reason) for t in late[:3]]


def test_the_stop_in_the_book_follows_the_leg() -> None:
    """D2: break-even and trailing move the order, not only the leg's record."""
    engine = _run(reject=0.0, partial=0.0)
    assert not engine.violations["d2"], engine.violations["d2"][:3]


def test_partial_fills_leave_no_untracked_or_stuck_position() -> None:
    """D3: what the venue holds is always the leg the engine tracks, or nothing; nothing is
    added to a position once its close is asked for; a closed signal never reopens; and a
    close goes through even when the rest of the entry was still resting."""
    engine = _run(reject=0.0, partial=0.9)
    for invariant in ("d3", "d3_stuck", "d3_added", "d3_reopened"):
        assert not engine.violations[invariant], (invariant, engine.violations[invariant][:3])
    assert engine.exit_requested_at, "the scenario must exercise closes"


def test_a_close_that_leaves_position_is_released_and_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """D3 safety net: when a close ends (here: immediate-or-cancel) with position left, the
    leg is released, its stop re-placed and the close asked for again, instead of waiting
    forever on an order that has already finished."""
    monkeypatch.setattr(engine_module, "PaperExecutionProvider", _ImmediateOrCancelCloses)
    engine = _run(reject=0.0, partial=0.9, max_holding_bars=TIME_STOP_BARS)
    for invariant in ("d3", "d3_stuck", "d3_added", "d3_reopened"):
        assert not engine.violations[invariant], (invariant, engine.violations[invariant][:3])
    trades = engine.result.trades  # type: ignore[attr-defined]
    assert any(t.exit_reason == "time stop" for t in trades), "the scenario must close on the time stop"
    assert engine.order_hygiene["exits_done_with_position_left"], "the scenario must end closes with position left"


def test_a_leg_without_a_stop_level_is_reported() -> None:
    """Fail loud: bars spent holding a position with no stop level become a caveat, and the
    result stops claiming to be reliable."""
    engine = _run(reject=0.0, partial=0.0, engine=_StopLevelsStripped)
    result = engine.result  # type: ignore[attr-defined]
    assert result.trades, "the scenario must hold positions"
    assert any("no stop level" in w for w in result.warnings), result.warnings
    assert not result.is_reliable
