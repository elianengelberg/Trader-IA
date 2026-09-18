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
