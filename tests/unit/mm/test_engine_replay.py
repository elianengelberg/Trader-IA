"""The engine end to end on a synthetic tape: deterministic, prefix-invariant, fills
only from prints on the tape, the hierarchy in order, and no road to real execution.

Every event is synthetic and says so. The numbers prove the machinery, not an edge.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tia.domain.enums import SystemMode
from tia.mm.costs import MarketMakerCostConfig
from tia.mm.engine import MarketMakerConfig, MarketMakerEngine
from tia.mm.latency import LatencyStats
from tia.mm.latency_model import build_latency_profile
from tia.mm.mm_replay import event_from_row, replay_market_maker
from tia.mm.order_book import DepthSnapshot, DepthUpdate, snapshot_from_levels
from tia.mm.recorder import BookStateEvent, TickRecorder
from tia.mm.safety import GlobalTradingSafetyGate
from tia.mm.spread import SpreadConfig
from tia.mm.streams import TradeEvent
from tia.risk.engine import RiskState

T0 = 1_789_754_400_000
MM_SRC = Path(__file__).resolve().parents[3] / "packages" / "tia" / "src" / "tia" / "mm"


def _stats(values: list[float]) -> dict:  # type: ignore[type-arg]
    stats = LatencyStats()
    for v in values:
        stats.add(v)
    return stats.as_dict()


PROFILE = build_latency_profile(
    stream={"latency_depth_ms": _stats([40, 50, 60, 70, 80]), "latency_trade_ms": _stats([40, 50, 60])},
    processing_us=_stats([20, 30, 40]),
    measured_at_utc="2026-09-18T00:00:00Z",
    commit="synthetic",
    duration_s=60,
    symbol="BTC-USD",
)


def _config() -> MarketMakerConfig:
    # A tight fee and floor so the synthetic tape can reach the quotes at all.
    return MarketMakerConfig(
        costs=MarketMakerCostConfig(maker_fee_bps=0.5, maker_fee_adverse_bps=1.0),
        spread=SpreadConfig(min_half_spread_bps=0.5, cost_buffer_bps=0.0, vol_multiplier=0.0),
        requote_interval_ms=200,
    )


def _snapshot() -> DepthSnapshot:
    bids = [(round(100_000.0 - i * 0.1, 1), 1.0) for i in range(80)]  # down to 99,992.1
    asks = [(round(100_000.2 + i * 0.1, 1), 1.0) for i in range(80)]
    return snapshot_from_levels(100, bids, asks)


def _tape(n_trades: int = 20, *, with_trades: bool = True) -> list[tuple[str, object, int]]:
    """Synthetic: a steady book, deep-level diffs every 100 ms, sells printing at 99,995.0."""
    events: list[tuple[str, object, int]] = [("snapshot", _snapshot(), T0)]
    uid = 101
    t = T0
    for i in range(n_trades * 2):
        t += 100
        events.append(("depth", DepthUpdate(uid, uid, ((99_993.0, 1.0 + (i % 3)),), (), t - 30, t), t))
        uid += 1
        if with_trades and i % 2 == 1:
            t += 10
            events.append(("trade", TradeEvent(500 + i, 99_995.0, 0.002, True, t - 5, t - 2, t), t))
    return events


def _gate(state: RiskState | None = None) -> GlobalTradingSafetyGate:
    holder = {"state": state or RiskState()}
    return GlobalTradingSafetyGate(risk_state=lambda: holder["state"], data_usable=lambda: (True, ""))


def _run(events: list[tuple[str, object, int]], *, gate: GlobalTradingSafetyGate | None = None, config: MarketMakerConfig | None = None) -> MarketMakerEngine:
    engine = MarketMakerEngine(config or _config(), latency=PROFILE.scenario("optimistic"), gate=gate or _gate())
    for kind, event, t in events:
        engine.on_event(kind, event, t)
    return engine


# ------------------------------------------------------------------ 18. deterministic replay, 19. no look-ahead


def test_two_runs_over_the_same_tape_agree_byte_for_byte() -> None:
    a, b = _run(_tape()), _run(_tape())
    assert a.journal_hash() == b.journal_hash() and a.snapshot()["ledger"] == b.snapshot()["ledger"]
    assert a.quotes >= 1 and a.execution.stats()["fills"] >= 1, a.snapshot()["no_quote_reasons"]


def test_a_prefix_of_the_tape_yields_a_prefix_of_the_journal() -> None:
    full = _tape()
    rows_full = [json.dumps(r, sort_keys=True, default=str) for r in _run(full).journal]
    for k in (5, 17, 30):
        rows_prefix = [json.dumps(r, sort_keys=True, default=str) for r in _run(full[:k]).journal]
        assert rows_prefix == rows_full[: len(rows_prefix)]


# ------------------------------------------------------------------ 21. no invented data, 13. fills need prints


def test_every_fill_names_a_print_on_the_tape_and_no_prints_means_no_fills() -> None:
    engine = _run(_tape())
    tape_trade_ids = {e.trade_id for k, e, _ in _tape() if k == "trade"}  # type: ignore[attr-defined]
    fills = [r for r in engine.journal if r["kind"] == "fill"]
    assert fills and all(set(f["venue_trade_ids"]) <= tape_trade_ids for f in fills)
    # Only sells printed, so only the bid could fill; the fill is at our resting price,
    # which a print at or through it (99,995.0 <= our bid) reached.
    assert all(f["side"] == "buy" and f["price"] >= 99_995.0 for f in fills)
    ledger = engine.snapshot()["ledger"]
    assert ledger["inventory_btc"] == pytest.approx(sum(f["quantity"] for f in fills)) and ledger["fees_usd"] > 0
    quiet = _run(_tape(with_trades=False))
    assert quiet.quotes >= 1 and quiet.execution.stats()["fills"] == 0 and quiet.snapshot()["ledger"]["inventory_btc"] == 0.0


# ------------------------------------------------------------------ 17/23. the hierarchy, in order


def test_the_gate_is_consulted_before_the_controller_and_a_block_cancels_everything() -> None:
    state = RiskState()
    gate = _gate(state)
    engine = MarketMakerEngine(_config(), latency=PROFILE.scenario("baseline"), gate=gate)
    calls = {"allowance": 0}
    original = engine.controller.allowance

    def counted(view, t_ms):  # type: ignore[no-untyped-def]
        calls["allowance"] += 1
        return original(view, t_ms)

    engine.controller.allowance = counted  # type: ignore[method-assign]
    events = _tape(10)
    for kind, event, t in events[:6]:
        engine.on_event(kind, event, t)
    assert engine.quotes >= 1 and calls["allowance"] >= 1 and engine.execution.open_orders()
    state.mode = SystemMode.HALTED
    state.kill_switch_reason = "operator"
    before = calls["allowance"]
    for kind, event, t in events[6:12]:
        engine.on_event(kind, event, t)
    blocks = [r for r in engine.journal if r["kind"] == "block"]
    assert blocks and blocks[-1]["layer"] == "gate" and "operator" in blocks[-1]["reason"]
    assert calls["allowance"] == before  # the controller was never asked while the gate said no
    assert engine.gate_blocks >= 1 and engine.last_decision is None
    assert all(o.t_cancel_requested_ms is not None for o in engine.execution.orders.values() if o.state in ("pending_arrival", "resting"))
    state.mode = SystemMode.NORMAL
    for kind, event, t in events[12:]:
        engine.on_event(kind, event, t)
    assert calls["allowance"] > before  # recovered: the controller is consulted again


def test_the_controllers_kill_switch_stops_quotes_without_touching_the_gate() -> None:
    engine = _run(_tape(2))
    engine.controller.engage_kill_switch("test")
    for kind, event, t in _tape(6)[9:]:
        engine.on_event(kind, event, t)
    decisions = [r for r in engine.journal if r["kind"] == "decision"]
    assert decisions[-1]["decision"] == "no_quote" and "kill switch" in decisions[-1]["reason"]
    assert engine.last_gate is not None and engine.last_gate.allows_quoting  # the gate is untouched and still SAFE


# ------------------------------------------------------------------ 18. replay from a recorded segment


def test_replay_from_a_recorded_segment_is_deterministic_and_names_its_profile(tmp_path: Path) -> None:
    recorder = TickRecorder(tmp_path, "BTC-USD", now_ms=lambda: T0)
    for kind, event, _t in _tape(12):
        if kind == "snapshot":
            snap = event
            recorder.record("snapshot", BookStateEvent(snap.last_update_id, snap.bids, snap.asks, T0))  # type: ignore[union-attr]
        else:
            recorder.record(kind, event)
    recorder.record("checkpoint", BookStateEvent(100 + 24, _snapshot().bids, _snapshot().asks, T0 + 3_000))
    recorder.close()
    segment = recorder.segments()[0]["path"]
    first = replay_market_maker([segment], config=_config(), profile=PROFILE, scenario="optimistic", keep_journal=True)
    second = replay_market_maker([segment], config=_config(), profile=PROFILE, scenario="optimistic")
    assert first.journal_hash == second.journal_hash and first.snapshot["ledger"] == second.snapshot["ledger"]
    assert first.profile_id == PROFILE.profile_id and first.latency_scenario == "optimistic" and first.config_id == _config().config_id
    assert first.events_by_kind["snapshot"] == 2 and first.events_by_kind["trade"] == 12
    assert first.snapshot["execution"]["fills"] >= 1
    slower = replay_market_maker([segment], config=_config(), profile=PROFILE, scenario="conservative")
    assert slower.snapshot["latency"]["order_latency_ms"] > first.snapshot["latency"]["order_latency_ms"]
    assert event_from_row({"k": "book", "R": 1, "u": 1}) == ("book", {"k": "book", "R": 1, "u": 1}, 1)


# ------------------------------------------------------------------ 20. no real execution


def test_nothing_in_the_market_maker_can_reach_an_execution_provider() -> None:
    forbidden = re.compile(r"tia\.execution|ExecutionProvider|submit_order|LiveActivationToken|binance_live|ccxt|api_key|API_KEY")
    offenders = [p.name for p in MM_SRC.glob("*.py") if forbidden.search(p.read_text(encoding="utf-8"))]
    assert offenders == []
    reads_real_money = [p.name for p in MM_SRC.glob("*.py") if "real_money" in p.read_text(encoding="utf-8")]
    assert reads_real_money == []  # the flag is read by nothing in the package
    engine = _run(_tape(2))
    assert not any(hasattr(v, "submit_order") or getattr(v, "is_live", False) for v in vars(engine).values())
