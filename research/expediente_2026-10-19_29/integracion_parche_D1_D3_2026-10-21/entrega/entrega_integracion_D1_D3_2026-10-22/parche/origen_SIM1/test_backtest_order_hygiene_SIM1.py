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
bar, the invariant the defect broke. The live session (``tia.runtime.live``) already
behaves this way; these tests hold the backtest to the same rules.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.market import Candle

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
SERIES: list[Candle] = asyncio.run(
    CsvReplayProvider(FIXTURES).get_candles("BTC-USD", "1h", limit=700)
)
MAX_BARS_UNPROTECTED = 8  # with a 20 % rejection rate, 8 rejections in a row is ~3e-6


class _Instrumented(BacktestEngine):
    """The engine with its per-bar invariants checked from the outside."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.violations: dict[str, list[str]] = {"d1_stop": [], "d1_exit": [], "d2": [], "d3": [], "d3_stuck": []}
        self.unprotected_streak = 0
        self.exit_requested_at: dict[str, int] = {}
        self.bar = 0

    def _request_exit(self, provider, leg, reason, stop_order_id, candle, counts):  # type: ignore[no-untyped-def]
        self.exit_requested_at.setdefault(leg.signal_id, self.bar)
        return super()._request_exit(provider, leg, reason, stop_order_id, candle, counts)

    def _sync_protective_stop(self, provider, leg, current_id, counts, **kwargs):  # type: ignore[no-untyped-def]
        self.bar += 1
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


def _run(*, reject: float, partial: float) -> _Instrumented:
    engine = _Instrumented(
        BacktestConfig(
            dataset="fixtures",
            timeframe="1h",
            warmup_bars=120,
            execution=ExecutionSimConfig(reject_probability=reject, partial_fill_probability=partial),
        ),
        DEFAULT_UNIVERSE,
    )
    engine.run(SERIES)
    return engine


def test_stops_and_exits_survive_rejections() -> None:
    """D1: a rejected stop or exit is retried under a fresh id and goes through."""
    engine = _run(reject=0.2, partial=0.0)
    assert engine.exit_requested_at, "the scenario must exercise exits"
    assert not engine.violations["d1_stop"], engine.violations["d1_stop"][:3]
    assert not engine.violations["d1_exit"], engine.violations["d1_exit"][:3]


def test_the_stop_in_the_book_follows_the_leg() -> None:
    """D2: break-even and trailing move the order, not only the leg's record."""
    engine = _run(reject=0.0, partial=0.0)
    assert not engine.violations["d2"], engine.violations["d2"][:3]


def test_partial_fills_leave_no_untracked_or_stuck_position() -> None:
    """D3: what the venue holds is always the leg the engine tracks, or nothing, and a
    close goes through even when the rest of the entry was still resting."""
    engine = _run(reject=0.0, partial=0.9)
    assert not engine.violations["d3"], engine.violations["d3"][:3]
    assert not engine.violations["d3_stuck"], engine.violations["d3_stuck"][:3]
    assert engine.order_hygiene["entry_remainders_cancelled_on_exit"], "the scenario must leave entry remainders resting"


def test_a_leg_without_a_stop_level_is_reported() -> None:
    """Fail loud: bars spent holding a position with no stop level become a caveat."""
    engine = _run(reject=0.0, partial=0.0)
    assert "bars_with_leg_and_no_stop" in engine.order_hygiene
