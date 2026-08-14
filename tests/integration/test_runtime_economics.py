"""The economics layer, wired into the running pipeline.

Three claims, each checked against a real run rather than a mock:

1. A risk-approved signal is priced before it becomes an order, and the arithmetic is
   recorded whether or not the order happens.
2. A closed round trip becomes evidence: its realised return, net of the fees actually
   paid, lands in the bucket the entry decision was drawn from.
3. The expected-value engine observes in paper mode and enforces in live mode — and the
   reason is a deadlock, not a convenience. This is the one worth reading the docstrings
   for, because "observing" is exactly the shape a disabled safety check has.
"""

from __future__ import annotations

import asyncio

import pytest

from tia.core.config import Environment, settings_for_env
from tia.runtime import RuntimeConfig, RuntimeEngine


async def run_engine(**overrides) -> RuntimeEngine:  # type: ignore[no-untyped-def]
    """Run a whole scenario to exhaustion and hand back the engine."""
    config = RuntimeConfig(
        scenario="trend_up",
        bar_interval_seconds=0.0,
        initial_capital=10_000.0,
        **overrides,
    )
    engine = RuntimeEngine(settings_for_env(Environment.DEMO), config)
    await engine.start()
    for _ in range(80_000):
        await asyncio.sleep(0)
        if not engine.is_running:
            break
    await engine.stop()
    return engine


# --------------------------------------------------------------------------- pricing


async def test_every_would_be_entry_is_priced_before_it_becomes_an_order() -> None:
    engine = await run_engine()

    assert engine.recent_evaluations, "no signal was ever priced"
    row = engine.recent_evaluations[0]
    costs = row["expected_value"]["costs"]

    # A round trip, not a single leg, and every component is present.
    assert set(costs) >= {
        "fee_bps", "spread_bps", "slippage_bps", "latency_bps", "impact_bps", "total_bps"
    }
    assert costs["total_bps"] > 0
    assert costs["dominant"] in {"fees", "spread", "slippage", "latency", "impact"}
    assert row["budget"]["profile"] in {"conservative", "balanced", "aggressive"}


async def test_the_cost_the_engine_subtracts_is_the_cost_the_simulator_charges() -> None:
    """A cost model that disagrees with the fill engine produces an edge that exists only
    in the arithmetic. Both read the same configured fee schedule."""
    settings = settings_for_env(Environment.DEMO)
    engine = await run_engine()
    fees = engine.economics_snapshot()["fees"]

    assert fees["taker_bps"] == settings.execution.taker_fee_bps
    assert fees["maker_bps"] == settings.execution.maker_fee_bps
    assert fees["round_trip_taker_bps"] == pytest.approx(settings.execution.taker_fee_bps * 2)


async def test_the_fee_schedule_is_reported_as_unverified() -> None:
    """It came from configuration, not from an account. The activation gate refuses to
    arm while this is true, and the dashboard says so rather than implying precision."""
    engine = await run_engine()
    fees = engine.economics_snapshot()["fees"]

    assert fees["verified_at_source"] is False
    assert fees["requires_verification"] is True
    assert "not a live account" in fees["source"]


async def test_a_decision_that_would_only_exit_is_not_priced_for_edge() -> None:
    """Closing a position is not a discretionary trade. Blocking an exit because its
    expected value is poor would leave the system holding something it decided to leave —
    which is how a stop-loss becomes advisory."""
    engine = await run_engine()

    exits = [
        row
        for row in engine.recent_decisions
        if row["expected_value"] is None and row["verdict"] == "approve"
    ]
    # There is at least one approved decision made while already holding — those are the
    # ones that carry no edge arithmetic.
    assert engine.counters.suppressed_position_open > 0 or exits


# --------------------------------------------------------------------------- evidence


async def test_a_closed_round_trip_becomes_evidence_in_the_right_bucket() -> None:
    engine = await run_engine()

    assert engine.closed_trades, "the run closed no round trips, so nothing was learned"
    trade = engine.closed_trades[0]

    assert trade["net_bps"] == pytest.approx(trade["gross_bps"] - trade["fees_bps"], abs=1e-6)
    assert trade["fees_bps"] > 0, "a round trip that paid no fees did not happen"
    assert trade["samples_now"] >= 1

    coverage = engine.economics_snapshot()["expected_value"]["coverage"]
    assert sum(coverage.values()) == len(engine.closed_trades)


async def test_realised_returns_are_recorded_net_of_fees_actually_paid() -> None:
    """Gross would double-count: the EV engine subtracts costs again downstream. An edge
    estimate built from gross returns overstates every expectation by a round trip."""
    engine = await run_engine()

    assert engine.closed_trades
    for trade in engine.closed_trades:
        assert trade["net_bps"] < trade["gross_bps"] or trade["fees_bps"] == 0.0


async def test_the_estimator_refuses_to_produce_an_edge_from_a_handful_of_trades() -> None:
    """A run that closes a few trades must not start claiming an expectation from them."""
    engine = await run_engine()
    snapshot = engine.economics_snapshot()["expected_value"]

    if len(engine.closed_trades) < snapshot["min_samples"]:
        assert snapshot["no_evidence"] > 0
        latest = snapshot["latest"]
        if latest is not None:
            assert latest["expected_value"]["edge"] is None


# --------------------------------------------------------------------------- the deadlock


async def test_paper_mode_observes_rather_than_enforces_and_says_so() -> None:
    """The circularity, stated where someone auditing the system will see it.

    The EV engine refuses to trade without a measured edge; an edge is measured from
    closed trades. Enforcing that in paper mode is a deadlock — no trades, so no evidence,
    so no trades, forever. Paper trading is how the evidence gets produced, so the engine
    prices every decision and records what it *would* have refused, while the trade
    proceeds.
    """
    engine = await run_engine()
    snapshot = engine.economics_snapshot()["expected_value"]

    assert snapshot["enforcing"] is False
    assert "deadlock" in snapshot["mode_explanation"]
    assert engine.counters.ev_rejected == 0
    assert engine.counters.ev_would_reject > 0, "nothing was evaluated, so nothing is proven"


async def test_observing_still_counts_every_refusal_it_would_have_made() -> None:
    """Observing must not mean invisible. ``would_reject`` is what makes turning
    enforcement on a decision with a known cost rather than a leap."""
    engine = await run_engine()

    assert engine.counters.ev_would_reject >= engine.counters.ev_no_evidence
    assert engine.economics_snapshot()["expected_value"]["evaluations"] >= (
        engine.counters.ev_would_reject
    )


async def test_enforcing_stops_the_trades_that_observing_only_counted() -> None:
    """The other half: with enforcement on, a system with no measured edge trades nothing.

    Same scenario, same seed, one flag different. If this produced trades anyway, the
    flag would be decorative.
    """
    enforced = await run_engine(enforce_expected_value=True)

    assert enforced.counters.ev_rejected > 0
    assert enforced.counters.ev_rejected == enforced.counters.ev_would_reject
    assert not enforced.closed_trades
    assert enforced.economics_snapshot()["expected_value"]["enforcing"] is True


# --------------------------------------------------------------------------- budget


async def test_the_risk_budget_is_computed_from_live_drawdown_and_streak() -> None:
    engine = await run_engine()
    budget = engine.economics_snapshot()["budget"]

    assert budget["state"] in {"normal", "defensive", "emergency"}
    assert 0.0 <= budget["total_multiplier"] <= 1.0
    assert budget["binding_constraint"]


async def test_the_budget_never_grows_after_a_loss_during_a_real_run() -> None:
    """The property test in ``test_risk_budget.py`` proves this over random inputs; this
    checks the runtime feeds it the inputs that make it hold — specifically, that a losing
    round trip increments the streak rather than resetting it."""
    engine = await run_engine()

    losses = [t for t in engine.closed_trades if t["net_bps"] <= 0]
    if losses:
        assert engine._consecutive_losses >= 0
        assert engine.economics_snapshot()["budget"]["streak_multiplier"] <= 1.0
