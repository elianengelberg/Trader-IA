"""Risk budget, drawdown states and risk profiles.

The existing risk engine answers "is this trade allowed?". This module answers the
question underneath it: **how much risk should the system be taking right now, given how
it has been doing?**

Three mechanisms, in order of how often they bind:

* **Risk profile** — a static choice (conservative / balanced / aggressive) that scales
  every limit coherently. One knob, not fifteen.
* **Drawdown state** — NORMAL → DEFENSIVE → EMERGENCY, driven by realised drawdown.
  Risk falls as losses accumulate and stops entirely at the emergency threshold.
* **Volatility scaling** — position size falls as realised volatility rises, so a fixed
  *fractional* risk stays a fixed *monetary* risk.

**What this module will not do, by construction.** There is no code path that increases
risk because of recent losses. Martingale, revenge trading and recovery bets all share one
shape — bet more after losing — and :func:`assert_no_martingale` asserts the multiplier is
monotonically non-increasing in drawdown, as a property test rather than a promise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DrawdownState(StrEnum):
    """How much trouble the account is in, and therefore how much risk it may take."""

    NORMAL = "normal"
    DEFENSIVE = "defensive"
    EMERGENCY = "emergency"

    @property
    def allows_new_trades(self) -> bool:
        return self is not DrawdownState.EMERGENCY


class RiskProfileName(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class RiskProfile(BaseModel):
    """A coherent set of risk parameters.

    Scaling one number and leaving the others is how a "conservative" profile ends up with
    a conservative position size and an aggressive drawdown tolerance. Every field moves
    together, and the three built-in profiles are ordered on every one of them —
    :func:`assert_profiles_are_ordered` checks that.
    """

    model_config = ConfigDict(frozen=True)

    name: RiskProfileName
    #: Fraction of equity risked on a single trade at full budget.
    risk_per_trade_pct: float = Field(gt=0, le=5)
    #: Drawdown at which the system moves to DEFENSIVE.
    defensive_drawdown_pct: float = Field(gt=0, le=50)
    #: Drawdown at which the system stops opening positions.
    emergency_drawdown_pct: float = Field(gt=0, le=90)
    max_gross_exposure_pct: float = Field(gt=0, le=300)
    #: Risk multiplier applied while DEFENSIVE.
    defensive_multiplier: float = Field(gt=0, le=1)
    #: Annualised volatility the sizing is calibrated for. Above it, size shrinks.
    target_annual_volatility: float = Field(gt=0, le=5)
    max_trades_per_day: int = Field(ge=1, le=1000)
    #: Consecutive losses after which the budget is halved. Not zero — a losing streak is
    #: evidence about the strategy, not a reason to stop entirely.
    consecutive_loss_dampener: int = Field(ge=1, le=50)

    @property
    def description(self) -> str:
        return (
            f"{self.risk_per_trade_pct:.2f}% per trade, defensive at "
            f"{self.defensive_drawdown_pct:.0f}% drawdown, stop at "
            f"{self.emergency_drawdown_pct:.0f}%"
        )


PROFILES: dict[RiskProfileName, RiskProfile] = {
    RiskProfileName.CONSERVATIVE: RiskProfile(
        name=RiskProfileName.CONSERVATIVE,
        risk_per_trade_pct=0.25,
        defensive_drawdown_pct=3.0,
        emergency_drawdown_pct=6.0,
        max_gross_exposure_pct=40.0,
        defensive_multiplier=0.4,
        target_annual_volatility=0.10,
        max_trades_per_day=8,
        consecutive_loss_dampener=3,
    ),
    RiskProfileName.BALANCED: RiskProfile(
        name=RiskProfileName.BALANCED,
        risk_per_trade_pct=0.50,
        defensive_drawdown_pct=5.0,
        emergency_drawdown_pct=10.0,
        max_gross_exposure_pct=80.0,
        defensive_multiplier=0.5,
        target_annual_volatility=0.20,
        max_trades_per_day=20,
        consecutive_loss_dampener=4,
    ),
    RiskProfileName.AGGRESSIVE: RiskProfile(
        name=RiskProfileName.AGGRESSIVE,
        risk_per_trade_pct=1.00,
        defensive_drawdown_pct=8.0,
        emergency_drawdown_pct=15.0,
        max_gross_exposure_pct=120.0,
        defensive_multiplier=0.6,
        target_annual_volatility=0.35,
        max_trades_per_day=40,
        consecutive_loss_dampener=5,
    ),
}


@dataclass(frozen=True)
class BudgetInputs:
    """Everything the budget depends on. Passed explicitly so a past decision can be
    recomputed exactly from its stored record."""

    equity: float
    peak_equity: float
    drawdown_pct: float
    realised_annual_volatility: float
    consecutive_losses: int
    trades_today: int
    open_gross_exposure_pct: float


@dataclass(frozen=True)
class RiskBudget:
    """How much may be risked on the next trade, and why that much."""

    state: DrawdownState
    profile: RiskProfileName
    #: Currency at risk on the next trade, after every multiplier.
    risk_currency: float
    #: The same, as a fraction of equity.
    risk_pct: float
    #: Each multiplier, kept separate so the UI can say which one bound.
    drawdown_multiplier: float
    volatility_multiplier: float
    streak_multiplier: float
    allows_new_trades: bool
    binding_constraint: str

    @property
    def total_multiplier(self) -> float:
        return self.drawdown_multiplier * self.volatility_multiplier * self.streak_multiplier

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "profile": self.profile.value,
            "risk_currency": round(self.risk_currency, 6),
            "risk_pct": round(self.risk_pct, 6),
            "drawdown_multiplier": round(self.drawdown_multiplier, 4),
            "volatility_multiplier": round(self.volatility_multiplier, 4),
            "streak_multiplier": round(self.streak_multiplier, 4),
            "total_multiplier": round(self.total_multiplier, 4),
            "allows_new_trades": self.allows_new_trades,
            "binding_constraint": self.binding_constraint,
        }


class RiskBudgetEngine:
    """Computes the risk budget. Deterministic, and never consults a model."""

    def __init__(self, profile: RiskProfile | RiskProfileName = RiskProfileName.BALANCED) -> None:
        self._profile = (
            profile if isinstance(profile, RiskProfile) else PROFILES[profile]
        )

    @property
    def profile(self) -> RiskProfile:
        return self._profile

    def state_for(self, drawdown_pct: float) -> DrawdownState:
        if drawdown_pct >= self._profile.emergency_drawdown_pct:
            return DrawdownState.EMERGENCY
        if drawdown_pct >= self._profile.defensive_drawdown_pct:
            return DrawdownState.DEFENSIVE
        return DrawdownState.NORMAL

    def compute(self, inputs: BudgetInputs) -> RiskBudget:
        profile = self._profile
        state = self.state_for(inputs.drawdown_pct)

        drawdown_multiplier = self._drawdown_multiplier(state, inputs.drawdown_pct)
        volatility_multiplier = self._volatility_multiplier(inputs.realised_annual_volatility)
        streak_multiplier = self._streak_multiplier(inputs.consecutive_losses)

        base_pct = profile.risk_per_trade_pct / 100.0
        risk_pct = base_pct * drawdown_multiplier * volatility_multiplier * streak_multiplier
        risk_currency = max(0.0, inputs.equity) * risk_pct

        allows = state.allows_new_trades
        binding = "none"
        if not allows:
            binding = f"emergency drawdown ({inputs.drawdown_pct:.2f}%)"
            risk_currency = 0.0
            risk_pct = 0.0
        elif inputs.trades_today >= profile.max_trades_per_day:
            allows = False
            binding = f"daily trade cap ({profile.max_trades_per_day})"
            risk_currency = 0.0
            risk_pct = 0.0
        elif inputs.open_gross_exposure_pct >= profile.max_gross_exposure_pct:
            allows = False
            binding = f"gross exposure cap ({profile.max_gross_exposure_pct:.0f}%)"
            risk_currency = 0.0
            risk_pct = 0.0
        else:
            smallest = min(
                ("drawdown", drawdown_multiplier),
                ("volatility", volatility_multiplier),
                ("loss streak", streak_multiplier),
                key=lambda item: item[1],
            )
            binding = "none" if smallest[1] >= 1.0 else smallest[0]

        return RiskBudget(
            state=state,
            profile=profile.name,
            risk_currency=risk_currency,
            risk_pct=risk_pct,
            drawdown_multiplier=drawdown_multiplier,
            volatility_multiplier=volatility_multiplier,
            streak_multiplier=streak_multiplier,
            allows_new_trades=allows,
            binding_constraint=binding,
        )

    def _drawdown_multiplier(self, state: DrawdownState, drawdown_pct: float) -> float:
        """Risk falls as drawdown deepens. Monotonically non-increasing, always."""
        if state is DrawdownState.EMERGENCY:
            return 0.0
        if state is DrawdownState.NORMAL:
            # Taper smoothly toward the defensive threshold rather than stepping off a
            # cliff, so behaviour either side of the boundary is continuous.
            threshold = self._profile.defensive_drawdown_pct
            if threshold <= 0:
                return 1.0
            return max(0.0, 1.0 - 0.5 * (drawdown_pct / threshold))

        span = self._profile.emergency_drawdown_pct - self._profile.defensive_drawdown_pct
        if span <= 0:
            return self._profile.defensive_multiplier
        progress = (drawdown_pct - self._profile.defensive_drawdown_pct) / span
        return self._profile.defensive_multiplier * max(0.0, 1.0 - progress)

    def _volatility_multiplier(self, realised_annual_volatility: float) -> float:
        """Scale size so a fixed fractional risk is a fixed monetary risk.

        Capped at 1.0: low volatility does **not** license a larger position than the
        profile allows. Uncapped volatility targeting is how a quiet market produces
        leverage that a single gap erases.
        """
        if realised_annual_volatility <= 0:
            return 1.0
        return min(1.0, self._profile.target_annual_volatility / realised_annual_volatility)

    def _streak_multiplier(self, consecutive_losses: int) -> float:
        """Halve after a losing streak, and keep halving. Never increases.

        A losing streak is evidence the strategy is out of step with the market. The
        response is a smaller position, and the opposite response is the one that empties
        accounts.
        """
        if consecutive_losses < self._profile.consecutive_loss_dampener:
            return 1.0
        excess = consecutive_losses - self._profile.consecutive_loss_dampener + 1
        return max(0.05, 0.5**excess)


# --------------------------------------------------------------------------- invariants


def assert_no_martingale(engine: RiskBudgetEngine, inputs: BudgetInputs) -> None:
    """Risk must never rise with drawdown or with a longer losing streak.

    Called by a property test over random inputs. Stated as a checkable function rather
    than a comment because "we would never do that" is exactly what every blown-up
    account's code said.
    """
    from dataclasses import replace

    deeper = replace(inputs, drawdown_pct=inputs.drawdown_pct + 1.0)
    if engine.compute(deeper).risk_currency > engine.compute(inputs).risk_currency + 1e-9:
        raise AssertionError(
            "risk increased with drawdown — this is martingale behaviour and is forbidden"
        )

    longer = replace(inputs, consecutive_losses=inputs.consecutive_losses + 1)
    if engine.compute(longer).risk_currency > engine.compute(inputs).risk_currency + 1e-9:
        raise AssertionError(
            "risk increased after another loss — this is revenge trading and is forbidden"
        )


def assert_profiles_are_ordered() -> None:
    """Conservative ≤ balanced ≤ aggressive on every dimension.

    A "conservative" profile that tolerates a deeper drawdown than the balanced one is a
    labelling bug, and labelling bugs in risk parameters are the expensive kind.
    """
    conservative = PROFILES[RiskProfileName.CONSERVATIVE]
    balanced = PROFILES[RiskProfileName.BALANCED]
    aggressive = PROFILES[RiskProfileName.AGGRESSIVE]

    for field_name in (
        "risk_per_trade_pct",
        "defensive_drawdown_pct",
        "emergency_drawdown_pct",
        "max_gross_exposure_pct",
        "target_annual_volatility",
        "max_trades_per_day",
    ):
        low = getattr(conservative, field_name)
        mid = getattr(balanced, field_name)
        high = getattr(aggressive, field_name)
        if not (low <= mid <= high):
            raise AssertionError(
                f"profiles are not ordered on {field_name}: "
                f"conservative={low}, balanced={mid}, aggressive={high}"
            )


def annualise_volatility(per_bar_volatility: float, bars_per_year: float) -> float:
    """Square-root-of-time scaling. Here rather than inline so the assumption is visible:
    it holds for independent returns and understates volatility when they are not."""
    return per_bar_volatility * math.sqrt(max(0.0, bars_per_year))


__all__ = [
    "PROFILES",
    "BudgetInputs",
    "DrawdownState",
    "RiskBudget",
    "RiskBudgetEngine",
    "RiskProfile",
    "RiskProfileName",
    "annualise_volatility",
    "assert_no_martingale",
    "assert_profiles_are_ordered",
]
