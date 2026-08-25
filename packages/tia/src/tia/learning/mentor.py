"""The Mentor — proposes risk adjustments; the arithmetic decides if they stand.

The user asked for an AI that reviews how the system is trading and improves it. The
dangerous version of that is a model that edits risk parameters because its prose sounded
confident. This module is the honest version, built on three hard rules:

1. **Proposals come from measurements, not vibes.** Every proposal is triggered by a
   specific number crossing a specific line in the system's own record — the calibration
   error the retrospective measured, the loss streak, an alert the behaviour audit raised.
   The trigger is cited in the proposal so the reader can check it.
2. **The catalog is tighten-only.** The Mentor can propose raising the expected-value bar,
   halting new entries, or stepping the risk profile down to conservative. There is no
   proposal that loosens a limit, enlarges a size, or adds risk — the catalog is closed and
   a test asserts every proposal in it tightens.
3. **Validation is counterfactual replay, and it gates application.** Before a proposal can
   be applied, it is replayed against the recorded closed trades: "under this rule, these N
   trades would have been refused; their combined net was X bps." A proposal whose replay
   does not show the tightening would have helped is REJECTED and shown as rejected — the
   Mentor's failures are as visible as its successes. Replay is arithmetic over the trade
   record: deterministic, reproducible, and honest about being per-trade bps (it assumes
   comparable notionals, and says so).

Like the rest of this package the engine is pure — records in, proposals out, no clock, no
I/O, no model call. A language model never touches this path; if one is configured, the
read-only Advisor can *explain* the Mentor's report, but the proposals and their verdicts
are produced by this arithmetic alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ProposalStatus(StrEnum):
    #: Replay confirmed the tightening would have helped; the operator may apply it.
    VALIDATED = "validated"
    #: Replay could not confirm a benefit. Never applicable; shown so the refusal teaches.
    REJECTED = "rejected"


@dataclass(frozen=True)
class Validation:
    """What the counterfactual replay found."""

    passed: bool
    method: str
    detail: str
    #: Estimated per-trade-bps improvement had the rule been in force. Positive is better.
    delta_bps: float
    trades_affected: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "method": self.method,
            "detail": self.detail,
            "delta_bps": round(self.delta_bps, 2),
            "trades_affected": self.trades_affected,
        }


@dataclass(frozen=True)
class MentorProposal:
    """One tighten-only adjustment, with its trigger and its replay verdict attached."""

    proposal_id: str
    kind: str
    title: str
    #: Why the Mentor raised this at all — the measured trigger, in plain language.
    rationale: str
    #: The concrete parameter change, machine-readable, for the apply path.
    action: dict[str, Any]
    validation: Validation
    #: How the change lands: "immediate" acts on the running session; "next_session"
    #: (the profile change) takes effect when the next session starts, by design.
    applies: str = "immediate"

    @property
    def status(self) -> ProposalStatus:
        return ProposalStatus.VALIDATED if self.validation.passed else ProposalStatus.REJECTED

    def as_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "kind": self.kind,
            "title": self.title,
            "rationale": self.rationale,
            "action": self.action,
            "validation": self.validation.as_dict(),
            "applies": self.applies,
            "status": self.status.value,
        }


#: The replay refuses to validate anything from fewer than this many affected trades — a
#: proposal justified by two data points is a coin flip wearing a rationale.
MIN_AFFECTED_TRADES = 3

REPLAY_METHOD = (
    "counterfactual replay of the recorded closed trades (per-trade bps; assumes "
    "comparable notionals)"
)


def _typical_notional(lessons: list[dict[str, Any]]) -> float:
    """Median dollars-at-work of the lessons that carry one — 0.0 when none do."""
    notionals = sorted(
        float(item.get("notional_usd") or 0.0)
        for item in lessons
        if float(item.get("notional_usd") or 0.0) > 0
    )
    if not notionals:
        return 0.0
    mid = len(notionals) // 2
    if len(notionals) % 2:
        return notionals[mid]
    return (notionals[mid - 1] + notionals[mid]) / 2.0


def _amount(bps_value: float, notional_usd: float) -> str:
    """A bps figure spoken as dollars at the given trade size; bps when no size is known.

    Presentation only — every stored number and threshold stays in basis points.
    """
    if notional_usd > 0:
        value = bps_value * notional_usd / 10_000.0
        return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"
    return f"{bps_value:+.1f} bps"


@dataclass
class MentorEngine:
    """Reads the record, proposes tighten-only adjustments, validates each by replay."""

    #: Mean calibration error (realised minus expected) at or below this triggers the
    #: threshold-raise proposal: the system is systematically promising more than it earns.
    calibration_trigger_bps: float = -5.0
    #: Cap on how far a single proposal may raise the EV bar above its current level.
    max_threshold_increment_bps: float = 20.0
    #: Recent mean net return at or below this triggers the halt proposal.
    halt_trigger_bps: float = -5.0
    #: Loss streak at which the conservative-profile proposal fires.
    streak_trigger: int = 5
    min_affected: int = MIN_AFFECTED_TRADES

    def review(
        self,
        *,
        lessons: list[dict[str, Any]],
        current_threshold_bps: float,
        consecutive_losses: int = 0,
        risk_profile: str = "balanced",
        audit_checks: list[dict[str, Any]] | None = None,
    ) -> list[MentorProposal]:
        """Produce every proposal the record currently justifies, verdicts attached.

        ``lessons`` are the retrospective's reviews (each carries ``expected_net_bps`` and
        ``realised_net_bps``), newest first — the same rows the Learning page shows, so the
        Mentor and the operator are reading identical evidence.

        Exploration trades are dropped first. Every proposal below reasons about the
        system's *edge* — that it overestimated one, or that the market has passed
        verdict on one — and an exploration trade claimed no edge to be wrong about. Left
        in, they would have the Mentor demand a halt because the system paid the price of
        the lessons it was told to go and buy.
        """
        audit_checks = audit_checks or []
        lessons = [item for item in lessons if not item.get("exploratory")]
        proposals: list[MentorProposal] = []

        threshold = self._propose_threshold_raise(lessons, current_threshold_bps)
        if threshold is not None:
            proposals.append(threshold)

        halt = self._propose_halt(lessons, audit_checks)
        if halt is not None:
            proposals.append(halt)

        profile = self._propose_conservative_profile(
            lessons, consecutive_losses, risk_profile, audit_checks
        )
        if profile is not None:
            proposals.append(profile)

        return proposals

    # ------------------------------------------------------------------ proposals

    def _propose_threshold_raise(
        self, lessons: list[dict[str, Any]], current_bps: float
    ) -> MentorProposal | None:
        """Raise the EV bar when the system systematically overestimates its edge."""
        if len(lessons) < self.min_affected:
            return None
        errors = [
            float(item["realised_net_bps"]) - float(item["expected_net_bps"])
            for item in lessons
        ]
        mean_error = sum(errors) / len(errors)
        if mean_error > self.calibration_trigger_bps:
            return None

        increment = min(self.max_threshold_increment_bps, math.ceil(-mean_error))
        new_bps = current_bps + increment

        skipped = [
            item for item in lessons if float(item["expected_net_bps"]) < new_bps
        ]
        delta = -sum(float(item["realised_net_bps"]) for item in skipped)
        passed = len(skipped) >= self.min_affected and delta > 0
        usd = _typical_notional(lessons)
        if passed:
            detail = (
                f"With the bar at {_amount(new_bps, usd)} per trade, {len(skipped)} of the "
                f"last {len(lessons)} trades would have been refused; together they netted "
                f"{_amount(-delta, usd)}, so skipping them improves the record by "
                f"{_amount(delta, usd)}."
            )
        elif len(skipped) < self.min_affected:
            detail = (
                f"Only {len(skipped)} recorded trades would have been affected — too few "
                f"to validate the change (minimum {self.min_affected})."
            )
        else:
            detail = (
                f"The {len(skipped)} trades the higher bar would have refused netted "
                f"{_amount(-delta, usd)} combined — refusing them would not have helped."
            )

        return MentorProposal(
            proposal_id="raise_ev_threshold",
            kind="raise_ev_threshold",
            title=(
                f"Demand at least {_amount(new_bps, usd)} expected profit per trade"
                if usd > 0
                else f"Raise the expected-value bar to {new_bps:.1f} bps"
            ),
            rationale=(
                f"Across the last {len(lessons)} closed trades, realised returns averaged "
                f"{_amount(mean_error, usd)} per trade below what the system expected at "
                "entry. When the estimate runs hot, the honest correction is a larger "
                "margin of safety."
            ),
            action={
                "kind": "raise_ev_threshold",
                "from_bps": round(current_bps, 2),
                "to_bps": round(new_bps, 2),
            },
            validation=Validation(
                passed=passed,
                method=REPLAY_METHOD,
                detail=detail,
                delta_bps=delta,
                trades_affected=len(skipped),
            ),
        )

    def _propose_halt(
        self, lessons: list[dict[str, Any]], audit_checks: list[dict[str, Any]]
    ) -> MentorProposal | None:
        """Halt new entries when recent trading is losing money after costs."""
        if len(lessons) < self.min_affected:
            return None
        nets = [float(item["realised_net_bps"]) for item in lessons]
        mean_net = sum(nets) / len(nets)
        audit_alert = any(
            check.get("key") == "negative_edge" and check.get("severity") == "alert"
            for check in audit_checks
        )
        if mean_net > self.halt_trigger_bps and not audit_alert:
            return None

        delta = -sum(nets)
        passed = delta > 0
        usd = _typical_notional(lessons)
        return MentorProposal(
            proposal_id="halt_new_entries",
            kind="halt_new_entries",
            title="Halt new entries until the evidence improves",
            rationale=(
                f"The last {len(nets)} closed trades averaged {_amount(mean_net, usd)} "
                "per trade net of fees. A negative average sustained over many trades is "
                "the market's verdict on the current edge; the disciplined response is to "
                "stop paying for information the record already contains."
            ),
            action={"kind": "halt_new_entries"},
            validation=Validation(
                passed=passed,
                method=REPLAY_METHOD,
                detail=(
                    f"Had entries been halted, the {_amount(-delta, usd)} those trades "
                    "lost would not have been lost."
                    if passed
                    else f"Those trades netted {_amount(-delta, usd)} combined — halting "
                    "would have cost money, so the halt is not justified by the record."
                ),
                delta_bps=delta,
                trades_affected=len(nets),
            ),
        )

    def _propose_conservative_profile(
        self,
        lessons: list[dict[str, Any]],
        consecutive_losses: int,
        risk_profile: str,
        audit_checks: list[dict[str, Any]],
    ) -> MentorProposal | None:
        """Step the risk profile down when the streak or the audit says exposure is high."""
        if risk_profile == "conservative":
            return None
        alerts = sum(1 for check in audit_checks if check.get("severity") == "alert")
        if consecutive_losses < self.streak_trigger and alerts < 2:
            return None

        nets = [float(item["realised_net_bps"]) for item in lessons]
        total = sum(nets)
        # Conservative sizing roughly halves the risk per trade; the replay scales the
        # recorded outcomes accordingly. Approximate on purpose, and labelled as such.
        delta = -0.5 * total
        passed = len(nets) >= self.min_affected and total < 0
        usd = _typical_notional(lessons)
        if passed:
            detail = (
                f"At roughly half size, the {_amount(total, usd)} the recent trades lost "
                f"would have been about {_amount(0.5 * total, usd)}."
            )
        elif total >= 0:
            detail = (
                "Recent trades are not losing money — the record does not justify the "
                "change yet."
            )
        else:
            detail = (
                f"Only {len(nets)} recorded trades — too few to validate the change "
                f"(minimum {self.min_affected})."
            )
        return MentorProposal(
            proposal_id="switch_profile_conservative",
            kind="switch_profile_conservative",
            title="Step the risk profile down to conservative",
            rationale=(
                f"{consecutive_losses} consecutive losing trades and {alerts} audit "
                "alert(s). Smaller positions buy time for the evidence to speak without "
                "changing what the system believes."
            ),
            action={
                "kind": "switch_profile_conservative",
                "from_profile": risk_profile,
                "to_profile": "conservative",
            },
            validation=Validation(
                passed=passed,
                method=REPLAY_METHOD + "; sizing effect approximated at half risk",
                detail=detail,
                delta_bps=delta,
                trades_affected=len(nets),
            ),
            applies="next_session",
        )


__all__ = [
    "MIN_AFFECTED_TRADES",
    "MentorEngine",
    "MentorProposal",
    "ProposalStatus",
    "Validation",
]
