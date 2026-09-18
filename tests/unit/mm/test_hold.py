"""HOLD: a pacing denial (quote rate, minimum interval) keeps a resting quote instead
of cancelling it — and nothing else is relaxed. Synthetic events throughout."""

from __future__ import annotations

from tests.unit.mm.test_engine_replay import PROFILE
from tia.domain.enums import SystemMode
from tia.mm.costs import MarketMakerCostConfig
from tia.mm.engine import MarketMakerConfig, MarketMakerEngine
from tia.mm.order_book import DepthSnapshot, DepthUpdate, snapshot_from_levels
from tia.mm.quoting import QuotingConfig
from tia.mm.risk import MarketMakerRiskLimits
from tia.mm.safety import GlobalTradingSafetyGate
from tia.mm.spread import SpreadConfig
from tia.risk.engine import RiskState

T0 = 1_789_754_400_000


def _config(*, max_quotes_per_minute: int = 10, min_quote_interval_ms: int = 250, ttl_ms: int = 1_000) -> MarketMakerConfig:
    return MarketMakerConfig(
        costs=MarketMakerCostConfig(maker_fee_bps=0.5, maker_fee_adverse_bps=1.0),
        spread=SpreadConfig(min_half_spread_bps=0.5, cost_buffer_bps=0.0, vol_multiplier=0.0),
        quoting=QuotingConfig(quote_ttl_ms=ttl_ms),
        requote_interval_ms=200,
        limits=MarketMakerRiskLimits(max_quotes_per_minute=max_quotes_per_minute, min_quote_interval_ms=min_quote_interval_ms),
    )


def _snapshot() -> DepthSnapshot:
    bids = [(round(100_000.0 - i * 0.5, 1), 1.0) for i in range(60)]
    asks = [(round(100_000.5 + i * 0.5, 1), 1.0) for i in range(60)]
    return snapshot_from_levels(100, bids, asks)


class Harness:
    def __init__(self, config: MarketMakerConfig | None = None) -> None:
        self.state = RiskState()
        self.gate = GlobalTradingSafetyGate(risk_state=lambda: self.state, data_usable=lambda: (True, ""))
        self.engine = MarketMakerEngine(config or _config(), latency=PROFILE.scenario("optimistic"), gate=self.gate)
        self.t = T0
        self.uid = 100
        self.engine.on_event("snapshot", _snapshot(), self.t)  # decision + first placement at T0

    def tick(self, dt_ms: int = 100, bids=(), asks=()) -> None:  # type: ignore[no-untyped-def]
        self.t += dt_ms
        self.uid += 1
        self.engine.on_event("depth", DepthUpdate(self.uid, self.uid, tuple(bids), tuple(asks), self.t - 30, self.t), self.t)

    def resting(self) -> list:  # type: ignore[type-arg]
        return [o for o in self.engine.execution.orders.values() if o.state == "resting" and o.t_cancel_requested_ms is None]

    def decisions(self, kind: str) -> list[dict]:  # type: ignore[type-arg]
        return [r for r in self.engine.journal if r["kind"] == "decision" and r.get("decision") == kind]


def test_minimum_interval_denial_holds_the_resting_quote_with_its_reason() -> None:
    h = Harness()
    assert h.engine.execution.placed == 2
    h.tick(100)  # the orders arrive (optimistic latency 40 ms); no decision yet (200 ms cadence)
    assert len(h.resting()) == 2
    h.tick(100)  # t = +200: a decision; last quote 200 ms ago < minimum 250 -> pacing denial
    holds = h.decisions("hold")
    assert len(holds) == 1 and "minimum" in holds[0]["reason"] and "held through pacing denial" in holds[0]["reason"]
    assert holds[0]["resting_orders"] and holds[0]["allowance"]["hold_only"] is True
    assert len(h.resting()) == 2 and h.engine.execution.cancelled == 0 and h.engine.execution.placed == 2
    assert h.engine.holds == 1 and h.engine.requotes == 0


def test_rate_limit_denial_holds_the_resting_quote() -> None:
    h = Harness(_config(max_quotes_per_minute=1, min_quote_interval_ms=50))
    h.tick(100)
    h.tick(100)  # decision: 1 quote in the last minute >= limit 1 -> pacing denial
    holds = h.decisions("hold")
    assert len(holds) == 1 and "quotes in the last minute" in holds[0]["reason"]
    assert len(h.resting()) == 2 and h.engine.execution.placed == 2 and h.engine.execution.cancelled == 0


def test_no_artificial_requotes_while_pacing_denies() -> None:
    h = Harness(_config(max_quotes_per_minute=1, min_quote_interval_ms=50, ttl_ms=60_000))
    for _ in range(8):
        h.tick(100)
    assert h.engine.holds >= 3 and h.engine.requotes == 0 and h.engine.hold_cancels == 0
    assert h.engine.execution.placed == 2 and h.engine.execution.cancelled == 0 and h.engine.cancels == 0
    assert all(r["decision"] == "hold" for r in [x for x in h.engine.journal if x["kind"] == "decision"][1:])


def test_global_halted_cancels_even_while_pacing_denies() -> None:
    h = Harness(_config(max_quotes_per_minute=1, min_quote_interval_ms=50))
    h.tick(100)
    h.tick(100)
    assert h.engine.holds == 1 and len(h.resting()) == 2
    h.state.mode = SystemMode.HALTED
    h.state.kill_switch_reason = "operator"
    h.tick(200)
    blocks = [r for r in h.engine.journal if r["kind"] == "block"]
    assert blocks and blocks[-1]["layer"] == "gate" and blocks[-1]["cancelled"] == 2
    assert h.resting() == [] and h.engine.gate_blocks == 1
    assert all(o.t_cancel_requested_ms is not None for o in h.engine.execution.orders.values())


def test_a_hard_risk_denial_cancels_the_resting_quote() -> None:
    h = Harness(_config(max_quotes_per_minute=1, min_quote_interval_ms=50))
    h.tick(100)
    h.tick(100)
    assert h.engine.holds == 1
    h.engine.controller.engage_kill_switch("test")  # a hard rule: not a pacing denial
    h.tick(200)
    last = [r for r in h.engine.journal if r["kind"] == "decision"][-1]
    assert last["decision"] == "no_quote" and "kill switch" in last["reason"] and last["allowance"]["hold_only"] is False
    assert last["cancelled"] == 2 and h.resting() == []


def test_a_quote_that_must_move_is_cancelled_not_held_and_not_replaced() -> None:
    h = Harness(_config(max_quotes_per_minute=1, min_quote_interval_ms=50))
    h.tick(100)
    h.tick(100)
    assert h.engine.holds == 1
    # The best 30 bids vanish: the mid drops 7.5 USD (0.75 bps), beyond the 0.5 bps threshold.
    h.tick(200, bids=[(round(100_000.0 - i * 0.5, 1), 0.0) for i in range(30)])
    last = [r for r in h.engine.journal if r["kind"] == "decision"][-1]
    assert last["decision"] == "no_quote" and "cancelled, not replaced" in last["reason"] and last["cancelled"] == 2
    assert h.engine.hold_cancels == 1 and h.engine.execution.placed == 2 and h.resting() == []


def test_ttl_expires_a_held_quote_and_pacing_relief_requotes() -> None:
    h = Harness(_config(max_quotes_per_minute=10, min_quote_interval_ms=1_500, ttl_ms=500))
    h.tick(100)
    h.tick(100)  # hold (minimum interval)
    assert h.engine.holds == 1
    for _ in range(4):  # +600 ms: the TTL (500 ms after arrival) requests cancels through the late-cancel path
        h.tick(100)
    assert h.engine.execution.expired >= 1
    for _ in range(12):  # +1.2 s more: cancels take effect; once 1.5 s passed since the placement, a new quote is allowed
        h.tick(100)
    assert h.engine.execution.cancelled >= 2 and h.engine.execution.placed >= 4
    assert h.decisions("quote")[-1]["t"] > T0  # a fresh placement, not a held one
