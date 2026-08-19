"""The Mentor: tighten-only proposals, gated by counterfactual replay.

The properties that make it safe to have at all: it proposes nothing when the record is
healthy; every proposal it does make tightens risk (never loosens); each ships with a
replay verdict computed from the recorded trades; and a proposal whose replay shows no
benefit is REJECTED and visibly so — the Mentor's failures are part of its report.
"""

from __future__ import annotations

from tia.learning.mentor import MentorEngine, ProposalStatus

TIGHTEN_ONLY_CATALOG = {
    "raise_ev_threshold",
    "halt_new_entries",
    "switch_profile_conservative",
}


def _lessons(*, expected: float, realised: float, n: int) -> list[dict]:
    return [
        {"expected_net_bps": expected, "realised_net_bps": realised, "fees_bps": 4.0}
        for _ in range(n)
    ]


def _by_kind(proposals, kind):  # type: ignore[no-untyped-def]
    return next((p for p in proposals if p.kind == kind), None)


# ------------------------------------------------------------------ healthy record


def test_a_healthy_record_produces_no_proposals() -> None:
    proposals = MentorEngine().review(
        lessons=_lessons(expected=15.0, realised=16.0, n=20),
        current_threshold_bps=5.0,
    )
    assert proposals == []


def test_a_thin_record_produces_no_proposals_however_bad_it_looks() -> None:
    """Two catastrophic trades are variance, not a mandate."""
    proposals = MentorEngine().review(
        lessons=_lessons(expected=20.0, realised=-80.0, n=2),
        current_threshold_bps=5.0,
    )
    assert proposals == []


# ------------------------------------------------------------------ the catalog is closed


def test_every_proposal_belongs_to_the_tighten_only_catalog() -> None:
    proposals = MentorEngine().review(
        lessons=_lessons(expected=20.0, realised=-30.0, n=15),
        current_threshold_bps=5.0,
        consecutive_losses=8,
        audit_checks=[{"key": "negative_edge", "severity": "alert"}],
    )
    assert proposals, "a record this bad must produce proposals"
    for proposal in proposals:
        assert proposal.kind in TIGHTEN_ONLY_CATALOG
        if proposal.kind == "raise_ev_threshold":
            assert proposal.action["to_bps"] > proposal.action["from_bps"]


# ------------------------------------------------------------------ threshold raise


def test_systematic_overestimation_proposes_a_higher_bar_and_replay_validates_it() -> None:
    # Expected +20, realised -30: mean error -50 bps. The raised bar refuses trades whose
    # expectation sat below it — all of them here — and those trades lost money, so the
    # replay confirms the benefit.
    proposals = MentorEngine().review(
        lessons=_lessons(expected=20.0, realised=-30.0, n=10),
        current_threshold_bps=5.0,
    )
    proposal = _by_kind(proposals, "raise_ev_threshold")
    assert proposal is not None
    assert proposal.status is ProposalStatus.VALIDATED
    assert proposal.validation.delta_bps == 300.0  # 10 trades x 30 bps saved
    assert proposal.validation.trades_affected == 10
    assert proposal.action["to_bps"] <= 5.0 + 20.0  # increment is capped


def test_a_raise_that_would_only_have_skipped_winners_is_rejected() -> None:
    """The arithmetic gate in action: the trigger fires (estimates run hot) but the trades
    the higher bar would refuse actually made money — so the replay rejects the change."""
    # Error -6 bps triggers the proposal and lifts the bar to 11, above these trades'
    # expected 10 — so the replay skips them. But they netted +4 each, so skipping them
    # would have cost money, and the arithmetic refuses the change.
    proposals = MentorEngine(calibration_trigger_bps=-5.0).review(
        lessons=_lessons(expected=10.0, realised=4.0, n=10),
        current_threshold_bps=5.0,
    )
    proposal = _by_kind(proposals, "raise_ev_threshold")
    assert proposal is not None
    assert proposal.status is ProposalStatus.REJECTED
    assert "would not have helped" in proposal.validation.detail


# ------------------------------------------------------------------ halt


def test_sustained_losses_propose_a_halt_and_replay_shows_what_it_saves() -> None:
    proposals = MentorEngine().review(
        lessons=_lessons(expected=10.0, realised=-12.0, n=12),
        current_threshold_bps=5.0,
    )
    proposal = _by_kind(proposals, "halt_new_entries")
    assert proposal is not None
    assert proposal.status is ProposalStatus.VALIDATED
    assert proposal.validation.delta_bps == 144.0  # 12 x 12 bps not lost


def test_no_halt_is_proposed_while_the_record_is_profitable() -> None:
    proposals = MentorEngine().review(
        lessons=_lessons(expected=10.0, realised=12.0, n=12),
        current_threshold_bps=5.0,
    )
    assert _by_kind(proposals, "halt_new_entries") is None


# ------------------------------------------------------------------ profile step-down


def test_a_long_losing_streak_proposes_conservative_and_cites_the_streak() -> None:
    proposals = MentorEngine().review(
        lessons=_lessons(expected=10.0, realised=-10.0, n=10),
        current_threshold_bps=5.0,
        consecutive_losses=6,
        risk_profile="balanced",
    )
    proposal = _by_kind(proposals, "switch_profile_conservative")
    assert proposal is not None
    assert proposal.status is ProposalStatus.VALIDATED
    assert proposal.applies == "next_session"  # profile changes never land mid-session
    assert "6 consecutive" in proposal.rationale


def test_already_conservative_means_no_profile_proposal() -> None:
    proposals = MentorEngine().review(
        lessons=_lessons(expected=10.0, realised=-10.0, n=10),
        current_threshold_bps=5.0,
        consecutive_losses=8,
        risk_profile="conservative",
    )
    assert _by_kind(proposals, "switch_profile_conservative") is None


# ------------------------------------------------------------------ determinism


def test_the_same_record_produces_the_same_proposals() -> None:
    kwargs = {
        "lessons": _lessons(expected=20.0, realised=-30.0, n=10),
        "current_threshold_bps": 5.0,
        "consecutive_losses": 6,
    }
    first = [p.as_dict() for p in MentorEngine().review(**kwargs)]
    second = [p.as_dict() for p in MentorEngine().review(**kwargs)]
    assert first == second
