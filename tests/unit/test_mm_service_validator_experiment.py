"""The S8 experiment's harness overrides: production defaults untouched, the three overrides
parsed, validated and applied to the maker's configuration only, invalid values refused, and
the evidence helpers that tell a TTL cancel from a requote from a stale-data cancel from a
fill, plus the event-loop lag summary. Nothing here touches the stale-data threshold."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from tia.mm.costs import MarketMakerCostConfig, MarketMakerCostModel
from tia.mm.engine import MarketMakerConfig
from tia.mm.execution import SymbolFilters
from tia.mm.quoting import QuotingConfig

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
FILTERS = SymbolFilters(symbol="BTC-USD", tick_size=0.01, step_size=0.00001, min_qty=0.00001, max_qty=9000.0, min_notional=5.0, order_types=("LIMIT", "LIMIT_MAKER"))


@pytest.fixture(scope="module")
def harness():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("validate_mm_live_service_testnet")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_the_production_defaults_are_exactly_what_the_harness_builds_without_flags(harness) -> None:  # type: ignore[no-untyped-def]
    args = harness.build_parser().parse_args([])
    assert (args.fee_scenario, args.quote_ttl_ms, args.requote_threshold_bps) == ("assumed", 1000, 0.5)
    overrides = harness.ExperimentOverrides.from_args(args)
    assert overrides.active == {} and overrides.experimental is False
    built = harness.build_maker_config(symbol="BTC-USD", filters=FILTERS, quote_size=0.0002, overrides=overrides)
    before = MarketMakerConfig(symbol="BTC-USD", quoting=QuotingConfig(base_quote_size_btc=0.0002, tick_size=0.01, size_step=0.00001, min_size_btc=0.0001))
    assert built == before  # what this harness always built: production defaults plus the grid and the size
    assert built.quoting.quote_ttl_ms == 1000 and built.requote_threshold_bps == 0.5 and built.fee_scenario == "assumed"
    assert built.costs == MarketMakerCostConfig() and MarketMakerCostModel(built.costs).maker_fee_bps == 10.0
    assert harness.ExperimentOverrides().as_dict()["note"].startswith("production defaults")


def test_the_three_overrides_parse_and_change_only_quoting_parameters(harness) -> None:  # type: ignore[no-untyped-def]
    args = harness.build_parser().parse_args(["--fee-scenario", "testnet_zero", "--quote-ttl-ms", "30000", "--requote-threshold-bps", "5"])
    overrides = harness.ExperimentOverrides.from_args(args)
    assert overrides.active == {"fee_scenario": "testnet_zero", "quote_ttl_ms": 30000, "requote_threshold_bps": 5.0} and overrides.experimental
    built = harness.build_maker_config(symbol="BTC-USD", filters=FILTERS, quote_size=0.0002, overrides=overrides)
    assert built.quoting.quote_ttl_ms == 30000 and built.requote_threshold_bps == 5.0
    assert built.costs.maker_fee_bps == 0.0 and built.costs.taker_fee_bps == 0.0 and built.costs.maker_fee_adverse_bps == 0.0
    assert built.costs.maker_fee_status.startswith("EXPERIMENT_TESTNET_ZERO") and MarketMakerCostModel(built.costs).maker_fee_bps == 0.0
    assert built.fee_scenario == "assumed"  # the engine learns no new scenario name
    plain = MarketMakerConfig()
    # Everything that is not a quoting parameter is the production default: data age, limits, spread, fair value, inventory, toxicity, regimes.
    assert built.max_data_age_ms == plain.max_data_age_ms == 2000 and built.requote_interval_ms == plain.requote_interval_ms
    assert built.limits == plain.limits and built.spread == plain.spread and built.fair_value == plain.fair_value and built.inventory == plain.inventory
    assert built.toxicity == plain.toxicity and built.regimes == plain.regimes and built.features == plain.features
    assert built.quoting.min_confidence == plain.quoting.min_confidence and built.quoting.max_offset_from_mid_bps == plain.quoting.max_offset_from_mid_bps
    recorded = overrides.as_dict()
    assert recorded["experimental"] is True and recorded["defaults"] == {"fee_scenario": "assumed", "quote_ttl_ms": 1000, "requote_threshold_bps": 0.5}
    assert "not a strategy" in recorded["note"] and "stale-data threshold" in recorded["note"]


def test_a_partial_override_is_recorded_as_only_what_changed(harness) -> None:  # type: ignore[no-untyped-def]
    args = harness.build_parser().parse_args(["--quote-ttl-ms", "30000"])
    overrides = harness.ExperimentOverrides.from_args(args)
    assert overrides.active == {"quote_ttl_ms": 30000}
    built = harness.build_maker_config(symbol="BTC-USD", filters=FILTERS, quote_size=0.0002, overrides=overrides)
    assert built.costs == MarketMakerCostConfig() and built.requote_threshold_bps == 0.5 and built.quoting.quote_ttl_ms == 30000


@pytest.mark.parametrize(
    "argv",
    [
        ["--quote-ttl-ms", "50"],  # below the floor
        ["--quote-ttl-ms", "10000000"],  # above the ceiling
        ["--quote-ttl-ms", "abc"],
        ["--quote-ttl-ms", "1.5"],
        ["--requote-threshold-bps", "0"],  # would requote on any change
        ["--requote-threshold-bps", "500"],
        ["--requote-threshold-bps", "x"],
        ["--fee-scenario", "mainnet"],
        ["--fee-scenario", "zero"],
        ["--fee-scenario", "verified"],  # a production scenario this harness does not offer
        ["--fee-scenario", "adverse"],
    ],
)
def test_invalid_values_are_refused_before_anything_runs(harness, argv, capsys) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SystemExit) as exc:
        harness.build_parser().parse_args(argv)
    assert exc.value.code == 2
    assert "invalid" in capsys.readouterr().err


def test_the_harness_never_names_the_stale_data_threshold(harness) -> None:  # type: ignore[no-untyped-def]
    source = Path(harness.__file__).read_text()
    assert "max_venue_age_s" not in source and "PROVISIONAL_MAX_VENUE_AGE_S" not in source
    assert "MarketDataService(args.symbol, stream=stream, fetch_snapshot=fetch_snapshot, recorder=None)" in source  # built with its defaults


class _Fill:
    def __init__(self, fill_id: str, t_ms: int, quantity: float) -> None:
        self.fill_id, self.t_ms, self.quantity = fill_id, t_ms, quantity


class _Order:
    def __init__(self, order_id: str, state: str, *, t_ack: int | None, t_cancel: int | None = None, reason: str = "", fills: list[_Fill] | None = None, submitted: bool = True) -> None:
        self.order_id, self.side, self.price, self.quantity, self.state = order_id, "buy", 85_000.0, 0.0002, state
        self.t_enqueued_ms, self.t_submitted_ms, self.t_ack_ms = 1_000, (1_001 if submitted else None), t_ack
        self.t_cancel_requested_ms, self.t_cancel_effective_ms, self.cancel_reason = t_cancel, (t_cancel + 240 if t_cancel else None), reason
        self.fills, self.ack_source, self.venue_order_id = fills or [], "stream", "9"


def test_cancel_reasons_are_classified_and_resting_times_measured(harness) -> None:  # type: ignore[no-untyped-def]
    orders = [
        _Order("a", "cancelled", t_ack=1_300, t_cancel=2_300, reason="ttl expired"),
        _Order("b", "cancelled", t_ack=1_300, t_cancel=1_800, reason="requote"),
        _Order("c", "cancelled", t_ack=1_300, t_cancel=1_400, reason="gate: data_invalid: market data not usable: venue data 1.1s old at the venue"),
        _Order("d", "cancelled", t_ack=1_300, t_cancel=1_350, reason="kill switch (data): market data not usable: last event 2448 ms ago, over 2000"),
        _Order("e", "cancelled", t_ack=1_300, t_cancel=5_300, reason="shutdown: validation window elapsed (by validate_mm_live_service_testnet)"),
        _Order("f", "cancelled", t_ack=1_300, t_cancel=1_900, reason="kill switch (user_stream_down): account stream dropped: closed"),
        _Order("g", "filled", t_ack=1_300, fills=[_Fill("77", 14_300, 0.0002)]),
        _Order("h", "refused", t_ack=None, submitted=False),
        # The engine's own no_quote reasons, verbatim from the 2026-10-05 Testnet evidence (e5b5625):
        _Order("i", "cancelled", t_ack=1_300, t_cancel=2_563, reason="both sides sized to zero: inventory -1% of limit: quotes shifted +0.00 bps; within limits"),
        _Order("j", "cancelled", t_ack=1_300, t_cancel=2_100, reason="fair value confidence 0.13 below 0.20: data 840 ms old; no 5 s volatility yet"),
        _Order("k", "cancelled", t_ack=1_300, t_cancel=2_200, reason="risk controller: daily loss limit reached"),
        _Order("l", "cancelled", t_ack=1_300, t_cancel=2_300, reason="quotes 1.0/2.0 further than 50.0 bps from the mid 85000.0: refused as implausible"),
        _Order("m", "filled", t_ack=1_300, fills=[_Fill("78", 2_000, 0.00016)], t_cancel=1_900, reason="requote | cancel rejected (code -2011): [ORDER_REJECTED] Unknown order sent."),
    ]
    lc = harness._order_lifecycle(orders)
    assert lc["orders"] == 13 and lc["sent_to_venue"] == 12 and lc["acknowledged"] == 12 and lc["never_acknowledged"] == 1
    assert lc["terminal"] == {"cancelled:ttl": 1, "cancelled:requote": 1, "cancelled:stale_data": 2, "cancelled:shutdown": 1, "cancelled:kill_switch": 1, "filled": 2, "refused": 1, "cancelled:no_quote_size": 1, "cancelled:no_quote_confidence": 1, "cancelled:no_quote_risk": 1, "cancelled:no_quote_implausible": 1}
    assert lc["cancel_reasons"] == {"ttl": 1, "requote": 1, "stale_data": 2, "shutdown": 1, "kill_switch": 1, "no_quote_size": 1, "no_quote_confidence": 1, "no_quote_risk": 1, "no_quote_implausible": 1}
    by_id = {r["order_id"]: r for r in lc["rows"]}
    assert by_id["a"]["resting_ms"] == 1_000 and by_id["b"]["resting_ms"] == 500 and by_id["g"]["resting_ms"] == 13_000 and by_id["h"]["resting_ms"] is None
    assert by_id["m"]["terminal"] == "filled" and by_id["m"]["resting_ms"] == 700  # a fill that raced our cancel ends at the fill, and stays a fill
    assert lc["resting_ms"]["count"] == 12 and lc["resting_ms"]["max"] == 13_000 and lc["resting_ms"]["min"] == 50
    assert lc["filled_orders"][0]["order_id"] == "g" and lc["filled_orders"][0]["filled_qty"] == 0.0002
    assert harness._classify_cancel_reason("") == "none" and harness._classify_cancel_reason("something new") == "other" and harness._classify_cancel_reason("pacing denial while a requote was due (x)") == "pacing"
    assert harness._classify_cancel_reason("requote | cancel rejected (code -2011): [ORDER_REJECTED] Unknown order sent.") == "requote"
    assert set(lc["cancel_reasons"]) <= set(harness.CANCEL_CLASSES)


def test_the_cancel_reason_is_kept_long_enough_to_read_the_whole_finding(harness) -> None:  # type: ignore[no-untyped-def]
    """The engine's reasons run past 80 characters (the 2026-10-05 evidence cut them at
    '...quotes shifted +0.00 bps; with'); the row keeps 160."""
    reason = "fair value confidence 0.13 below 0.20: data 840 ms old; no 5 s volatility yet; wide spread regime; components disagree in sign; " + "x" * 80
    [row] = harness._order_lifecycle([_Order("a", "cancelled", t_ack=1_300, t_cancel=2_300, reason=reason)])["rows"]
    assert row["cancel_reason"] == reason[:160] and len(row["cancel_reason"]) == 160 and "components disagree in sign" in row["cancel_reason"]


def test_the_loop_lag_summary_reports_percentiles_and_the_stalls(harness) -> None:  # type: ignore[no-untyped-def]
    samples = [1.0] * 98 + [3.0, 985.0]
    stalls = [{"t_ms": 1_791_000_000_000, "lag_ms": 985.0}]
    out = harness._lag_summary(samples, stalls, 200.0)
    assert out["samples"] == 100 and out["p50_ms"] == 1.0 and out["p99_ms"] == 3.0 and out["max_ms"] == 985.0  # nearest rank: p99 of 100 is the 99th sample; the stall is the max
    assert out["stall_count"] == 1 and out["stalls"] == stalls and out["stall_threshold_ms"] == 200.0
    assert harness._lag_summary([], [], 200.0)["p50_ms"] is None
