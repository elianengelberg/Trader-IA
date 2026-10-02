"""The market maker's own kill switch: engages, cancels, is seen by the global gate, is
released by a named person, and never lifts anything above it."""

from __future__ import annotations

import pytest

from tia.domain.enums import SystemMode
from tia.mm.kill_switch import KillSeverity, MMKillSwitch
from tia.mm.safety import GlobalTradingSafetyGate, SafetyState
from tia.risk.engine import RiskState

T0 = 1_789_754_400_000


def _switch(clock: dict[str, int]):  # type: ignore[no-untyped-def]
    cancels: list[tuple[int, str]] = []
    events: list[dict] = []  # type: ignore[type-arg]

    def cancel_open(t_ms: int, reason: str) -> int:
        cancels.append((t_ms, reason))
        return 2

    return MMKillSwitch(now_ms=lambda: clock["ms"], cancel_open=cancel_open, on_event=events.append), cancels, events


def test_a_sticky_engagement_cancels_and_stays_until_a_named_person_releases_it() -> None:
    clock = {"ms": T0}
    switch, cancels, events = _switch(clock)
    assert not switch.engaged and switch.status() == ""
    event = switch.engage("unknown_fill", "trade 7 on an order we did not place", severity=KillSeverity.CANCEL_OPEN)
    assert switch.engaged and switch.sticky and switch.status() == "unknown_fill: trade 7 on an order we did not place"
    assert cancels == [(T0, "kill switch (unknown_fill): trade 7 on an order we did not place")] and event.cancelled == 2
    assert switch.cancelled_total == 2 and switch.engaged_at_ms == T0 and switch.severity is KillSeverity.CANCEL_OPEN
    with pytest.raises(ValueError, match="naming who approved"):
        switch.release(approved_by="  ")
    clock["ms"] += 1_000
    released = switch.release(approved_by="elian")
    assert not switch.engaged and switch.status() == "" and released.actor == "elian" and released.action == "release"
    assert [e["action"] for e in events] == ["engage", "release"] and events[0]["kind"] == "kill_switch"
    assert switch.as_dict()["history"][-1]["action"] == "release" and switch.engagements == 1


def test_no_new_quotes_does_not_cancel_and_severity_only_escalates() -> None:
    clock = {"ms": T0}
    switch, cancels, _ = _switch(clock)
    switch.engage("excessive_api_errors", "11 errors", severity=KillSeverity.NO_NEW_QUOTES)
    assert cancels == [] and switch.severity is KillSeverity.NO_NEW_QUOTES
    switch.engage("foreign_open_order", "someone else", severity=KillSeverity.CANCEL_OPEN)
    assert len(cancels) == 1 and switch.severity is KillSeverity.CANCEL_OPEN
    assert switch.trigger == "excessive_api_errors" and switch.history[-1].trigger == "foreign_open_order"  # first cause kept, later one recorded
    switch.engage("activation", "expired", severity=KillSeverity.NO_NEW_QUOTES)
    assert switch.severity is KillSeverity.CANCEL_OPEN  # never relaxed by a later, milder engagement


def test_a_transient_condition_clears_itself_and_a_sticky_one_does_not() -> None:
    clock = {"ms": T0}
    switch, cancels, _ = _switch(clock)
    switch.engage("data", "stream disconnected", severity=KillSeverity.CANCEL_OPEN, sticky=False)
    assert switch.engaged and not switch.sticky and switch.status() == "data: stream disconnected" and len(cancels) == 1
    assert switch.clear("something_else") is False
    assert switch.clear("data") is True and not switch.engaged and switch.severity is None
    switch.engage("data", "stale", sticky=False)
    switch.engage("operator", "stop", actor="elian")
    switch.clear("data")
    assert switch.engaged and switch.status() == "operator: stop"  # the sticky one remains
    switch.release(approved_by="elian")
    assert not switch.engaged
    switch.engage("operator", "stop", actor="elian")
    switch.engage("data", "stale", sticky=False)
    switch.release(approved_by="elian")
    assert switch.engaged and switch.status() == "data: stale"  # the transient one remains


def test_the_global_gate_sees_it_and_the_global_halt_is_never_lifted_by_it() -> None:
    clock = {"ms": T0}
    switch, _, _ = _switch(clock)
    state = RiskState()
    gate = GlobalTradingSafetyGate(risk_state=lambda: state, data_usable=lambda: (True, ""), system_unsafe=switch.status)
    assert gate.status(T0).state is SafetyState.SAFE
    switch.engage("reconciliation", "balance mismatch")
    status = gate.status(T0 + 1)
    assert status.state is SafetyState.SYSTEM_UNSAFE and "reconciliation: balance mismatch" in status.reason and not status.allows_quoting
    state.mode = SystemMode.HALTED
    state.kill_switch_reason = "session kill switch"
    switch.release(approved_by="elian")
    halted = gate.status(T0 + 2)
    assert halted.state is SafetyState.HALTED  # releasing the maker's switch changes nothing above it
    state.mode = SystemMode.NORMAL
    assert gate.status(T0 + 3).state is SafetyState.SAFE


def test_the_snapshot_is_complete_and_bounded() -> None:
    clock = {"ms": T0}
    switch, _, _ = _switch(clock)
    for i in range(300):
        switch.engage("api", f"error {i}", severity=KillSeverity.NO_NEW_QUOTES, sticky=False)
        switch.clear("api")
    snap = switch.as_dict()
    assert len(switch.history) == 200 and len(snap["history"]) == 20 and snap["engagements"] == 300 and snap["engaged"] is False
    assert "never remove one" in snap["note"]
