"""Authorization of a quote: the risk stage (ALLOW / REDUCE_ONLY / DENY) and the economics
stage (per side, every cost itemised), and how the engine applies them. The paper engine
has no authorizer; ``test_engine_replay`` proves it writes the same journal as before."""

from __future__ import annotations

from typing import Any

import pytest

from tests.unit.mm.test_engine_replay import PROFILE, _config, _gate, _tape
from tests.unit.mm.test_safety_risk_quoting import LATENCY, _features
from tia.mm.authorization import (
    ActivationView,
    Authorization,
    AuthorizationContext,
    EconomicsConfig,
    MMEconomicsAuthorizer,
    MMRiskAuthorizer,
    Verdict,
)
from tia.mm.engine import MarketMakerEngine
from tia.mm.fair_value import FairValueEstimate
from tia.mm.quoting import QuoteDecision
from tia.mm.risk import LedgerView, RiskAllowance
from tia.mm.safety import SafetyState, SafetyStatus
from tia.mm.toxicity import ToxicityReading

T0 = 1_789_754_400_000


def _gate_status(state: SafetyState = SafetyState.SAFE, reason: str = "") -> SafetyStatus:
    return SafetyStatus(state, reason, T0)


def _allowance(*, allowed: bool = True, bid: bool = True, ask: bool = True, max_size: float = 0.01, hold_only: bool = False, reason: str = "within limits", kill: bool = False) -> RiskAllowance:
    return RiskAllowance(allowed=allowed, reason=reason, max_size_btc=max_size, bid_allowed=bid, ask_allowed=ask, kill_switch=kill, hold_only=hold_only)


def _ctx(*, stage: str = "risk", gate: SafetyStatus | None = None, allowance: RiskAllowance | None = None, inventory: float = 0.0, mark: float = 100_000.0, cash: float | None = None, base: float | None = None, **extra: Any) -> AuthorizationContext:
    return AuthorizationContext(
        t_ms=T0, stage=stage, gate=gate or _gate_status(), allowance=allowance or _allowance(),
        ledger=LedgerView(inventory, 5_000.0, 5_000.0, 5_000.0, mark), latency=LATENCY, cash_usd=cash, base_balance_btc=base, **extra,
    )


def _risk(*, cap: float | None = None, activation: ActivationView | None = None, health: str = "", kill: str = "", margin: float = 120.0) -> MMRiskAuthorizer:
    return MMRiskAuthorizer(
        capital_cap_usd=lambda: cap,
        activation=(lambda _t: activation) if activation is not None else None,
        execution_health=lambda: health,
        kill_switch=lambda: kill,
        expiry_margin_s=margin,
    )


# ------------------------------------------------------------------ risk stage


def test_a_clean_context_is_allowed_on_both_sides_with_the_controllers_size() -> None:
    verdict = _risk().authorize(_ctx())
    assert verdict.verdict is Verdict.ALLOW and verdict.bid_allowed and verdict.ask_allowed and verdict.max_size_btc == 0.01
    assert verdict.reasons == ("within every limit",) and verdict.stage == "risk" and verdict.authorizer == "mm_risk"
    assert verdict.as_dict()["verdict"] == "allow"


@pytest.mark.parametrize("state", [SafetyState.HALTED, SafetyState.SAFE_MODE, SafetyState.SYSTEM_UNSAFE, SafetyState.DATA_INVALID])
def test_a_closed_global_gate_is_a_denial_whatever_else_holds(state: SafetyState) -> None:
    verdict = _risk().authorize(_ctx(gate=_gate_status(state, "because")))
    assert verdict.denied and not verdict.bid_allowed and not verdict.ask_allowed
    assert any(f"global gate {state.value}" in r for r in verdict.reasons)


def test_the_kill_switch_the_execution_health_and_the_controller_each_deny() -> None:
    assert "kill switch" in _risk(kill="operator stop").authorize(_ctx()).reasons[0]
    assert "execution: order x in UNKNOWN" in _risk(health="order x in UNKNOWN state").authorize(_ctx()).reasons[0]
    hard = _risk().authorize(_ctx(allowance=_allowance(allowed=False, reason="daily loss reached", kill=True)))
    assert hard.denied and "risk controller: daily loss reached" in hard.reasons[0]
    # A pacing-only denial belongs to the engine's HOLD rule and is not a denial here.
    pacing = _risk().authorize(_ctx(allowance=_allowance(allowed=False, hold_only=True, reason="120 quotes in the last minute")))
    assert pacing.verdict is Verdict.ALLOW


def test_the_activation_denies_when_invalid_or_about_to_expire_and_allows_with_time_left() -> None:
    expired = _risk(activation=ActivationView(False, 0.0, "expired at noon")).authorize(_ctx())
    assert expired.denied and "activation: expired at noon" in expired.reasons[0]
    soon = _risk(activation=ActivationView(True, 60.0)).authorize(_ctx())
    assert soon.denied and "expires in 60 s" in soon.reasons[0] and "cancelled while the token is still valid" in soon.reasons[0]
    fine = _risk(activation=ActivationView(True, 600.0)).authorize(_ctx())
    assert fine.verdict is Verdict.ALLOW and fine.components["activation_seconds_remaining"] == 600.0
    never = _risk(activation=ActivationView(True, None, "simulated venue")).authorize(_ctx())
    assert never.verdict is Verdict.ALLOW


def test_inventory_at_a_limit_is_reduce_only_on_the_reducing_side() -> None:
    verdict = _risk().authorize(_ctx(allowance=_allowance(bid=False, ask=True, reason="inventory at a limit: reducing side only"), inventory=0.05))
    assert verdict.verdict is Verdict.REDUCE_ONLY and not verdict.bid_allowed and verdict.ask_allowed
    assert "inventory or notional at a limit" in verdict.reasons[0]


def test_the_capital_ceiling_caps_the_size_and_turns_reduce_only_when_reached() -> None:
    room = _risk(cap=1_500.0).authorize(_ctx(inventory=0.01, mark=100_000.0))  # exposure 1000 of 1500
    assert room.verdict is Verdict.ALLOW and room.max_size_btc == pytest.approx(0.005) and room.components["exposure_usd"] == 1_000.0
    reached = _risk(cap=500.0).authorize(_ctx(inventory=0.01, mark=100_000.0))
    assert reached.verdict is Verdict.REDUCE_ONLY and not reached.bid_allowed and reached.ask_allowed
    assert "capital cap 500.00 USD reached" in reached.reasons[0]
    flat = _risk(cap=0.0).authorize(_ctx(inventory=0.0))
    assert flat.denied and "no side may quote" in flat.reasons[0]


def test_real_balances_remove_the_side_they_cannot_fund_and_cap_the_other() -> None:
    no_cash = _risk().authorize(_ctx(cash=0.0, base=0.05))
    assert no_cash.verdict is Verdict.REDUCE_ONLY and not no_cash.bid_allowed and no_cash.ask_allowed and no_cash.max_size_btc == 0.01
    small = _risk().authorize(_ctx(cash=300.0, base=0.002))
    assert small.verdict is Verdict.ALLOW and small.max_size_btc == pytest.approx(0.002)  # min(0.01, 300/100000, 0.002)
    nothing = _risk().authorize(_ctx(cash=0.0, base=0.0))
    assert nothing.denied and "no side may quote" in nothing.reasons[0]


def test_verdicts_are_counted() -> None:
    authorizer = _risk()
    authorizer.authorize(_ctx())
    authorizer.authorize(_ctx(gate=_gate_status(SafetyState.HALTED, "x")))
    authorizer.authorize(_ctx(allowance=_allowance(bid=False)))
    assert authorizer.verdicts == {Verdict.ALLOW: 1, Verdict.REDUCE_ONLY: 1, Verdict.DENY: 1}


# ------------------------------------------------------------------ economics stage


def _fv(value: float = 100_000.0) -> FairValueEstimate:
    return FairValueEstimate(T0, value, value, 0.0, 0.9, {}, 0.0)


def _decision(bid: float | None, ask: float | None, size: float = 0.001) -> QuoteDecision:
    return QuoteDecision(T0, bid, ask, size if bid else 0.0, size if ask else 0.0, size, 1.0, 0.5, 100_000.0, 0.9, "test", 1_000)


def _econ(config: EconomicsConfig | None = None, *, fee: float = 0.5, taker: float = 1.0) -> MMEconomicsAuthorizer:
    return MMEconomicsAuthorizer(config, maker_fee_bps=lambda: fee, taker_fee_bps=lambda: taker, max_inventory_btc=0.05)


def _econ_ctx(decision: QuoteDecision, *, vol: float | None = 0.0, toxicity: ToxicityReading | None = None) -> AuthorizationContext:
    return _ctx(stage="economics", features=_features(spread_bps=1.0, vol_5s=vol), fair_value=_fv(), decision=decision, toxicity=toxicity)


def test_each_side_is_priced_and_only_the_sides_that_clear_the_floor_are_allowed() -> None:
    # bid 0.5 bps from fair value pays the whole 0.5 bps fee: nothing left after the unwind term.
    verdict = _econ().authorize(_econ_ctx(_decision(99_995.0, 100_010.0)))
    assert verdict.verdict is Verdict.ALLOW and not verdict.bid_allowed and verdict.ask_allowed
    sides = verdict.components["sides"]
    assert sides["bid"]["capture_bps"] == pytest.approx(0.5) and sides["bid"]["fee_bps"] == 0.5 and sides["bid"]["net_bps"] < 0
    assert sides["ask"]["capture_bps"] == pytest.approx(1.0) and sides["ask"]["net_bps"] > 0 and sides["ask"]["allowed"]
    for key in ("capture_bps", "fee_bps", "adverse_bps", "inventory_cost_bps", "unwind_bps", "latency_risk_bps", "requote_cost_bps", "net_bps"):
        assert key in sides["bid"]
    assert verdict.reasons[0].startswith("bid: net") and "below the +0.000 bps floor" in verdict.reasons[0]
    assert "not measured yet" in verdict.components["adverse_source"]


def test_a_higher_floor_or_measured_adverse_selection_denies_both_sides() -> None:
    floor = _econ(EconomicsConfig(min_net_edge_bps=1.0)).authorize(_econ_ctx(_decision(99_995.0, 100_010.0)))
    assert floor.denied and not floor.bid_allowed and not floor.ask_allowed and len(floor.reasons) == 2
    measured = ToxicityReading(score=0.8, adverse_mean_bps=2.0, samples=25, widen_bps=0.0, size_factor=1.0, reason="")
    adverse = _econ().authorize(_econ_ctx(_decision(99_995.0, 100_010.0), toxicity=measured))
    assert adverse.denied and adverse.components["sides"]["ask"]["adverse_bps"] == 2.0 and "measured over 25" in adverse.components["adverse_source"]
    few = ToxicityReading(score=0.8, adverse_mean_bps=2.0, samples=5, widen_bps=0.0, size_factor=1.0, reason="")
    assert _econ().authorize(_econ_ctx(_decision(99_995.0, 100_010.0), toxicity=few)).components["sides"]["ask"]["adverse_bps"] == 0.0


def test_volatility_prices_inventory_carry_and_the_orders_flight() -> None:
    calm = _econ().authorize(_econ_ctx(_decision(None, 100_010.0), vol=0.0)).components["sides"]["ask"]
    rough = _econ().authorize(_econ_ctx(_decision(None, 100_010.0), vol=3.0)).components["sides"]["ask"]
    assert calm["inventory_cost_bps"] == 0.0 and calm["latency_risk_bps"] == 0.0
    assert rough["inventory_cost_bps"] > 0 and rough["latency_risk_bps"] > 0 and rough["net_bps"] < calm["net_bps"]


def test_nothing_to_price_is_allowed_and_counted() -> None:
    authorizer = _econ()
    verdict = authorizer.authorize(_ctx(stage="economics", decision=None))
    assert verdict.verdict is Verdict.ALLOW and verdict.reasons == ("nothing to price",)
    assert authorizer.verdicts[Verdict.ALLOW] == 1


# ------------------------------------------------------------------ the engine applies them


class _Stub:
    def __init__(self, stage: str, verdict: Verdict, *, bid: bool = True, ask: bool = True, reason: str = "stub") -> None:
        self.name, self.stage, self._verdict, self._bid, self._ask, self._reason = f"stub_{stage}", stage, verdict, bid, ask, reason
        self.calls = 0

    def authorize(self, ctx: AuthorizationContext) -> Authorization:
        self.calls += 1
        assert ctx.stage == self.stage
        return Authorization(self.name, self.stage, self._verdict, (self._reason,), self._bid, self._ask)


def _run(authorizers: tuple[Any, ...]) -> MarketMakerEngine:
    engine = MarketMakerEngine(_config(), latency=PROFILE.scenario("optimistic"), gate=_gate(), authorizers=authorizers)
    for kind, event, t in _tape(6):
        engine.on_event(kind, event, t)
    return engine


def test_a_risk_denial_blocks_at_the_authorization_layer_and_is_journaled() -> None:
    stub = _Stub("risk", Verdict.DENY, bid=False, ask=False, reason="token expired")
    engine = _run((stub,))
    assert stub.calls >= 1 and engine.quotes == 0 and engine.authorization_blocks >= 1
    blocks = [r for r in engine.journal if r.get("kind") == "block"]
    assert blocks and blocks[0]["layer"] == "authorization" and "stub_risk: token expired" in blocks[0]["reason"]
    assert engine.last_authorizations[0]["verdict"] == "deny"
    assert engine.snapshot()["authorization_blocks"] == engine.authorization_blocks


def test_reduce_only_keeps_one_side_and_the_decision_row_carries_the_verdict() -> None:
    engine = _run((_Stub("risk", Verdict.REDUCE_ONLY, bid=False, ask=True, reason="inventory at a limit"),))
    quotes = [r for r in engine.journal if r.get("kind") == "decision" and r.get("decision") == "quote"]
    assert quotes, "the tape should have produced at least one quote"
    assert all(r["bid"] is None and r["ask"] is not None for r in quotes)
    assert quotes[0]["authorizations"][0]["verdict"] == "reduce_only" and quotes[0]["authorizations"][0]["reasons"] == ["inventory at a limit"]


def test_economics_removes_a_side_or_the_whole_quote_after_quoting() -> None:
    one_side = _run((_Stub("economics", Verdict.ALLOW, bid=True, ask=False, reason="ask: net -0.2 bps"),))
    quotes = [r for r in one_side.journal if r.get("kind") == "decision" and r.get("decision") == "quote"]
    assert quotes and all(r["ask"] is None and r["bid"] is not None for r in quotes)
    assert "economics removed a side" in quotes[0]["reason"] and one_side.authorization_side_removals >= 1
    none = _run((_Stub("economics", Verdict.DENY, bid=False, ask=False, reason="both sides negative"),))
    assert none.quotes == 0
    rows = [r for r in none.journal if r.get("kind") == "decision"]
    assert rows and rows[0]["decision"] == "no_quote" and rows[0]["reason"].startswith("economics: stub_economics: both sides negative")
    assert none.no_quote_reasons.get("economics", 0) >= 1


def test_the_engine_reports_its_execution_mode_and_an_allowing_stack_quotes_normally() -> None:
    engine = _run((_Stub("risk", Verdict.ALLOW), _Stub("economics", Verdict.ALLOW)))
    assert engine.quotes >= 1 and engine.snapshot()["execution_mode"] == "paper"
    quote = next(r for r in engine.journal if r.get("kind") == "decision" and r.get("decision") == "quote")
    assert [a["stage"] for a in quote["authorizations"]] == ["risk", "economics"]
