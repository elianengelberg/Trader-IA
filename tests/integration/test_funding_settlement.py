"""Funding settles by the clock, in every state; a gap is settled from its own data or
recorded as unreconciled (Phase 1.7).

PAUSED and SAFE_MODE hold the position and send nothing, and the settlement they live
through is still charged, on time. A session that was not there for a settlement — a
stalled loop here, a restart in ``test_funding_restore.py`` — settles it from the venue's
realised rate for that settlement and the mark printed then, each period with its own
numbers and its own journal key; a missing rate, a missing mark, a fill since the
settlement or a period too old to look up leaves the period **unreconciled**, counted and
listed with the reason, never charged at today's numbers and never charged as zero.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import pytest

from tests.integration.test_live_runtime import (
    FakeMarketData,
    _open_a_position,
    _previous_funding_block,
    build_runtime_paper_with,
)
from tia.runtime.live import (
    FUNDING_PROMPT_GRACE_SECONDS,
    FUNDING_RECONSTRUCT_MAX_PERIODS,
    funding_period_from_index,
    funding_period_index,
    funding_period_key,
    funding_period_of,
    funding_period_start,
)
from tia.runtime.states import LiveState

RATE = 0.0001
TODAYS_READING = 0.0009


def _events(runtime, kind: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    seen: list[dict[str, Any]] = []
    previous = runtime._on_event

    def capture(event: dict[str, Any]) -> None:
        if event.get("type") == kind:
            seen.append(event.get("data", {}))
        previous(event)

    runtime._on_event = capture
    return seen


def _settlement_after(now: datetime, periods: int = 1) -> datetime:
    return funding_period_start(funding_period_from_index(funding_period_index(funding_period_of(now)) + periods))


def _period_key_after(now: datetime, periods: int = 1) -> str:
    return funding_period_key(funding_period_from_index(funding_period_index(funding_period_of(now)) + periods))


async def _step_until(runtime, clock, target: datetime, *, step: timedelta = timedelta(seconds=60)) -> int:  # type: ignore[no-untyped-def]
    """Cycle every ``step`` of clock time until the clock is past ``target``; the cycles."""
    cycles = 0
    while clock.now() < target:
        if cycles >= 600:
            raise AssertionError("the clock never reached the target")
        clock.advance_by(step)
        await runtime._cycle_once()
        cycles += 1
    return cycles


def _stall_to(runtime, clock, target: datetime) -> datetime:  # type: ignore[no-untyped-def]
    """Jump the clock to ``target``, or further, so that the gap since the last settlement
    check exceeds the prompt grace: a stall the session was not there for, wherever in the
    period the position happened to open (the fake series is anchored to the wall clock)."""
    checked = runtime._funding_checked_at or clock.now()
    at = max(target, checked + timedelta(seconds=FUNDING_PROMPT_GRACE_SECONDS + 1))
    clock.advance_to(at)
    return at


class _ArchiveMarket(FakeMarketData):
    """A feed with history on request: ``get_candles(end=...)`` answers from an archive
    of the marks printed at given moments, the way a venue's klines with ``endTime`` do."""

    def __init__(self, candles, clock=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(candles, clock)
        self.archive: dict[datetime, float] = {}
        self.history_calls = 0

    async def get_candles(self, symbol, timeframe, *, limit=500, end=None):  # type: ignore[no-untyped-def]
        if end is not None:
            self.history_calls += 1
            if end in self.archive:
                px = self.archive[end]
                base = self._candles[0]
                return [base.model_copy(update={
                    "open_time": end - timedelta(minutes=1), "close_time": end,
                    "open": px, "high": px, "low": px, "close": px,
                })]
        return await super().get_candles(symbol, timeframe, limit=limit, end=end)


def _build(*, archive: bool = False, **overrides: Any):  # type: ignore[no-untyped-def]
    runtime, execution, market = build_runtime_paper_with(
        charge_funding=True, trail_atr_multiple=0.0, breakeven_after_r=0.0, **overrides
    )
    if archive:
        feed = _ArchiveMarket(market._candles, market._clock)
        feed.cursor = market.cursor
        runtime._market_data = feed
        market = feed
    runtime._funding_rate = lambda: RATE
    return runtime, execution, market


async def _held(runtime, execution, market):  # type: ignore[no-untyped-def]
    await _open_a_position(runtime, execution, market)
    position = next(iter((await execution.get_positions()).values()))
    runtime._planned_exit["stop"] = execution.price * (0.5 if position.quantity > 0 else 1.5)
    return position


def _sign(position) -> float:  # type: ignore[no-untyped-def]
    return 1.0 if position.quantity > 0 else -1.0


def _funding_adjustments(execution) -> list[float]:  # type: ignore[no-untyped-def]
    return [a for a, reason in execution.adjustments if "funding" in reason]


# ------------------------------------------------------------------ paused and safe mode


async def test_a_settlement_during_a_pause_is_charged_on_time_and_nothing_is_sent() -> None:
    runtime, execution, market = _build()
    await runtime.start()
    try:
        position = await _held(runtime, execution, market)
        runtime.pause(actor="operator")
        assert runtime.machine.state is LiveState.PAUSED
        closed = _events(runtime, "trade.closed")
        payments = _events(runtime, "live.funding")
        submissions, orders, charged = execution.submissions, runtime.counters["orders"], len(_funding_adjustments(execution))
        boundary = _settlement_after(runtime._clock.now())

        cycles = await _step_until(runtime, market._clock, boundary + timedelta(seconds=1))
        assert cycles >= 1 and runtime.machine.state is LiveState.PAUSED, "still paused, and it ran"
        expected = RATE * abs(position.quantity) * execution.price * _sign(position)
        assert runtime.funding["payments"] == 1
        assert runtime.funding["paid_usd"] == pytest.approx(expected, rel=0.05)
        assert payments[-1]["source"] == "observed" and payments[-1]["attributed"] is True
        assert payments[-1]["period"] == funding_period_key(funding_period_of(boundary))
        assert runtime._open_trade is not None and runtime._open_trade["funding_paid"] == pytest.approx(runtime.funding["paid_usd"])
        assert runtime.funding["unreconciled_periods"] == 0 and runtime.funding["unattributed_payments"] == 0
        assert len(_funding_adjustments(execution)) == charged + 1
        # Accounting only: no order, no fill, no exit while paused.
        assert execution.submissions == submissions and runtime.counters["orders"] == orders
        assert not closed and (await execution.get_positions()) != {}
        assert runtime.funding["period"] == funding_period_key(funding_period_of(runtime._clock.now()))
    finally:
        await runtime.stop()


async def test_safe_mode_holds_the_position_settles_its_funding_and_sends_nothing() -> None:
    runtime, execution, market = _build()
    await runtime.start()
    try:
        position = await _held(runtime, execution, market)
        await runtime.kill_switch(reason="operator doubt", actor="operator")
        assert runtime.machine.state is LiveState.SAFE_MODE
        closed = _events(runtime, "trade.closed")
        submissions, charged = execution.submissions, len(_funding_adjustments(execution))
        boundary = _settlement_after(runtime._clock.now())

        await _step_until(runtime, market._clock, boundary + timedelta(seconds=1))
        assert runtime.machine.state is LiveState.SAFE_MODE, "no automatic exit"
        with pytest.raises(Exception, match="resume"):
            runtime.resume(actor="operator")
        expected = RATE * abs(position.quantity) * execution.price * _sign(position)
        assert runtime.funding["payments"] == 1
        assert runtime.funding["paid_usd"] == pytest.approx(expected, rel=0.05)
        assert len(_funding_adjustments(execution)) == charged + 1
        assert execution.submissions == submissions, "nothing was sent"
        assert not closed and (await execution.get_positions()) != {}, "the position is still held"
        assert runtime._open_trade is not None
    finally:
        await runtime.stop()


# ------------------------------------------------------------------------- gaps


async def test_a_stall_across_two_settlements_without_history_leaves_both_unreconciled() -> None:
    runtime, execution, market = _build()
    await runtime.start()
    try:
        position = await _held(runtime, execution, market)
        now = runtime._clock.now()
        keys = [_period_key_after(now, 1), _period_key_after(now, 2)]
        unreconciled = _events(runtime, "live.funding_unreconciled")
        charged = len(_funding_adjustments(execution))

        market._clock.advance_to(_settlement_after(now, 2) + timedelta(seconds=1))
        await runtime._cycle_once()

        assert runtime.funding["payments"] == 0 and len(_funding_adjustments(execution)) == charged
        assert runtime.funding["unreconciled_periods"] == 2
        assert [e["period"] for e in runtime.funding["unreconciled"]] == keys
        assert {e["reason"] for e in runtime.funding["unreconciled"]} == {"rate_unknown"}
        assert [e["period"] for e in unreconciled] == keys
        assert runtime.funding["last_unreconciled_reason"] == "rate_unknown"
        assert runtime.funding["period"] == keys[-1], "the pointer moved past them: they are not pending, they are unknown"
        assert runtime._open_trade["funding_paid"] == 0.0 and runtime.funding["unattributed_usd"] == 0.0
        assert position.quantity != 0
        assert runtime.snapshot()["account"]["funding"]["unreconciled_periods"] == 2
    finally:
        await runtime.stop()


async def test_a_stall_across_two_settlements_with_history_and_marks_settles_each_from_its_own_data() -> None:
    persisted: list[tuple[str, dict[str, Any]]] = []

    async def persist(kind: str, payload: dict[str, Any]) -> None:
        persisted.append((kind, payload))

    runtime, execution, market = _build(archive=True, persist=persist)
    runtime._funding_rate = lambda: TODAYS_READING
    await runtime.start()
    try:
        position = await _held(runtime, execution, market)
        now = runtime._clock.now()
        b1, b2 = _settlement_after(now, 1), _settlement_after(now, 2)
        k1, k2 = _period_key_after(now, 1), _period_key_after(now, 2)
        market.archive = {b1: 50_100.0, b2: 49_900.0}
        runtime._funding_rate_at = {b1: 0.0001, b2: -0.0002}.get
        payments = _events(runtime, "live.funding")

        market._clock.advance_to(b2 + timedelta(seconds=1))
        await runtime._cycle_once()
        assert await runtime.flush_persistence(timeout_seconds=5.0)

        qty, sign = abs(position.quantity), _sign(position)
        expected = [0.0001 * qty * 50_100.0 * sign, -0.0002 * qty * 49_900.0 * sign]
        assert runtime.funding["payments"] == 2 == runtime.funding["reconstructed_payments"]
        assert runtime.funding["unreconciled_periods"] == 0
        assert runtime.funding["paid_usd"] == pytest.approx(sum(expected), abs=1e-6)  # the record rounds to 6 dp
        assert [p["source"] for p in payments] == ["reconstructed", "reconstructed"]
        assert [p["period"] for p in payments] == [k1, k2]
        assert [p["rate"] for p in payments] == [0.0001, -0.0002], "each settlement's own rate, never today's reading"
        assert [p["paid_usd"] for p in payments] == pytest.approx(expected, abs=1e-4)
        assert [p["notional"] for p in payments] == pytest.approx([qty * 50_100.0, qty * 49_900.0], abs=0.01)
        # Attributed: the leg was open at both settlements.
        assert runtime._open_trade["funding_paid"] == pytest.approx(sum(expected), rel=1e-9)
        assert runtime.funding["unattributed_payments"] == 0
        # The journal: one adjustment per period, keyed by the period.
        # The settlements and the plan travel in one batched write (Phase 1.8).
        envelopes = [
            env
            for kind, payload in persisted
            for env in (payload["envelopes"] if kind == "account_events" else [payload["envelope"]] if kind == "account_event" else [])
        ]
        keys = [e.idempotency_key for e in envelopes if e.event_type == "account.adjustment"]
        assert keys == [f"account.adjustment:funding:{k1}", f"account.adjustment:funding:{k2}"]
        batches = [payload for kind, payload in persisted if kind == "account_events"]
        assert len(batches) == 1 and [e.event_type for e in batches[0]["envelopes"]] == ["account.adjustment", "account.adjustment", "account.plan"]
        # The record reconciles with the account: attributed + unattributed = what the venue moved.
        assert runtime._open_trade["funding_paid"] + runtime.funding["unattributed_usd"] == pytest.approx(
            -sum(_funding_adjustments(execution)), abs=1e-6
        )
        assert runtime.funding["period"] == k2
    finally:
        await runtime.stop()


async def test_periods_older_than_the_lookup_window_are_unreconciled_without_a_lookup() -> None:
    runtime, execution, market = _build(archive=True)
    await runtime.start()
    try:
        position = await _held(runtime, execution, market)
        now = runtime._clock.now()
        gap = FUNDING_RECONSTRUCT_MAX_PERIODS + 2
        boundaries = [_settlement_after(now, i) for i in range(1, gap + 1)]
        market.archive = dict.fromkeys(boundaries, 50_000.0)
        runtime._funding_rate_at = lambda at: RATE
        market._clock.advance_to(boundaries[-1] + timedelta(seconds=1))
        await runtime._cycle_once()

        assert runtime.funding["payments"] == FUNDING_RECONSTRUCT_MAX_PERIODS
        assert runtime.funding["unreconciled_periods"] == 2
        assert [e["reason"] for e in runtime.funding["unreconciled"]] == ["too_old", "too_old"]
        assert [e["period"] for e in runtime.funding["unreconciled"]] == [_period_key_after(now, 1), _period_key_after(now, 2)]
        assert market.history_calls == FUNDING_RECONSTRUCT_MAX_PERIODS, "no lookup for the periods given up"
        assert runtime.funding["paid_usd"] == pytest.approx(
            RATE * abs(position.quantity) * 50_000.0 * _sign(position) * FUNDING_RECONSTRUCT_MAX_PERIODS, abs=1e-5
        )
    finally:
        await runtime.stop()


@pytest.mark.parametrize(
    ("history", "reason"),
    [
        (None, "rate_unknown"),
        (lambda at: None, "rate_unknown"),
        (lambda at: float("nan"), "rate_unknown"),
        (lambda at: float("inf"), "rate_unknown"),
        (lambda at: "not-a-rate", "rate_unknown"),
        (lambda at: (_ for _ in ()).throw(ConnectionError("history unreachable")), "rate_unknown"),
    ],
    ids=["no-history", "none", "nan", "inf", "string", "raises"],
)
async def test_a_missing_or_invalid_realised_rate_leaves_the_period_unreconciled(history, reason) -> None:  # type: ignore[no-untyped-def]
    runtime, execution, market = _build(archive=True)
    await runtime.start()
    try:
        await _held(runtime, execution, market)
        now = runtime._clock.now()
        b1 = _settlement_after(now)
        market.archive = {b1: 50_000.0}
        runtime._funding_rate_at = history
        charged = len(_funding_adjustments(execution))
        _stall_to(runtime, market._clock, b1 + timedelta(seconds=1))
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 0 and len(_funding_adjustments(execution)) == charged
        assert runtime.funding["unreconciled_periods"] == 1
        assert runtime.funding["unreconciled"] == [{"period": _period_key_after(now), "reason": reason}]
        assert runtime._open_trade["funding_paid"] == 0.0
    finally:
        await runtime.stop()


async def test_a_missing_mark_at_the_settlement_leaves_the_period_unreconciled() -> None:
    """The feed has no bar near the settlement (plain fake: its bars end hours before):
    the realised rate alone does not price a settlement."""
    runtime, execution, market = _build()
    await runtime.start()
    try:
        await _held(runtime, execution, market)
        now = runtime._clock.now()
        runtime._funding_rate_at = lambda at: RATE
        _stall_to(runtime, market._clock, _settlement_after(now) + timedelta(seconds=1))
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 0
        assert runtime.funding["unreconciled"] == [{"period": _period_key_after(now), "reason": "mark_unknown"}]
    finally:
        await runtime.stop()


async def test_a_fill_after_the_settlement_leaves_the_period_unreconciled() -> None:
    """What was held *at* the settlement cannot be read off a position that changed since."""
    runtime, execution, market = _build(archive=True)
    await runtime.start()
    try:
        await _held(runtime, execution, market)
        now = runtime._clock.now()
        b1 = _settlement_after(now)
        market.archive = {b1: 50_000.0}
        runtime._funding_rate_at = lambda at: RATE
        runtime._last_fill_at = b1 + timedelta(minutes=1)
        _stall_to(runtime, market._clock, b1 + timedelta(minutes=2))
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 0
        assert runtime.funding["unreconciled"] == [{"period": _period_key_after(now), "reason": "position_changed"}]
    finally:
        await runtime.stop()


async def test_a_settlement_reconstructed_for_a_leg_opened_after_it_is_the_accounts_not_the_legs() -> None:
    runtime, execution, market = _build(archive=True)
    await runtime.start()
    try:
        position = await _held(runtime, execution, market)
        now = runtime._clock.now()
        b1 = _settlement_after(now)
        market.archive = {b1: 50_000.0}
        runtime._funding_rate_at = lambda at: RATE
        # The record says the leg opened after the settlement (a restored leg whose fill
        # the journal dates later): the charge is the account's, pinned on no trade.
        runtime._open_trade["opened_at"] = b1 + timedelta(minutes=5)
        _stall_to(runtime, market._clock, b1 + timedelta(minutes=10))
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 1 and runtime.funding["unattributed_payments"] == 1
        assert runtime.funding["unattributed_usd"] == pytest.approx(RATE * abs(position.quantity) * 50_000.0 * _sign(position), abs=1e-6)
        assert runtime._open_trade["funding_paid"] == 0.0
    finally:
        await runtime.stop()


async def test_flat_through_a_gap_owes_nothing_and_records_nothing() -> None:
    runtime, execution, market = _build()
    await runtime.start()
    try:
        market.advance()
        await runtime._cycle_once()  # the pointer is set
        now = runtime._clock.now()
        assert await execution.get_positions() == {}
        market._clock.advance_to(_settlement_after(now, 2) + timedelta(seconds=1))
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 0 and runtime.funding["unreconciled_periods"] == 0
        assert runtime.funding["period"] == _period_key_after(now, 2)
    finally:
        await runtime.stop()


# ------------------------------------------------------------------- idempotency


async def test_a_period_this_process_settled_is_never_settled_again() -> None:
    """A pointer moved backwards (a restore adopting an older plan) finds the period in
    the settled set and charges nothing."""
    runtime, execution, market = _build()
    await runtime.start()
    try:
        await _held(runtime, execution, market)
        market.advance()  # first: the bar may itself enter a new period
        runtime._funding_period = _previous_funding_block(runtime._clock.now())
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 1
        charged = len(_funding_adjustments(execution))
        settled = runtime.funding["period"]

        market.advance()
        runtime._funding_period = _previous_funding_block(runtime._clock.now())  # redelivery
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 1 and len(_funding_adjustments(execution)) == charged
        assert runtime.funding["period"] == settled and runtime.funding["unreconciled_periods"] == 0
    finally:
        await runtime.stop()


async def test_a_watched_settlement_without_a_usable_reading_is_unreconciled_under_the_monitors_reason() -> None:
    runtime, execution, market = _build()
    runtime._funding_rate = lambda: None
    runtime._funding_status = lambda: {"state": "stale", "rate": None}
    await runtime.start()
    try:
        await _held(runtime, execution, market)
        market.advance()  # first: the bar may itself enter a new period
        runtime._funding_period = _previous_funding_block(runtime._clock.now())
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 0 and runtime.funding["skipped_stale"] == 1
        assert runtime.funding["unreconciled"] == [{"period": runtime.funding["period"], "reason": "stale"}]
        assert math.isfinite(runtime._ledger.snapshot().equity)
    finally:
        await runtime.stop()


# ------------------------------------------------------- the rate a settlement is priced at


async def test_a_watched_settlement_is_priced_at_the_realised_rate_when_the_record_already_has_it() -> None:
    """Two rates exist for a settlement: the venue's running estimate (the monitor's
    current reading) and the realised rate the venue publishes for it. The record says
    which one priced each settlement; the realised one wins whenever it is known (Phase 1.8)."""
    runtime, execution, market = _build()
    runtime._funding_rate = lambda: TODAYS_READING
    payments = _events(runtime, "live.funding")
    await runtime.start()
    try:
        position = await _held(runtime, execution, market)
        market.advance()  # first: the bar may itself enter a new period
        boundary = funding_period_start(funding_period_of(runtime._clock.now()))
        runtime._funding_rate_at = lambda at: RATE if at == boundary else None
        runtime._funding_period = _previous_funding_block(runtime._clock.now())
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 1
        assert payments[-1]["source"] == "observed" and payments[-1]["rate_source"] == "realised"
        assert payments[-1]["rate"] == RATE, "the realised rate, not today's reading"
        assert runtime.funding["realised_payments"] == 1 and runtime.funding["estimate_payments"] == 0
        assert runtime.funding["last_rate_source"] == "realised"
        assert "realised rate" in execution.adjustments[-1][1]
        assert runtime.funding["paid_usd"] == pytest.approx(RATE * abs(position.quantity) * execution.price * _sign(position), rel=0.05)
    finally:
        await runtime.stop()


async def test_a_watched_settlement_without_the_realised_rate_is_priced_at_the_estimate_and_says_so() -> None:
    runtime, execution, market = _build()
    runtime._funding_rate = lambda: TODAYS_READING
    payments = _events(runtime, "live.funding")
    await runtime.start()
    try:
        await _held(runtime, execution, market)
        runtime._funding_rate_at = lambda at: None  # the venue has not published it yet
        market.advance()  # first: the bar may itself enter a new period
        runtime._funding_period = _previous_funding_block(runtime._clock.now())
        await runtime._cycle_once()
        assert runtime.funding["payments"] == 1
        assert payments[-1]["rate_source"] == "estimate" and payments[-1]["rate"] == TODAYS_READING
        assert runtime.funding["estimate_payments"] == 1 and runtime.funding["realised_payments"] == 0
        assert "estimate rate" in execution.adjustments[-1][1]
    finally:
        await runtime.stop()
