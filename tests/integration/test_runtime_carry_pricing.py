"""How the 24/7 session prices the carry in its expected value (Phase 1.3, Etapa Dos).

With a time stop the holding horizon is bounded, and the eight-hour settlements it may
cross are priced at the monitor's funding rate — paid when paid, never credited. Without
a reading nothing is priced *and the omission is counted*: the session's own accrual
charges nothing for a period it has no rate for, so the gate subtracts the cost the
simulator will charge, no more and no less. Without a time stop no horizon is claimed.
"""

from __future__ import annotations

from typing import Any

from tests.integration.test_live_runtime import _seed_every_bucket
from tests.integration.test_paper_cancellations import build
from tia.domain.enums import Direction
from tia.economics.costs import TradeCosts


def _record_estimates(runtime) -> list[tuple[dict[str, Any], TradeCosts]]:  # type: ignore[no-untyped-def]
    calls: list[tuple[dict[str, Any], TradeCosts]] = []
    real = runtime._costs.estimate

    def recording(**kwargs: Any) -> TradeCosts:
        costs = real(**kwargs)
        calls.append((kwargs, costs))
        return costs

    runtime._costs.estimate = recording  # type: ignore[method-assign]
    return calls


async def _drive_to_first_order(runtime, market, bars: int = 400) -> None:  # type: ignore[no-untyped-def]
    _seed_every_bucket(runtime)
    for _ in range(bars):
        market.advance()
        await runtime._cycle_once()
        if runtime.counters["orders"] >= 1:
            return
    raise AssertionError("no order was ever sent")


async def test_a_bounded_horizon_with_a_reading_prices_one_settlement_per_eight_hours() -> None:
    """Twelve one-minute bars cross at most one settlement: one period at +0.0001 is
    1 bps on a long and nothing on a short (a payment it would receive)."""
    runtime, _execution, market, _clock = build(max_holding_bars=12, charge_funding=True)
    runtime._funding_rate = lambda: 0.0001
    calls = _record_estimates(runtime)
    await runtime.start()
    try:
        await _drive_to_first_order(runtime, market)
    finally:
        await runtime.stop()
    assert calls
    for kwargs, costs in calls:
        assert kwargs["funding_periods"] == 1.0
        assert kwargs["funding_rate"] == 0.0001
        assert costs.funding_known is True and costs.complete is True
        if kwargs["direction"] is Direction.LONG:
            assert costs.funding_bps == 1.0
        else:
            assert costs.funding_bps == 0.0
    assert runtime.funding["ev_carry_unpriced"] == 0


async def test_without_a_reading_nothing_is_priced_the_omission_is_counted_and_entries_go_on() -> None:
    runtime, _execution, market, _clock = build(max_holding_bars=12, charge_funding=True)
    assert runtime._funding_rate is None, "the fixture has no funding monitor"
    calls = _record_estimates(runtime)
    await runtime.start()
    try:
        await _drive_to_first_order(runtime, market)
    finally:
        await runtime.stop()
    assert calls
    for kwargs, costs in calls:
        assert kwargs["funding_periods"] == 0.0 and kwargs["funding_rate"] is None
        assert costs.funding_bps == 0.0 and costs.complete is True
    assert runtime.funding["ev_carry_unpriced"] >= len(calls)
    assert runtime.counters["orders"] >= 1, "a missing funding feed does not stop the paper session"


async def test_without_a_time_stop_no_horizon_is_claimed() -> None:
    runtime, _execution, market, _clock = build(max_holding_bars=0, charge_funding=True)
    runtime._funding_rate = lambda: 0.0001
    calls = _record_estimates(runtime)
    await runtime.start()
    try:
        await _drive_to_first_order(runtime, market)
    finally:
        await runtime.stop()
    assert calls and all(k["funding_periods"] == 0.0 for k, _ in calls)
    assert runtime.funding["ev_carry_unpriced"] == 0


async def test_a_non_finite_reading_is_treated_as_no_reading() -> None:
    runtime, _execution, market, _clock = build(max_holding_bars=12, charge_funding=True)
    runtime._funding_rate = lambda: float("nan")
    calls = _record_estimates(runtime)
    await runtime.start()
    try:
        await _drive_to_first_order(runtime, market)
    finally:
        await runtime.stop()
    assert calls and all(k["funding_periods"] == 0.0 and k["funding_rate"] is None for k, _ in calls)
    assert runtime.funding["ev_carry_unpriced"] >= 1
