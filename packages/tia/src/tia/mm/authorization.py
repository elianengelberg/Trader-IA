"""Authorization of a quote, in two stages, each with an explicit verdict and its reasons.

The engine's hierarchy is unchanged: data validity, the global safety gate, the maker's own
risk controller, then quoting. Authorizers sit *inside* that hierarchy as extra readers,
never as a bypass: they can only remove something the layers above allowed. In paper mode
the engine carries no authorizer and this module is not consulted at all, so the paper
journal is byte for byte what it was.

* **Risk** (before quoting): the global gate's word restated, the market maker's kill
  switch, the health of the execution path (an order in an UNKNOWN state blocks every new
  one), the activation token's validity with a margin before expiry, the controller's
  allowance, the real balances and the capital ceiling the activation granted. Verdicts:
  ``ALLOW``, ``REDUCE_ONLY`` (only the side that reduces inventory may quote) or ``DENY``.
* **Economics** (after quoting, before sending): per side, the expected spread capture
  of the quote against the fair value minus the maker fee, the adverse selection the
  markouts have measured, the cost of carrying the inventory the fill would create, the
  expected cost of an unwind by taker, the price risk over the order's flight and the
  requote overhead. ``ALLOW`` or ``DENY`` per side, every component in the journal.

None of this calls the session's ``RiskEngine.evaluate`` with an invented directional
signal, and none of it builds a fake long or short for the ``ExpectedValueEngine``: a
quote is two resting orders, and it is priced as what it is.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from tia.mm.fair_value import FairValueEstimate
from tia.mm.features import FeatureVector
from tia.mm.inventory import InventoryState
from tia.mm.latency_model import LatencyScenario
from tia.mm.quoting import QuoteDecision
from tia.mm.risk import LedgerView, RiskAllowance
from tia.mm.safety import SafetyStatus
from tia.mm.spread import SpreadDecision
from tia.mm.toxicity import ToxicityReading


class Verdict(StrEnum):
    ALLOW = "allow"
    REDUCE_ONLY = "reduce_only"
    DENY = "deny"


@dataclass(frozen=True)
class Authorization:
    authorizer: str
    stage: str
    verdict: Verdict
    reasons: tuple[str, ...]
    bid_allowed: bool
    ask_allowed: bool
    #: A ceiling on the size of a new order, when the authorizer imposes one.
    max_size_btc: float | None = None
    components: dict[str, Any] = field(default_factory=dict)

    @property
    def denied(self) -> bool:
        return self.verdict is Verdict.DENY

    def as_dict(self) -> dict[str, Any]:
        return {
            "authorizer": self.authorizer,
            "stage": self.stage,
            "verdict": self.verdict.value,
            "reasons": list(self.reasons),
            "bid_allowed": self.bid_allowed,
            "ask_allowed": self.ask_allowed,
            "max_size_btc": self.max_size_btc,
            "components": self.components,
        }


@dataclass(frozen=True)
class AuthorizationContext:
    """Everything an authorizer may read. It is handed values, never engines."""

    t_ms: int
    stage: str
    gate: SafetyStatus
    allowance: RiskAllowance
    ledger: LedgerView
    latency: LatencyScenario
    #: Real balances when the ledger knows them (live); None in paper.
    cash_usd: float | None = None
    base_balance_btc: float | None = None
    features: FeatureVector | None = None
    fair_value: FairValueEstimate | None = None
    inventory: InventoryState | None = None
    spread: SpreadDecision | None = None
    toxicity: ToxicityReading | None = None
    decision: QuoteDecision | None = None


class QuoteAuthorizer(Protocol):
    name: str
    stage: str

    def authorize(self, ctx: AuthorizationContext) -> Authorization: ...


@dataclass(frozen=True)
class ActivationView:
    """What the risk authorizer is told about the activation token: a reading, not the
    token. ``valid`` False means no live order may be sent; ``seconds_remaining`` None
    means the token does not expire (a simulated venue holds none)."""

    valid: bool
    seconds_remaining: float | None
    detail: str = ""


# ---------------------------------------------------------------------------- risk


class MMRiskAuthorizer:
    """ALLOW / REDUCE_ONLY / DENY from conditions the layers above already decided, the
    activation, the execution path's health and the real balances. Reads everything
    through callables so it holds no engine and can change nothing."""

    name = "mm_risk"
    stage = "risk"

    def __init__(
        self,
        *,
        capital_cap_usd: Callable[[], float | None],
        activation: Callable[[int], ActivationView] | None = None,
        execution_health: Callable[[], str] | None = None,
        kill_switch: Callable[[], str] | None = None,
        expiry_margin_s: float = 120.0,
    ) -> None:
        self._capital_cap_usd = capital_cap_usd
        self._activation = activation
        self._execution_health = execution_health or (lambda: "")
        self._kill_switch = kill_switch or (lambda: "")
        self._expiry_margin_s = expiry_margin_s
        self.verdicts = {Verdict.ALLOW: 0, Verdict.REDUCE_ONLY: 0, Verdict.DENY: 0}

    def authorize(self, ctx: AuthorizationContext) -> Authorization:
        deny: list[str] = []
        reduce: list[str] = []
        components: dict[str, Any] = {}

        # 1. The global gate, restated. The engine consulted it already; the verdict is
        #    written down here so an authorization row never shows ALLOW under a closed gate.
        if not ctx.gate.allows_quoting:
            deny.append(f"global gate {ctx.gate.state.value}: {ctx.gate.reason}")
        # 2. The market maker's own kill switch.
        kill = self._kill_switch()
        if kill:
            deny.append(f"market maker kill switch: {kill}")
        # 3. The execution path: an order in an UNKNOWN state, excessive API errors, a
        #    refused activation — nothing new is sent until it is resolved.
        health = self._execution_health()
        if health:
            deny.append(f"execution: {health}")
        # 4. The activation token, with a margin: resting orders are cancelled while the
        #    token can still authorise the cancel.
        if self._activation is not None:
            view = self._activation(ctx.t_ms)
            components["activation_seconds_remaining"] = view.seconds_remaining
            if not view.valid:
                deny.append(f"activation: {view.detail or 'not valid'}")
            elif view.seconds_remaining is not None and view.seconds_remaining <= self._expiry_margin_s:
                deny.append(
                    f"activation expires in {view.seconds_remaining:.0f} s, inside the {self._expiry_margin_s:.0f} s margin: "
                    "no new orders, resting ones are cancelled while the token is still valid"
                )
        # 5. The controller. A pacing-only denial is the engine's HOLD rule, not a denial here.
        allowance = ctx.allowance
        if not allowance.allowed and not allowance.hold_only:
            deny.append(f"risk controller: {allowance.reason}")
        bid_ok, ask_ok = allowance.bid_allowed, allowance.ask_allowed
        if (bid_ok or ask_ok) and not (bid_ok and ask_ok):
            reduce.append(f"inventory or notional at a limit: {allowance.reason}")
        max_size = allowance.max_size_btc
        mark = ctx.ledger.mark_price
        inventory = ctx.ledger.inventory_btc

        # 6. The capital ceiling the activation granted: exposure may not grow past it.
        cap = self._capital_cap_usd()
        components["capital_cap_usd"] = cap
        if cap is not None and mark > 0:
            exposure = abs(inventory) * mark
            components["exposure_usd"] = round(exposure, 6)
            room = cap - exposure
            if room <= 0:
                reduce.append(f"capital cap {cap:.2f} USD reached by exposure {exposure:.2f} USD: reducing side only")
                bid_ok, ask_ok = bid_ok and inventory < 0, ask_ok and inventory > 0
            else:
                max_size = min(max_size, room / mark)
        # 7. Real balances: a bid needs the quote currency, an ask needs the base asset.
        if ctx.cash_usd is not None and mark > 0:
            affordable = max(0.0, ctx.cash_usd) / mark
            components["cash_usd"] = ctx.cash_usd
            if affordable <= 0 and bid_ok:
                bid_ok = False
                reduce.append("no quote currency available for a bid")
            elif bid_ok:
                max_size = min(max_size, affordable)
        if ctx.base_balance_btc is not None:
            components["base_balance_btc"] = ctx.base_balance_btc
            if ctx.base_balance_btc <= 0 and ask_ok:
                ask_ok = False
                reduce.append("no base asset available for an ask")
            elif ask_ok:
                max_size = min(max_size, ctx.base_balance_btc)
        if not deny and not (bid_ok or ask_ok):
            deny.append("no side may quote: " + "; ".join(reduce or ["nothing allowed"]))

        verdict = Verdict.DENY if deny else (Verdict.REDUCE_ONLY if reduce else Verdict.ALLOW)
        self.verdicts[verdict] += 1
        return Authorization(
            authorizer=self.name,
            stage=self.stage,
            verdict=verdict,
            reasons=tuple(deny + reduce) if (deny or reduce) else ("within every limit",),
            bid_allowed=bid_ok and not deny,
            ask_allowed=ask_ok and not deny,
            max_size_btc=max_size,
            components=components,
        )


# ---------------------------------------------------------------------------- economics


@dataclass(frozen=True)
class EconomicsConfig:
    #: Net expected edge, in bps of notional, a side must clear to be sent. Zero means
    #: strictly non-negative expectation; nothing here claims any number is profitable.
    min_net_edge_bps: float = 0.0
    #: PROVISIONAL assumption: how long a fill's inventory is expected to be carried
    #: before the opposite quote takes it off. Prices the volatility of carrying it.
    holding_horizon_s: float = 30.0
    #: Overhead charged per quote for the cancel/replace churn (0: the venue charges none).
    requote_cost_bps: float = 0.0
    #: Below this many resolved markouts the measured adverse selection is not used
    #: (and the component is 0.0, stated as unmeasured — never invented).
    min_toxicity_samples: int = 20
    vol_window: str = "5s"

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


class MMEconomicsAuthorizer:
    """Per side: capture - fee - adverse - inventory - unwind - latency - requote ≥ floor."""

    name = "mm_economics"
    stage = "economics"

    def __init__(
        self,
        config: EconomicsConfig | None = None,
        *,
        maker_fee_bps: Callable[[], float],
        taker_fee_bps: Callable[[], float],
        max_inventory_btc: float,
    ) -> None:
        self.config = config or EconomicsConfig()
        self._maker_fee_bps = maker_fee_bps
        self._taker_fee_bps = taker_fee_bps
        self._max_inventory_btc = max(1e-12, max_inventory_btc)
        self.verdicts = {Verdict.ALLOW: 0, Verdict.DENY: 0}

    def authorize(self, ctx: AuthorizationContext) -> Authorization:
        decision, features, fv = ctx.decision, ctx.features, ctx.fair_value
        if decision is None or not decision.is_quote or features is None or fv is None:
            self.verdicts[Verdict.ALLOW] += 1
            return Authorization(self.name, self.stage, Verdict.ALLOW, ("nothing to price",), True, True)
        cfg = self.config
        fee = self._maker_fee_bps()
        taker = self._taker_fee_bps()
        vol = float(features.vol_bps.get(cfg.vol_window) or 0.0)
        tox = ctx.toxicity
        if tox is not None and tox.adverse_mean_bps is not None and tox.samples >= cfg.min_toxicity_samples:
            adverse, adverse_source = max(0.0, tox.adverse_mean_bps), f"measured over {tox.samples} markouts"
        else:
            adverse, adverse_source = 0.0, "not measured yet: no adverse selection charged (stated, not assumed)"
        latency_risk = vol * math.sqrt(max(0.0, ctx.latency.order_latency_ms) / 5_000.0)
        inventory = ctx.ledger.inventory_btc
        sides: dict[str, dict[str, Any]] = {}
        reasons: list[str] = []
        for side, price, size in (("bid", decision.bid_price, decision.bid_size), ("ask", decision.ask_price, decision.ask_size)):
            if price is None or size <= 0:
                continue
            capture = (fv.fair_value - price) / fv.fair_value * 10_000.0 if side == "bid" else (price - fv.fair_value) / fv.fair_value * 10_000.0
            after = inventory + size if side == "bid" else inventory - size
            utilisation = min(1.0, abs(after) / self._max_inventory_btc)
            inventory_cost = vol * math.sqrt(cfg.holding_horizon_s / 5.0) * utilisation
            unwind = utilisation * (features.spread_bps / 2.0 + taker)
            net = capture - fee - adverse - inventory_cost - unwind - latency_risk - cfg.requote_cost_bps
            allowed = net >= cfg.min_net_edge_bps
            sides[side] = {
                "price": price,
                "size": size,
                "capture_bps": round(capture, 4),
                "fee_bps": fee,
                "adverse_bps": round(adverse, 4),
                "inventory_cost_bps": round(inventory_cost, 4),
                "unwind_bps": round(unwind, 4),
                "latency_risk_bps": round(latency_risk, 4),
                "requote_cost_bps": cfg.requote_cost_bps,
                "net_bps": round(net, 4),
                "allowed": allowed,
            }
            if not allowed:
                reasons.append(f"{side}: net {net:+.3f} bps below the {cfg.min_net_edge_bps:+.3f} bps floor (capture {capture:.3f}, fee {fee:.3f}, adverse {adverse:.3f}, inventory {inventory_cost:.3f}, unwind {unwind:.3f}, latency {latency_risk:.3f})")
        bid_allowed = sides.get("bid", {}).get("allowed", False)
        ask_allowed = sides.get("ask", {}).get("allowed", False)
        verdict = Verdict.ALLOW if (bid_allowed or ask_allowed) else Verdict.DENY
        self.verdicts[verdict] += 1
        return Authorization(
            authorizer=self.name,
            stage=self.stage,
            verdict=verdict,
            reasons=tuple(reasons) if reasons else ("both quoted sides clear the floor",),
            bid_allowed=bid_allowed,
            ask_allowed=ask_allowed,
            components={"sides": sides, "adverse_source": adverse_source, "vol_bps": vol, "config": cfg.as_dict()},
        )


__all__ = [
    "ActivationView",
    "Authorization",
    "AuthorizationContext",
    "EconomicsConfig",
    "MMEconomicsAuthorizer",
    "MMRiskAuthorizer",
    "QuoteAuthorizer",
    "Verdict",
]
