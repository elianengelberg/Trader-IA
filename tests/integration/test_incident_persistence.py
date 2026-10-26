"""R24-H1 — what happens to an incident on its way to the store (SQLite; the PostgreSQL twin is
``tests/postgres/test_pg_incidents.py``).

* An invalid kind is never truncated and never refused into oblivion: the row is written under
  ``incident_kind_invalid`` with the original kept in ``detail``, and the refusal is logged.
* A write the store refuses is not reported as a write: ``_persist`` answers ``False``, nothing
  is left half-written, and ``persistence_status()`` names the incident that was not recorded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from tests.unit.test_incident_kind_contract import invalid_kind, limit
from tia.core.config import Environment, settings_for_env
from tia.persistence import IncidentRepository
from tia.persistence.models import IncidentRow


def _state(tmp_path: Path) -> Any:
    from tia.api.state import AppState

    url = f"sqlite+aiosqlite:///{tmp_path / 'incidents.db'}"
    return AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": url}))


def _incident(incident_id: str, kind: object, **extra: Any) -> dict[str, Any]:
    return {"incident_id": incident_id, "at": datetime(2026, 10, 25, 12, 0, tzinfo=UTC), "kind": kind,
            "actor": "system", "reason": "test", "run_id": "live_t", "detail": {"k": 1}, **extra}


async def _rows(state: Any) -> list[IncidentRow]:
    async with state.database.session() as session:
        return list((await session.execute(select(IncidentRow).order_by(IncidentRow.incident_id))).scalars())


@pytest.mark.parametrize("kind", ["too_long", "", "Has Space", None], ids=["too_long", "empty", "bad_chars", "none"])
async def test_an_invalid_kind_is_kept_under_an_explicit_kind_not_cut_or_lost(tmp_path: Path, kind: object, monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.persistence.repositories as repositories

    if kind == "too_long":
        kind = "x" * (limit() + 1)

    errors: list[str] = []
    monkeypatch.setattr(repositories._log, "error", lambda event, **kw: errors.append(event))
    state = _state(tmp_path)
    await state.database.ensure_schema()
    try:
        assert await state._persist("incident", _incident("inc_bad", kind)) is True
        [row] = await _rows(state)
        assert row.kind == invalid_kind()
        assert row.detail["invalid_kind"] == repr(kind)[:500] and row.detail["k"] == 1, "the original is kept"
        assert row.detail["invalid_kind_problem"]
        assert "incident_kind_invalid" in errors
    finally:
        await state.database.close()


async def test_a_refused_incident_write_is_not_claimed_and_says_which_incident(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.api.state as state_mod

    errors: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(state_mod._log, "error", lambda event, **kw: errors.append((event, kw)))
    state = _state(tmp_path)
    await state.database.ensure_schema()
    try:
        assert await state._persist("incident", _incident("inc_1", "protection_failed")) is True
        # The same id again: the store refuses it (primary key). Nothing else may change.
        assert await state._persist("incident", _incident("inc_1", "entries_blocked:protection_failed", reason="other")) is False
        rows = await _rows(state)
        assert [(r.incident_id, r.kind, r.reason) for r in rows] == [("inc_1", "protection_failed", "test")]
        status = state.persistence_status()
        assert status["failures"] == 1 and status["incident_failures"] == 1
        assert status["last_failed_incident"]["incident_id"] == "inc_1"
        assert status["last_failed_incident"]["kind"] == "entries_blocked:protection_failed"
        assert [e for e, _ in errors] == ["incident_not_recorded"]
        assert errors[0][1]["incident_kind"] == "entries_blocked:protection_failed"
    finally:
        await state.database.close()


async def test_a_session_that_fails_leaves_none_of_its_incidents(tmp_path: Path) -> None:
    """The store's own atomicity, pinned: an incident that shares a transaction with a refused
    write goes with it. Each runtime incident is written in a session of its own for that reason."""
    state = _state(tmp_path)
    await state.database.ensure_schema()
    try:
        await state._persist("incident", _incident("inc_dup", "safe_mode"))
        with pytest.raises(IntegrityError):
            async with state.database.session() as session:
                await IncidentRepository(session).record(_incident("inc_new", "halt_new_orders"))
                await IncidentRepository(session).record(_incident("inc_dup", "safe_mode"))
        async with state.database.session() as session:
            assert (await session.execute(select(func.count()).select_from(IncidentRow))).scalar_one() == 1
    finally:
        await state.database.close()
