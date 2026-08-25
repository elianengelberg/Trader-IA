"""The retrospective engine: does it read the right lesson, and only ever tighten?

Two properties carry the weight. First, a closed trade is classified by the gap between
what it was expected to do and what it did — a loss on a positive expectation is the
serious case and must be named as such. Second, the guardrail it derives can only make the
system *more* cautious, and must ease on its own as a punished pattern comes back in line.
A retrospective that could talk the system into a trade, or that latched a penalty forever,
would be worse than none.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tia.domain.enums import Direction, MarketRegime
from tia.learning.retrospective import (
    Guardrail,
    LessonCategory,
    RetrospectiveEngine,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _review(engine: RetrospectiveEngine, *, expected: float, realised: float, i: int = 0,
            regime: MarketRegime = MarketRegime.TRENDING_UP,
            direction: Direction = Direction.LONG, confidence: float = 0.8,
            fees: float = 6.0, expected_cost: float | None = None):
    return engine.review(
        regime=regime,
        direction=direction,
        confidence=confidence,
        expected_net_bps=expected,
        realised_net_bps=realised,
        fees_bps=fees,
        closed_at=BASE + timedelta(minutes=i),
        signal_id=f"sig-{i}",
        symbol="BTC-USD",
        expected_cost_bps=expected_cost,
    )


# --------------------------------------------------------------------- classification


def test_a_profit_that_tracks_expectation_is_confirmation() -> None:
    review = _review(RetrospectiveEngine(), expected=20.0, realised=22.0)
    assert review.category is LessonCategory.EDGE_CONFIRMED
    assert review.is_win
    assert not review.is_concern


def test_a_loss_on_a_positive_expectation_is_the_serious_lesson() -> None:
    review = _review(RetrospectiveEngine(), expected=15.0, realised=-30.0)
    assert review.category is LessonCategory.UNEXPECTED_LOSS
    assert review.is_concern
    assert "lost" in review.headline.lower()


def test_a_shrunken_but_positive_return_is_an_overestimate_not_a_loss() -> None:
    review = _review(RetrospectiveEngine(), expected=40.0, realised=5.0)
    assert review.category is LessonCategory.EDGE_OVERESTIMATED
    assert review.is_concern
    assert review.is_win  # still made money, just far less than promised


def test_beating_the_estimate_is_recorded_as_an_underestimate() -> None:
    review = _review(RetrospectiveEngine(), expected=5.0, realised=40.0)
    assert review.category is LessonCategory.EDGE_UNDERESTIMATED
    assert not review.is_concern


def test_a_gap_inside_the_tolerance_is_noise_not_a_lesson() -> None:
    engine = RetrospectiveEngine(tolerance_bps=8.0)
    review = _review(engine, expected=20.0, realised=14.0)  # 6 bps miss < 8
    assert review.category is LessonCategory.EDGE_CONFIRMED


def test_a_fee_overrun_is_flagged_alongside_the_verdict() -> None:
    engine = RetrospectiveEngine(cost_tolerance_bps=5.0)
    review = _review(engine, expected=30.0, realised=8.0, fees=20.0, expected_cost=10.0)
    assert review.cost_overrun is True
    assert review.category is LessonCategory.EDGE_OVERESTIMATED
    assert "fees" in review.lesson.lower()


# --------------------------------------------------------------------- memory


def test_memory_accumulates_per_pattern_and_sorts_worst_first() -> None:
    engine = RetrospectiveEngine()
    # A good long bucket and a bad short bucket.
    for i in range(6):
        _review(engine, expected=15.0, realised=16.0, i=i, direction=Direction.LONG)
    for i in range(6):
        _review(engine, expected=15.0, realised=-20.0, i=100 + i, direction=Direction.SHORT)

    worst_first = engine.memory()
    assert worst_first[0].direction is Direction.SHORT
    assert worst_first[0].mean_error_bps < worst_first[-1].mean_error_bps
    assert worst_first[-1].win_rate == 1.0


# --------------------------------------------------------------------- guardrails


def test_one_bad_trade_files_a_lesson_but_moves_no_risk() -> None:
    engine = RetrospectiveEngine(min_reviews_for_guardrail=5)
    _review(engine, expected=15.0, realised=-40.0)
    guard = engine.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    assert not guard.is_active  # below the recurrence floor
    assert engine.reviews == 1  # but the lesson is on file


def test_a_recurring_disappointment_tightens_threshold_and_size() -> None:
    engine = RetrospectiveEngine(min_reviews_for_guardrail=5, error_floor_bps=3.0)
    for i in range(6):
        _review(engine, expected=20.0, realised=-25.0, i=i)

    guard = engine.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    assert guard.is_active
    assert guard.threshold_add_bps > 0.0
    assert guard.size_multiplier < 1.0
    assert guard.based_on_trades == 6


def test_the_guardrail_only_ever_tightens_never_loosens() -> None:
    """Even a bucket that wildly *beat* expectation earns no size or threshold relief."""
    engine = RetrospectiveEngine(min_reviews_for_guardrail=5)
    for i in range(8):
        _review(engine, expected=5.0, realised=80.0, i=i)  # huge positive surprises
    guard = engine.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    assert guard.threshold_add_bps == 0.0
    assert guard.size_multiplier == 1.0  # never above 1.0


def test_the_penalty_eases_as_the_pattern_comes_back_in_line() -> None:
    engine = RetrospectiveEngine(min_reviews_for_guardrail=5, error_floor_bps=3.0)
    for i in range(6):
        _review(engine, expected=20.0, realised=-25.0, i=i)
    punished = engine.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    # Now the bucket behaves for a long stretch; the running mean error climbs back up.
    for i in range(40):
        _review(engine, expected=20.0, realised=21.0, i=200 + i)
    eased = engine.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    assert eased.threshold_add_bps < punished.threshold_add_bps
    assert not eased.is_active  # fully back to neutral, no latch


def test_the_threshold_penalty_is_capped() -> None:
    engine = RetrospectiveEngine(min_reviews_for_guardrail=5, threshold_cap_bps=40.0)
    for i in range(6):
        _review(engine, expected=50.0, realised=-500.0, i=i)  # catastrophic miss
    guard = engine.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    assert guard.threshold_add_bps <= 40.0


def test_neutral_guardrail_reports_the_pattern_it_declined_to_touch() -> None:
    guard = Guardrail.neutral("trending_up|long|0.70-0.85", based_on_trades=3)
    assert not guard.is_active
    assert guard.as_dict()["active"] is False


# --------------------------------------------------------------------- report + rebuild


def test_the_report_summarises_calibration_and_lists_active_guards() -> None:
    engine = RetrospectiveEngine(min_reviews_for_guardrail=5)
    for i in range(6):
        _review(engine, expected=20.0, realised=-25.0, i=i, direction=Direction.SHORT)
    for i in range(6):
        _review(engine, expected=15.0, realised=16.0, i=100 + i, direction=Direction.LONG)

    report = engine.report()
    assert report["reviews"] == 12
    assert report["mean_calibration_error_bps"] < 0  # dragged down by the short bucket
    assert len(report["active_guardrails"]) == 1  # only the short bucket earned one
    assert report["active_guardrails"][0]["pattern"].startswith("trending_down") is False
    assert any("short" in g["pattern"] for g in report["active_guardrails"])
    assert report["recent_lessons"][0]["signal_id"] == "sig-105"


def test_the_report_headline_counts_every_trade_beyond_the_recent_buffer() -> None:
    """The recent-lessons list is bounded; the headline statistics must not be. A system
    that reviewed 3,200 trades saying "500 reviewed" reads as a stale page, not a buffer."""
    engine = RetrospectiveEngine(history_limit=5)
    for i in range(8):
        _review(engine, expected=10.0, realised=12.0, i=i)

    report = engine.report()
    assert report["reviews"] == 8  # lifetime, not the capped buffer
    assert report["wins"] == 8
    assert sum(report["category_counts"].values()) == 8
    assert len(report["recent_lessons"]) <= 5  # the buffer itself stays bounded


def test_the_memory_is_rebuilt_exactly_from_the_persisted_trade_record() -> None:
    """A restart must not amnesia the lessons: replaying the stored rows reproduces them."""
    live = RetrospectiveEngine()
    rows = []
    for i in range(6):
        _review(live, expected=20.0, realised=-25.0, i=i)
        rows.append(
            {
                "regime": "trending_up",
                "direction": "long",
                "confidence": 0.8,
                "expected_net_bps": 20.0,
                "net_bps": -25.0,
                "fees_bps": 6.0,
                "closed_at": BASE + timedelta(minutes=i),
                "signal_id": f"sig-{i}",
                "symbol": "BTC-USD",
            }
        )

    rebuilt = RetrospectiveEngine()
    rebuilt.record_many(rows)

    assert rebuilt.reviews == live.reviews
    live_guard = live.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    rebuilt_guard = rebuilt.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    assert rebuilt_guard.threshold_add_bps == live_guard.threshold_add_bps
    assert rebuilt_guard.size_multiplier == live_guard.size_multiplier


# --------------------------------------------------------------------- dollars

def test_lessons_carry_dollars_and_the_report_exposes_the_typical_trade_size() -> None:
    """Basis points stay the learning unit — they compare trades of any size — but each
    lesson keeps its trade's dollars, and the report exposes the *median* trade size so
    every page can translate. Median on purpose: one whale trade must not skew what a
    threshold appears to cost."""
    engine = RetrospectiveEngine()
    for i, notional in enumerate((10_000.0, 12_000.0, 900_000.0)):
        engine.review(
            regime=MarketRegime.TRENDING_UP,
            direction=Direction.LONG,
            confidence=0.8,
            expected_net_bps=20.0,
            realised_net_bps=-30.0,
            fees_bps=6.0,
            closed_at=BASE + timedelta(minutes=i),
            signal_id=f"sig-{i}",
            symbol="BTC-USD",
            notional_usd=notional,
        )
    assert engine.typical_notional_usd == 12_000.0
    report = engine.report()
    assert report["typical_notional_usd"] == 12_000.0
    newest = report["recent_lessons"][0]
    assert newest["notional_usd"] == 900_000.0
    # With a known size the narration speaks dollars; the whale trade lost 30 bps of
    # $900k = $2,700, and that is the number a person should read.
    assert "$2,700.00" in newest["headline"]


def test_narration_falls_back_to_bps_when_no_trade_size_is_known() -> None:
    """A made-up dollar figure would be worse than an unfamiliar unit."""
    review = _review(RetrospectiveEngine(), expected=15.0, realised=-30.0)
    assert "bps" in review.headline
    assert review.notional_usd == 0.0


def test_rebuilding_from_persisted_rows_recovers_each_trades_dollars() -> None:
    """The persisted trade record stores entry price and quantity; record_many must turn
    them back into the notional, so dollars survive a restart exactly like the lessons."""
    engine = RetrospectiveEngine()
    engine.record_many(
        [
            {
                "regime": "trending_up",
                "direction": "long",
                "confidence": 0.8,
                "expected_net_bps": 20.0,
                "net_bps": -25.0,
                "fees_bps": 6.0,
                "closed_at": BASE,
                "signal_id": "sig-0",
                "symbol": "BTC-USD",
                "entry_price": 50_000.0,
                "quantity": 0.3,
            }
        ]
    )
    assert engine.typical_notional_usd == 15_000.0
    assert engine.recent(1)[0].notional_usd == 15_000.0


# --------------------------------------------------------------------- exploration

def test_an_exploration_trade_teaches_without_being_scored_as_a_broken_promise() -> None:
    """The distortion this flag exists to prevent.

    An exploration trade is taken *because* the bucket has no evidence, so its recorded
    "expectation" is just the round-trip cost. Scored as a claim the system then missed,
    a handful of them drag the mean calibration error down, tighten guardrails on the very
    buckets the session went to investigate, and have the Mentor propose halting because
    the system paid for the lessons it was told to buy.
    """
    engine = RetrospectiveEngine(min_reviews_for_guardrail=5, error_floor_bps=3.0)
    for i in range(10):
        engine.review(
            regime=MarketRegime.TRENDING_UP,
            direction=Direction.LONG,
            confidence=0.8,
            expected_net_bps=-3.5,   # no edge known: the cost of finding out
            realised_net_bps=-40.0,
            fees_bps=6.0,
            closed_at=BASE + timedelta(minutes=i),
            signal_id=f"exp-{i}",
            symbol="BTC-USD",
            notional_usd=2_000.0,
            exploratory=True,
        )

    report = engine.report()
    # They happened, they lost, and the win rate says so — nothing is hidden.
    assert report["reviews"] == 10
    assert report["wins"] == 0
    assert report["exploration_reviews"] == 10
    # But no claim was made, so there is no calibration error and no concern.
    assert report["calibrated_reviews"] == 0
    assert report["mean_calibration_error_bps"] == 0.0
    assert report["concerns"] == 0
    assert report["active_guardrails"] == []
    guard = engine.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    )
    assert not guard.is_active

    # A judged trade in the same bucket still counts, and still bites once there are
    # enough of them: the exclusion is about exploration, not about going easy.
    for i in range(5):
        _review(engine, expected=20.0, realised=-30.0, i=100 + i)
    assert engine.report()["calibrated_reviews"] == 5
    assert engine.guardrail_for(
        regime=MarketRegime.TRENDING_UP, direction=Direction.LONG, confidence=0.8
    ).is_active


def test_an_exploration_lesson_reads_as_a_lesson_bought_not_a_verdict() -> None:
    review = RetrospectiveEngine().review(
        regime=MarketRegime.RANGING,
        direction=Direction.SHORT,
        confidence=0.6,
        expected_net_bps=-3.5,
        realised_net_bps=25.0,
        fees_bps=6.0,
        closed_at=BASE,
        signal_id="exp",
        symbol="BTC-USD",
        notional_usd=2_000.0,
        exploratory=True,
    )
    assert review.category is LessonCategory.EXPLORATION
    assert review.exploratory
    assert not review.is_concern
    assert "exploration trade" in review.headline
    assert "no judgement was made" in review.lesson
