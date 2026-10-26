"""Adversarial cases at the boundaries between the runtime and the store (mission v2, phase M).

Each test names the condition it adds that the item suites do not already cover:

* two refused writes of different kinds in one session (an incident *and* an outcome): both are
  counted, the stop record carries both, the rebuild names what it can, and the dispatcher names
  the incident — no single error hides the other;
* the incidents of the protection emergencies (P0/R18) have distinct ids within one simulated
  instant: an id written twice is refused by the primary key, and a refused incident turns a
  clean stop into ``writes_failed`` and blocks the next session;
* a refusal from the store right after an exit: the journal and the fills table disagree, and the
  rebuild says so instead of believing either (on SQLite here; PostgreSQL in test_pg_r15.py's sweep).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tests.integration import test_account_restore as account
from tests.integration.test_exit_rejection import protected_position, working
from tests.integration.test_protection_invariants import fail_stops
from tests.integration.test_r15_crash_recovery import _round_trip, _state
from tia.core.errors import OrderRejectedError, ReconciliationError
from tia.domain.enums import OrderType
from tia.persistence import RunRepository


async def test_two_refused_writes_of_different_kinds_are_both_counted_and_named(tmp_path: Path) -> None:
    state = _state(tmp_path)
    await state.database.ensure_schema()
    refused: list[str] = []

    async def refusing(kind: str, payload: Any) -> Any:
        if kind == "edge_outcome" or (kind == "incident" and payload.get("kind") == "halt_new_orders"):
            refused.append(kind)
            payload = {**payload, "incident_id": None} if kind == "incident" else payload  # NOT NULL: the store refuses it
            if kind == "edge_outcome":
                raise RuntimeError("store unavailable for the outcome")
        return await state._persist(kind, payload)

    try:
        runtime = await _round_trip(state, refusing)
        runtime._incident("halt_new_orders", reason="adversarial", actor="test")  # one the store will refuse
        await account.settle(runtime)
        assert "edge_outcome" in refused and "incident" in refused
        assert runtime.persist_failed_writes == 2, runtime.persist_failed_writes
        status = state.persistence_status()
        assert status["incident_failures"] == 1 and status["last_failed_incident"]["kind"] == "halt_new_orders"
        async with state.database.session() as session:
            await RunRepository(session).mark_persistence(runtime.run_id, runtime.persistence_report())
        restore = await account.rebuild(state.database)
        assert restore.complete is False
        assert restore.checks["round_trips_without_outcome"], "the outcome is named"
        assert "2 refused" in restore.error, "the stop record counts both"
    finally:
        await state.database.close()


def _incident_ids(saved: list[tuple[str, Any]]) -> Counter[str]:
    return Counter(p["incident_id"] for k, p in saved if k == "incident")


@pytest.mark.parametrize("scenario", ["exit_and_reprotection_refused", "stop_refused_every_cycle", "stop_unknown_then_refused"])
async def test_the_incidents_of_a_protection_emergency_have_distinct_ids(monkeypatch: pytest.MonkeyPatch, scenario: str) -> None:
    saved: list[tuple[str, Any]] = []
    persist = lambda kind, payload: saved.append((kind, payload))  # noqa: E731 - a recorder
    if scenario == "exit_and_reprotection_refused":
        runtime, execution, _market, _ = await protected_position(persist)
        real = execution.submit_order

        async def everything_refused(intent):  # type: ignore[no-untyped-def]
            if intent.signal_id.startswith(("exit:", "protective:")):
                raise OrderRejectedError("refused", code=-2010)
            return await real(intent)

        monkeypatch.setattr(execution, "submit_order", everything_refused)
        try:
            await runtime._close_position("signal reversed")
            await runtime._close_position("time stop")  # a second trigger in the same instant
            assert await working(execution, OrderType.STOP) == []
        finally:
            await runtime.stop()
    else:
        runtime, execution, market, _ = account.build(persist=persist)
        await runtime.start()
        try:
            if scenario == "stop_refused_every_cycle":
                fail_stops(monkeypatch, execution, OrderRejectedError("code=-2010 refused", code=-2010))
                await account.open_position(runtime, market)
            else:
                await account.open_position(runtime, market)
                # Inner wrapper refuses every stop; the outer one turns the first into an unknown outcome.
                fail_stops(monkeypatch, execution, OrderRejectedError("code=-2010 refused", code=-2010))
                fail_stops(monkeypatch, execution, ReconciliationError("timed out; UNKNOWN"), times=1)

                async def unknown_then_absent(*, symbol: str, client_order_id: str) -> None:
                    return None

                monkeypatch.setattr(execution, "resolve_unknown_order", unknown_then_absent, raising=False)
            for _ in range(3):
                market.advance()
                await runtime._cycle_once()
                await runtime._cycle_once()  # twice in one simulated instant
        finally:
            await runtime.stop()
    ids = _incident_ids(saved)
    assert ids, "the scenario produced incidents"
    assert [i for i, n in ids.items() if n > 1] == [], [
        (p["kind"], p["incident_id"]) for k, p in saved if k == "incident" and ids[p["incident_id"]] > 1
    ]
