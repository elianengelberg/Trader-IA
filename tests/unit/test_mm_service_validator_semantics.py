"""The service validator's kill-switch verdicts, demonstrated on synthetic final states.

``scripts/validate_mm_live_service_testnet.py`` is a script, not a package; its judge is
exercised here with hand-built statuses so the semantics are pinned: a transient engagement
during the run is the rails working, a sticky one is a FAIL, a deliberate shutdown is
recorded as a shutdown with no safety engagement left, and a ghost transient after stop is a
FAIL (the service could no longer observe it). This is a test of the validator, not of
Binance.
"""

from __future__ import annotations

import importlib
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(scope="module")
def validator_module():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("validate_mm_live_service_testnet")
    finally:
        sys.path.remove(str(SCRIPTS))


def _status(*, kill: dict[str, Any], placed: int = 3) -> dict[str, Any]:
    counters = dict.fromkeys(("placed", "acked", "rejected", "rejected_would_cross", "refused_validation", "refused_blocked", "deferred_cancel_pending", "cancel_requests", "cancelled", "expired", "unknown", "cancel_rejected_after_close", "fills", "report_fills", "trade_poll_fills", "duplicate_trades"), 0)
    counters.update({"placed": placed, "acked": placed, "cancel_requests": placed, "cancelled": placed})
    return {
        "execution": {**counters, "states": {"cancelled": placed}},
        "counts": {"events": 100, "decisions": 50, "quotes": 10, "requotes": 5, "cancels": 3, "gate_blocks": 0, "data_blocks": 0},
        "heartbeats": 20, "engine_errors": 0, "last_engine_error": "", "last_block_reason": "",
        "authorization_blocks": 0, "authorization_side_removals": 0, "authorizations": [],
        "ledger": {"fills": 0, "inventory_btc": 0.0},
        "reconciliation": {"count": 3, "failures": 0, "interval_s": 15.0, "last": {"ok": True, "critical": False}},
        "kill_switch": kill, "unknown_orders": [], "open_orders": [], "running": False, "stop_reason": "done",
        "user_stream": {"connected": False, "reports": 6, "balance_updates": 6, "disconnects": 0, "reconnects": 0},
        "is_live": False, "activation": None, "venue": "binance-spot-testnet", "latency": {},
    }


def _judge(module: Any, *, before: dict[str, Any], after: dict[str, Any]) -> dict[str, str]:
    args = Namespace(rest_url=module.REST_URL, ws_url=module.WS_URL, stream_url=module.STREAM_URL, symbol="BTC-USD")
    v = module.ServiceValidation.__new__(module.ServiceValidation)
    v.args, v.ev, v.samples = args, module.Evidence(), [{"kill": before}]
    v.final_status = v.stop_result = _status(kill=after)
    v.open_after_stop = []
    v.judge()
    return v.ev.results


def _shutdown(**extra: Any) -> dict[str, Any]:
    base = {"engaged": False, "sticky": False, "trigger": "", "reason": "shutdown: done", "severity": None, "transient": {}, "shutdown": {"reason": "done", "actor": "validator", "at_ms": 1}, "blocks_quoting": True, "history": []}
    base.update(extra)
    return base


def test_a_clean_run_and_a_clean_shutdown_pass_both_readings(validator_module) -> None:  # type: ignore[no-untyped-def]
    results = _judge(validator_module, before={"engaged": False, "sticky": False, "transient": {}}, after=_shutdown())
    assert results["S10.no_sticky_kill_during_the_run"] == "PASS" and results["S10b.shutdown_recorded_as_shutdown_no_safety_engagement_left"] == "PASS"


def test_a_transient_engagement_during_the_run_is_the_rails_working_not_a_fail(validator_module) -> None:  # type: ignore[no-untyped-def]
    before = {"engaged": True, "sticky": False, "trigger": "data", "transient": {"data": "market data not usable: last event 4151 ms ago"}}
    results = _judge(validator_module, before=before, after=_shutdown())
    assert results["S10.no_sticky_kill_during_the_run"] == "PASS"


def test_a_sticky_safety_kill_during_the_run_fails_and_stays_failed_after_the_stop(validator_module) -> None:  # type: ignore[no-untyped-def]
    before = {"engaged": True, "sticky": True, "trigger": "reconciliation", "reason": "reconciliation: foreign_open_order x1", "transient": {}}
    after = _shutdown(engaged=True, sticky=True, trigger="reconciliation", reason="reconciliation: foreign_open_order x1")
    results = _judge(validator_module, before=before, after=after)
    assert results["S10.no_sticky_kill_during_the_run"] == "FAIL" and results["S10b.shutdown_recorded_as_shutdown_no_safety_engagement_left"] == "FAIL"


def test_a_ghost_transient_after_the_stop_fails_the_shutdown_reading(validator_module) -> None:  # type: ignore[no-untyped-def]
    """The 2026-10-04 Testnet state: shutdown recorded, but a 'data' condition nobody could
    observe any more still attached to the stopped service."""
    after = _shutdown(engaged=True, transient={"data": "market data not usable: venue data 1.1s old"})
    results = _judge(validator_module, before={"engaged": False, "sticky": False, "transient": {}}, after=after)
    assert results["S10.no_sticky_kill_during_the_run"] == "PASS" and results["S10b.shutdown_recorded_as_shutdown_no_safety_engagement_left"] == "FAIL"


def test_a_stop_recorded_as_a_sticky_kill_instead_of_a_shutdown_fails(validator_module) -> None:  # type: ignore[no-untyped-def]
    after = {"engaged": True, "sticky": True, "trigger": "stop", "reason": "stop: done", "severity": "cancel_open", "transient": {}, "shutdown": None, "blocks_quoting": True, "history": []}
    results = _judge(validator_module, before={"engaged": False, "sticky": False, "transient": {}}, after=after)
    assert results["S10b.shutdown_recorded_as_shutdown_no_safety_engagement_left"] == "FAIL"


def test_a_dying_run_leaves_only_the_orders_with_no_cancel_in_flight(validator_module) -> None:  # type: ignore[no-untyped-def]
    """Seen on Testnet (R1, 2026-10-04): the one resting order at death carried a cancel the
    data gate had just requested; the venue completed it. Such an order is on its way out and
    is never counted as left behind; it is listed apart so the evidence says what happened."""

    class Local:
        def __init__(self, order_id: str, state: str, cancel_at: int | None) -> None:
            self.order_id, self.state, self.t_cancel_requested_ms = order_id, state, cancel_at

    left, in_flight = validator_module._left_resting([Local("b", "resting", None), Local("a", "resting", None), Local("c", "resting", 1791131737654), Local("d", "pending_arrival", None), Local("e", "cancelled", 5)])
    assert left == ["a", "b"] and in_flight == ["c"]
    assert validator_module._left_resting([Local("c", "resting", 1)]) == ([], ["c"])  # nothing left: the drill says NOT TESTED, not FAIL
    assert validator_module._left_resting([]) == ([], [])
