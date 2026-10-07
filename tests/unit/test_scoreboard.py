"""The strategy scoreboard: credit where due, blame with enough evidence, and muting
that can only refuse."""

from __future__ import annotations

import pytest

from tia.learning.scoreboard import MIN_TRADES_TO_JUDGE, StrategyScoreboard


def test_a_strategy_is_credited_and_blamed_for_its_own_trades() -> None:
    board = StrategyScoreboard()
    board.record("trend", 20.0)
    board.record("trend", -5.0)
    board.record("mean_rev", -30.0)

    rows = {r["strategy_id"]: r for r in board.report()}
    assert rows["trend"]["trades"] == 2 and rows["trend"]["wins"] == 1
    assert rows["trend"]["mean_net_bps"] == pytest.approx(7.5)
    assert rows["mean_rev"]["mean_net_bps"] == -30.0
    assert board.report()[0]["strategy_id"] == "trend"  # best first


def test_muting_needs_the_floor_and_a_record_worse_than_its_own_noise() -> None:
    board = StrategyScoreboard()
    for i in range(MIN_TRADES_TO_JUDGE - 1):
        board.record("bad", -20.0 + (2.0 if i % 2 else -2.0))
    assert board.is_muted("bad") is False  # one short of the floor
    board.record("bad", -20.0)
    assert board.is_muted("bad") is True
    assert "muted" in board.reason("bad")
    assert board.report()[0]["needed_to_judge"] == 0


def test_a_red_but_noisy_record_does_not_mute() -> None:
    board = StrategyScoreboard()
    for i in range(MIN_TRADES_TO_JUDGE + 10):
        board.record("noisy", -1.0 + (60.0 if i % 2 else -60.0))
    assert board.is_muted("noisy") is False


def test_exploration_trades_are_recorded_but_never_judge() -> None:
    board = StrategyScoreboard()
    for _ in range(MIN_TRADES_TO_JUDGE + 5):
        board.record("explorer", -50.0, exploratory=True)
    row = board.report()[0]
    assert row["trades"] == MIN_TRADES_TO_JUDGE + 5
    assert row["judged"] == 0
    assert board.is_muted("explorer") is False


def test_rows_without_a_strategy_are_skipped_not_invented() -> None:
    board = StrategyScoreboard()
    credited = board.record_many(
        [
            {"strategy_id": "trend", "net_bps": 5.0},
            {"strategy_id": None, "net_bps": 5.0},
            {"net_bps": 5.0},
            {"strategy_id": "", "net_bps": 5.0},
        ]
    )
    assert credited == 1
    assert [r["strategy_id"] for r in board.report()] == ["trend"]


def test_an_unknown_strategy_is_not_muted_and_has_no_reason() -> None:
    board = StrategyScoreboard()
    assert board.is_muted("never-seen") is False
    assert board.reason("never-seen") == ""


# ----------------------------------------------------------------- which evidence judges
#
# The policy decides which closed trades a strategy answers for. ``legacy`` is the
# behaviour every deployment has had; ``real_only`` refuses to let a scenario generator's
# losses mute a strategy trading real prices. The verdict rule is the same under both.

from statistics import mean  # noqa: E402

from tia.learning.scoreboard import (  # noqa: E402
    MUTE_SE,
    SCOREBOARD_POLICIES,
    credited_strategy_version,
)


def _negatives(n: int, *, base: float = -20.0) -> list[float]:
    """``n`` returns around ``base``, alternating ±2 so the record has a spread."""
    return [base + (2.0 if i % 2 else -2.0) for i in range(n)]


def _rows(strategy_id: str, values: list[float], market_data: str | None) -> list[dict]:
    return [{"strategy_id": strategy_id, "net_bps": v, "market_data": market_data} for v in values]


def test_legacy_is_the_default_and_credits_synthetic_rows_exactly_as_before() -> None:
    board = StrategyScoreboard()
    assert board.policy == "legacy"
    assert SCOREBOARD_POLICIES == ("legacy", "real_only")
    assert board.record_many(_rows("bad", _negatives(100), "synthetic")) == 100
    assert board.is_muted("bad") is True
    row = board.report()[0]
    assert row["trades"] == 100 and row["judged"] == 100
    assert row["excluded_synthetic"] == 0 and row["excluded_unknown"] == 0


def test_legacy_ignores_provenance_entirely() -> None:
    """With and without ``market_data`` — real, synthetic, missing — a legacy board ends
    up byte-for-byte where the board before provenance existed would have."""
    with_provenance = StrategyScoreboard(policy="legacy")
    without = StrategyScoreboard()
    for i, value in enumerate(_negatives(40)):
        with_provenance.record("s", value, market_data=("synthetic", None, "real")[i % 3])
        without.record("s", value)
    assert with_provenance.report() == without.report()
    assert with_provenance.is_muted("s") is without.is_muted("s") is True


def test_under_real_only_a_hundred_synthetic_losers_cannot_mute() -> None:
    board = StrategyScoreboard(policy="real_only")
    assert board.record_many(_rows("bad", _negatives(100), "synthetic")) == 0
    assert board.is_muted("bad") is False
    assert board.reason("bad") == ""
    row = board.report()[0]
    assert row["trades"] == 0 and row["judged"] == 0 and row["mean_net_bps"] is None
    assert row["excluded_synthetic"] == 100 and row["excluded_unknown"] == 0
    assert row["needed_to_judge"] == MIN_TRADES_TO_JUDGE


def test_under_real_only_twenty_nine_real_losers_do_not_mute() -> None:
    board = StrategyScoreboard(policy="real_only")
    board.record_many(_rows("bad", _negatives(MIN_TRADES_TO_JUDGE - 1), "real"))
    row = board.report()[0]
    assert row["judged"] == MIN_TRADES_TO_JUDGE - 1 and row["needed_to_judge"] == 1
    assert board.is_muted("bad") is False


def test_under_real_only_thirty_sufficiently_negative_real_losers_mute() -> None:
    board = StrategyScoreboard(policy="real_only")
    board.record_many(_rows("bad", _negatives(MIN_TRADES_TO_JUDGE), "real"))
    row = board.report()[0]
    assert row["judged"] == MIN_TRADES_TO_JUDGE
    # The rule, verbatim: judged >= 30 and mean + 1.0 * standard error < 0.
    assert row["mean_net_bps"] + MUTE_SE * row["standard_error_bps"] < 0
    assert board.is_muted("bad") is True
    assert "muted" in board.reason("bad")


def test_the_verdict_rule_is_identical_under_both_policies() -> None:
    """Real rows judged under ``real_only`` produce the same statistics and the same
    verdict as the same rows under ``legacy``: the policy filters, it never re-judges."""
    cases = {
        "floor": _negatives(MIN_TRADES_TO_JUDGE),
        "one short": _negatives(MIN_TRADES_TO_JUDGE - 1),
        "red but noisy": [-1.0 + (60.0 if i % 2 else -60.0) for i in range(40)],
        "winning": [10.0 + (2.0 if i % 2 else -2.0) for i in range(40)],
    }
    for name, values in cases.items():
        legacy, real_only = StrategyScoreboard(), StrategyScoreboard(policy="real_only")
        legacy.record_many(_rows(name, values, "real"))
        real_only.record_many(_rows(name, values, "real"))
        assert legacy.report() == real_only.report(), name
        assert legacy.is_muted(name) is real_only.is_muted(name), name


def test_under_real_only_mixed_evidence_judges_only_the_real_rows() -> None:
    board = StrategyScoreboard(policy="real_only")
    real = _negatives(MIN_TRADES_TO_JUDGE)
    credited = board.record_many(_rows("s", [-200.0] * 100, "synthetic") + _rows("s", real, "real"))
    assert credited == MIN_TRADES_TO_JUDGE
    row = board.report()[0]
    assert row["trades"] == MIN_TRADES_TO_JUDGE and row["judged"] == MIN_TRADES_TO_JUDGE
    assert row["excluded_synthetic"] == 100
    assert row["mean_net_bps"] == pytest.approx(mean(real), abs=1e-3)  # the real rows alone
    assert board.is_muted("s") is True  # thirty real losers mute on their own merits

    # And the mirror image: a hundred catastrophic synthetic rows cannot drag down a
    # strategy whose real record is positive.
    good = StrategyScoreboard(policy="real_only")
    good.record_many(
        _rows("s", [-200.0] * 100, "synthetic")
        + _rows("s", [10.0 + (2.0 if i % 2 else -2.0) for i in range(MIN_TRADES_TO_JUDGE)], "real")
    )
    assert good.is_muted("s") is False
    assert good.report()[0]["mean_net_bps"] == pytest.approx(10.0)


def test_under_real_only_rows_without_provenance_do_not_count() -> None:
    board = StrategyScoreboard(policy="real_only")
    rows = [{"strategy_id": "s", "net_bps": v} for v in _negatives(100)]  # no key at all
    rows += _rows("s", _negatives(50), None)  # an explicit null
    assert board.record_many(rows) == 0
    assert board.is_muted("s") is False
    row = board.report()[0]
    assert row["judged"] == 0 and row["excluded_unknown"] == 150 and row["excluded_synthetic"] == 0


def test_the_historical_synthetic_record_cannot_mute_anyone_under_real_only() -> None:
    """The evidence store as it stood on 2026-10-06, by strategy: 2446 trend_following,
    493 mean_reversion and 21 breakout rows, every one from a training simulation. The
    returns here are stand-ins (negative enough to mute where the floor allows) — the
    row counts are the real ones. Under ``legacy`` two strategies are muted on that
    record; under ``real_only`` none of it judges anybody."""
    counts = {"trend_following": 2446, "mean_reversion": 493, "breakout": 21}
    rows: list[dict] = []
    for strategy_id, n in counts.items():
        rows += _rows(strategy_id, _negatives(n, base=-8.0), "synthetic")

    legacy = StrategyScoreboard(policy="legacy")
    assert legacy.record_many(rows) == sum(counts.values())
    assert legacy.is_muted("trend_following") and legacy.is_muted("mean_reversion")
    assert legacy.is_muted("breakout") is False  # 21 is under the floor, as before

    real_only = StrategyScoreboard(policy="real_only")
    assert real_only.record_many(rows) == 0
    for strategy_id in counts:
        assert real_only.is_muted(strategy_id) is False, strategy_id
    assert {r["strategy_id"]: r["excluded_synthetic"] for r in real_only.report()} == counts
    assert all(r["judged"] == 0 for r in real_only.report())


def test_exploration_is_recorded_but_never_judges_under_real_only_either() -> None:
    board = StrategyScoreboard(policy="real_only")
    for _ in range(MIN_TRADES_TO_JUDGE + 5):
        board.record("explorer", -50.0, exploratory=True, market_data="real")
    row = board.report()[0]
    assert row["trades"] == MIN_TRADES_TO_JUDGE + 5 and row["exploratory"] == row["trades"]
    assert row["judged"] == 0 and board.is_muted("explorer") is False


def test_an_unknown_policy_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="unknown scoreboard policy"):
        StrategyScoreboard(policy="probation")


def test_credited_strategy_version_is_the_named_strategys_own_and_never_a_guess() -> None:
    from types import SimpleNamespace

    opinions = (
        SimpleNamespace(strategy_id="breakout", strategy_version="1.1.0"),
        SimpleNamespace(strategy_id="trend_following", strategy_version="1.1.0"),
    )
    credited = SimpleNamespace(
        strategy_id="trend_following",
        strategy_version="breakout@1.1.0+trend_following@1.1.0",  # the fusion's string
        opinions=opinions,
    )
    assert credited_strategy_version(credited) == "1.1.0"
    fused = SimpleNamespace(strategy_id="fusion", strategy_version="x", opinions=opinions)
    assert credited_strategy_version(fused) is None
    assert credited_strategy_version(SimpleNamespace(strategy_id="breakout")) is None


def test_the_policy_is_read_from_the_environment_and_defaults_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``TIA_LIVE__SCOREBOARD_POLICY`` is how a deployment opts in; anything that is not
    one of the two policies fails configuration rather than silently doing something."""
    from pydantic import ValidationError

    from tia.core.config import Settings

    monkeypatch.delenv("TIA_LIVE__SCOREBOARD_POLICY", raising=False)
    assert Settings(_env_file=None).live.scoreboard_policy == "legacy"
    monkeypatch.setenv("TIA_LIVE__SCOREBOARD_POLICY", "real_only")
    assert Settings(_env_file=None).live.scoreboard_policy == "real_only"
    monkeypatch.setenv("TIA_LIVE__SCOREBOARD_POLICY", "legacy")
    assert Settings(_env_file=None).live.scoreboard_policy == "legacy"
    monkeypatch.setenv("TIA_LIVE__SCOREBOARD_POLICY", "probation")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
