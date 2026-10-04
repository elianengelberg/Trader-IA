"""The block validator's fill-probe arithmetic, without a venue: where a probe re-pegs (and
where it must not), what the probes netted, and the CLI's side choices."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(scope="module")
def validator():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("validate_mm_testnet")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_a_bid_repegs_up_only_when_the_best_bid_rose_and_never_across_the_spread(validator) -> None:  # type: ignore[no-untyped-def]
    f = validator._repeg_target
    assert f("buy", 100.00, 100.00, 100.02, 0.01) is None  # still at the best
    assert f("buy", 100.00, 100.05, 100.07, 0.01) == 100.05  # the best bid rose: follow it
    assert f("buy", 100.00, 99.90, 99.92, 0.01) is None  # the best fell through us: a fill, not a re-peg
    assert f("buy", 100.00, 100.019, 100.02, 0.01) == 100.01  # rounded down onto the grid, below the ask
    assert f("buy", 100.00, 100.02, 100.02, 0.01) is None  # a target at the ask would take: refused


def test_an_ask_repegs_down_only_when_the_best_ask_fell_and_never_across_the_spread(validator) -> None:  # type: ignore[no-untyped-def]
    f = validator._repeg_target
    assert f("sell", 100.10, 100.08, 100.10, 0.01) is None
    assert f("sell", 100.10, 100.03, 100.05, 0.01) == 100.05
    assert f("sell", 100.10, 100.20, 100.22, 0.01) is None  # the best rose through us
    assert f("sell", 100.10, 100.05, 100.05, 0.01) is None  # a target at the bid would take: refused


def test_the_net_inventory_is_bought_minus_sold(validator) -> None:  # type: ignore[no-untyped-def]
    assert validator._net_inventory([("buy", 0.0001), ("sell", 0.0001)]) == 0.0
    assert validator._net_inventory([("buy", 0.0003), ("sell", 0.0001)]) == pytest.approx(0.0002)
    assert validator._net_inventory([("sell", 0.0002)]) == pytest.approx(-0.0002)
    assert validator._net_inventory([]) == 0.0


def test_the_cli_offers_bid_ask_or_both_and_keeps_the_single_bid_as_the_default(validator, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    import argparse

    parser = argparse.ArgumentParser()
    # the same flags the script declares, read back from its main() source so a drift shows
    source = Path(validator.__file__).read_text()
    assert '"--fill-probe-sides", default="bid", choices=("bid", "ask", "both")' in source
    assert '"--fill-probe-repeg", type=float, default=0.0' in source
    parser.add_argument("--fill-probe-sides", default="bid", choices=("bid", "ask", "both"))
    assert parser.parse_args([]).fill_probe_sides == "bid"
    with pytest.raises(SystemExit):
        parser.parse_args(["--fill-probe-sides", "market"])
