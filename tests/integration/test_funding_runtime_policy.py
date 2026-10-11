"""How the 24/7 session uses a funding rate it may or may not have (Phase 1.5).

An absent, stale or invalid rate charges nothing and is counted under its reason; a
non-finite number never reaches the ledger; the funding a round trip paid while open is
in its reported net exactly once (the accrual booked it in the account, the round trip's
own realised P&L is booked before carry); and the ``block`` policy refuses an entry whose
carry cannot be priced.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from tests.integration.test_live_runtime import (
    _open_a_position,
    _previous_funding_block,
    _seed_every_bucket,
    build_runtime_paper_with,
)


def _events(runtime, kind: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    seen: list[dict[str, Any]] = []
    previous = runtime._on_event

    def capture(event: dict[str, Any]) -> None:
        if event.get("type") == kind:
            seen.append(event.get("data", {}))
        previous(event)

    runtime._on_event = capture
    return seen


async def _settle_once(runtime, market) -> None:  # type: ignore[no-untyped-def]
    """The next check sees one eight-hour boundary crossed since the last one — a
    settlement watched as it happens (Phase 1.7)."""
    market.advance()  # first: the bar may itself enter a new period
    runtime._funding_period = _previous_funding_block(runtime._clock.now())
    await runtime._cycle_once()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "not-a-number"])
async def test_an_invalid_rate_charges_nothing_touches_no_ledger_and_is_counted(bad: Any) -> None:
    runtime, execution, market = build_runtime_paper_with(charge_funding=True)
    runtime._funding_rate = lambda: bad
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        equity_before = runtime._ledger.snapshot().equity
        await _settle_once(runtime, market)
        assert runtime._open_trade is not None
        assert runtime.funding["payments"] == 0
        assert runtime.funding["skipped_no_rate"] == 1 and runtime.funding["skipped_invalid"] == 1
        assert runtime.funding["last_skip_reason"] == "invalid"
        assert runtime._ledger.snapshot().equity == pytest.approx(equity_before)
        assert math.isfinite(runtime._ledger.snapshot().equity)
        assert not [a for a in execution.adjustments if "funding" in a[1]]
    finally:
        await runtime.stop()


async def test_a_stale_reading_is_skipped_under_its_own_reason() -> None:
    runtime, execution, market = build_runtime_paper_with(charge_funding=True)
    runtime._funding_rate = lambda: None
    runtime._funding_status = lambda: {"state": "stale", "rate": None, "age_seconds": 7200.0}
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        await _settle_once(runtime, market)
        assert runtime.funding["payments"] == 0
        assert runtime.funding["skipped_stale"] == 1 and runtime.funding["skipped_no_rate"] == 1
        assert runtime.funding["last_skip_reason"] == "stale"
    finally:
        await runtime.stop()


async def test_an_absent_reading_is_skipped_under_absent() -> None:
    runtime, execution, market = build_runtime_paper_with(charge_funding=True)
    runtime._funding_rate = lambda: None
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        await _settle_once(runtime, market)
        assert runtime.funding["skipped_absent"] == 1 and runtime.funding["skipped_no_rate"] == 1
    finally:
        await runtime.stop()


async def test_a_zero_rate_settles_as_a_payment_of_nothing() -> None:
    runtime, execution, market = build_runtime_paper_with(charge_funding=True)
    runtime._funding_rate = lambda: 0.0
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        equity_before = runtime._ledger.snapshot().equity
        await _settle_once(runtime, market)
        assert runtime.funding["payments"] == 1 and runtime.funding["paid_usd"] == 0.0
        assert runtime.funding["skipped_no_rate"] == 0
        assert runtime._open_trade["funding_paid"] == 0.0
        assert runtime._ledger.snapshot().equity == pytest.approx(equity_before)
    finally:
        await runtime.stop()


async def test_the_funding_a_round_trip_paid_is_in_its_net_exactly_once() -> None:
    """One settlement at +0.0001 while open, then the close. The closed trade reports a
    net that is gross minus fees minus the funding paid; the ledger carries the funding
    once (booked at the settlement) and the round trip's P&L before carry."""
    runtime, execution, market = build_runtime_paper_with(
        charge_funding=True, trail_atr_multiple=0.0, breakeven_after_r=0.0
    )
    runtime._funding_rate = lambda: 0.0001
    closed = _events(runtime, "trade.closed")
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        long = position.quantity > 0
        notional = abs(position.quantity) * execution.price
        runtime._planned_exit["stop"] = execution.price * (0.5 if long else 1.5)
        realised_before = runtime._ledger.snapshot().realised_pnl

        await _settle_once(runtime, market)
        expected_funding = 0.0001 * notional * (1.0 if long else -1.0)
        assert runtime._open_trade is not None
        assert runtime._open_trade["funding_paid"] == pytest.approx(expected_funding, rel=0.05)

        assert await runtime._close_position("time stop") is True
        for _ in range(3):
            market.advance()
            await runtime._cycle_once()
            if runtime._open_trade is None:
                break
        assert runtime._open_trade is None and closed, "the round trip closed and was announced"
        trade = closed[-1]
        funding_bps = expected_funding / notional * 10_000.0
        assert trade["funding_bps"] == pytest.approx(funding_bps, rel=0.05)
        assert trade["net_bps"] == pytest.approx(trade["gross_bps"] - trade["fees_bps"] - trade["funding_bps"], abs=1e-6)
        # The ledger: the settlement booked -funding; the close booked gross - fees.
        realised_after = runtime._ledger.snapshot().realised_pnl
        before_carry_usd = notional * (trade["gross_bps"] - trade["fees_bps"]) / 10_000.0
        assert realised_after - realised_before == pytest.approx(before_carry_usd - expected_funding, rel=0.05)
        # The estimator still learns the gross move; the retrospective sees the net of carry.
        assert trade["carry_unpriced"] is None or isinstance(trade["carry_unpriced"], str)
    finally:
        await runtime.stop()


async def test_the_block_policy_refuses_an_entry_whose_carry_cannot_be_priced() -> None:
    runtime, execution, market = build_runtime_paper_with(
        charge_funding=True, max_holding_bars=12, funding_unknown_policy="block"
    )
    runtime._funding_rate = lambda: None
    refusals = _events(runtime, "live.no_trade")
    await runtime.start()
    try:
        _seed_every_bucket(runtime)
        for _ in range(200):
            market.advance()
            await runtime._cycle_once()
        assert runtime.counters["orders"] == 0
        assert runtime.funding["blocked"] >= 1
        assert runtime.funding["ev_carry_unpriced"] >= 1
        assert runtime.funding["ev_carry_unpriced_reason"] == "absent"
        assert any("funding gate" in str(r.get("reason", "")) for r in refusals)
        assert await execution.get_positions() == {}
    finally:
        await runtime.stop()


async def test_the_allow_policy_takes_the_entry_and_marks_the_carry_unpriced() -> None:
    runtime, execution, market = build_runtime_paper_with(charge_funding=True, max_holding_bars=12)
    runtime._funding_rate = lambda: None
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        assert runtime._entry_beliefs is not None
        assert runtime._entry_beliefs["carry_unpriced"] == "absent"
        assert runtime.funding["blocked"] == 0
    finally:
        await runtime.stop()


async def test_a_priced_carry_leaves_no_mark() -> None:
    runtime, execution, market = build_runtime_paper_with(charge_funding=True, max_holding_bars=12)
    runtime._funding_rate = lambda: 0.0001
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        assert runtime._entry_beliefs["carry_unpriced"] is None
        assert runtime.funding["ev_carry_unpriced"] == 0
    finally:
        await runtime.stop()


async def test_funding_on_a_position_no_round_trip_tracks_is_charged_once_and_counted_as_unattributed() -> None:
    """The venue holds a position this session lost the record of (a leg a restart did
    not carry, a fill never read). The venue charges positions, not records: the account
    pays the settlement, once, through the same path as any other; no trade carries it,
    so it is counted as unattributed — no round trip is invented and no P&L is moved
    anywhere but the cash the venue moved (Phase 1.6)."""
    runtime, execution, market = build_runtime_paper_with(charge_funding=True)
    runtime._funding_rate = lambda: 0.0001
    closed = _events(runtime, "trade.closed")
    payments = _events(runtime, "live.funding")
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        position = next(iter((await execution.get_positions()).values()))
        long = position.quantity > 0
        notional = abs(position.quantity) * execution.price
        # The record is gone; the position is not.
        runtime._open_trade = None
        runtime._planned_exit = {}
        runtime._entry_beliefs = None
        realised_before = runtime._ledger.snapshot().realised_pnl
        charged_before = [a for a in execution.adjustments if "funding" in a[1]]

        await _settle_once(runtime, market)

        expected = 0.0001 * notional * (1.0 if long else -1.0)
        assert runtime.funding["payments"] == 1
        assert runtime.funding["unattributed_payments"] == 1
        assert runtime.funding["unattributed_usd"] == pytest.approx(expected, rel=0.05)
        assert runtime.funding["paid_usd"] == pytest.approx(expected, rel=0.05)
        assert payments and payments[-1]["attributed"] is False
        # Charged once, in the account, through the venue's cash path.
        charged = [a for a in execution.adjustments if "funding" in a[1]]
        assert len(charged) == len(charged_before) + 1
        assert charged[-1][0] == pytest.approx(-expected, rel=0.05)
        assert runtime._ledger.snapshot().realised_pnl - realised_before == pytest.approx(-expected, rel=0.05)
        # No round trip was invented to carry it.
        assert runtime._open_trade is None
        assert runtime.counters["round_trips"] == 0 and not closed
        assert (await execution.get_positions()) != {}, "the position is still the venue's"
    finally:
        await runtime.stop()


async def test_a_tracked_leg_is_never_counted_as_unattributed() -> None:
    runtime, execution, market = build_runtime_paper_with(charge_funding=True)
    runtime._funding_rate = lambda: 0.0001
    payments = _events(runtime, "live.funding")
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        await _settle_once(runtime, market)
        assert runtime.funding["payments"] == 1 and runtime.funding["unattributed_payments"] == 0
        assert runtime.funding["unattributed_usd"] == 0.0
        assert payments[-1]["attributed"] is True
        assert runtime._open_trade["funding_paid"] == pytest.approx(runtime.funding["paid_usd"])
    finally:
        await runtime.stop()
