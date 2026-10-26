"""R24-H2 — the evidence refresher does not depend on commit order to see every row.

``refresh_session_evidence`` reads ``edge_outcomes`` forward from a watermark, the newest
``ingested_at`` it has seen. On PostgreSQL ``ingested_at`` defaults to the *start* of the writing
transaction, so a training batch that opened before the session's own close and committed after
the refresher ran carries a stamp older than the watermark and was never read (the PostgreSQL
interleaving is ``tests/postgres/test_pg_concurrency.py``). The watermark stays the fast path; a
count of the table, compared with what the session holds, is the completeness check, and a
mismatch is resolved by id. Here the late row is written with an old stamp directly, which is
what the late commit looks like to the reader, so the property is pinned on SQLite too.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tia.core.config import Environment, settings_for_env
from tia.persistence import EdgeStateRepository

AT = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


class _RunningSession:
    run_id = "live_session"
    is_running = True

    def __init__(self) -> None:
        self.absorbed: list[str] = []

    def absorb_evidence(self, *, outcomes: Any, reviews: Any) -> dict[str, Any]:
        self.absorbed.extend(review["signal_id"] for review in reviews)
        return {}


def _outcome(outcome_id: str, run_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "outcome_id": outcome_id, "run_id": run_id, "signal_id": outcome_id, "symbol": "BTC-USD",
        "regime": "trending_up", "direction": "long", "confidence": 0.7, "entry_price": 50_000.0,
        "exit_price": 50_100.0, "quantity": 0.01, "gross_bps": 20.0, "fees_bps": 10.0,
        "net_bps": 10.0, "closed_at": AT, "source": "sim", **extra,
    }


async def _state(tmp_path: Path) -> tuple[Any, _RunningSession]:
    from tia.api.state import AppState

    url = f"sqlite+aiosqlite:///{tmp_path / 'evidence.db'}"
    state = AppState(settings_for_env(Environment.TESTING).model_copy(update={"database_url": url}))
    await state.database.ensure_schema()
    session = _RunningSession()
    state.live_runtime = session
    return state, session


async def _write(state: Any, values: dict[str, Any]) -> None:
    async with state.database.session() as db:
        await EdgeStateRepository(db).append(values)


async def test_a_row_stamped_before_the_watermark_still_reaches_the_session(tmp_path: Path) -> None:
    state, session = await _state(tmp_path)
    try:
        await _write(state, _outcome("first", "train_a"))
        assert (await state.refresh_session_evidence())["absorbed"] == 1
        watermark = state._evidence_watermark
        assert watermark is not None
        # What a batch that opened earlier and committed later looks like to the reader.
        await _write(state, _outcome("late", "train_b", ingested_at=watermark - timedelta(minutes=5)))
        result = await state.refresh_session_evidence()
        assert session.absorbed == ["first", "late"], result
        assert (await state.refresh_session_evidence())["absorbed"] == 0, "never twice"
        assert session.absorbed == ["first", "late"]
    finally:
        state.live_runtime = None
        await state.database.close()


async def test_the_sessions_own_rows_found_by_the_check_are_still_not_fed_back(tmp_path: Path) -> None:
    state, session = await _state(tmp_path)
    try:
        await _write(state, _outcome("first", "train_a"))
        await state.refresh_session_evidence()
        old = state._evidence_watermark - timedelta(minutes=5)
        await _write(state, _outcome("own-late", "live_session", ingested_at=old))
        await _write(state, _outcome("batch-late", "train_b", ingested_at=old))
        await state.refresh_session_evidence()
        assert session.absorbed == ["first", "batch-late"], "the session's own trade is already in its memory"
        assert {"own-late", "batch-late"} <= state._absorbed_evidence_ids
    finally:
        state.live_runtime = None
        await state.database.close()


async def test_a_refresh_with_nothing_missed_does_not_read_the_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The check costs a count when nothing was missed; the id read happens only on a mismatch."""
    calls: list[str] = []
    real = getattr(EdgeStateRepository, "ids", None)

    async def ids(self: EdgeStateRepository) -> Any:
        calls.append("ids")
        assert real is not None
        return await real(self)

    monkeypatch.setattr(EdgeStateRepository, "ids", ids, raising=False)
    state, session = await _state(tmp_path)
    try:
        # Explicit, distinct stamps: SQLite's own CURRENT_TIMESTAMP has whole seconds and makes
        # the watermark's boundary exclusive (R24-O1), which would trigger the check for a row
        # written in the same second — correctly, but this test pins the quiet path.
        start = datetime.now(UTC)
        for i in range(3):
            await _write(state, _outcome(f"o{i}", "train_a", ingested_at=start + timedelta(seconds=i)))
            await state.refresh_session_evidence()
        assert calls == [] and session.absorbed == ["o0", "o1", "o2"]
        await _write(state, _outcome("late", "train_b", ingested_at=state._evidence_watermark - timedelta(minutes=5)))
        await state.refresh_session_evidence()
        assert calls == ["ids"] and session.absorbed[-1] == "late"
    finally:
        state.live_runtime = None
        await state.database.close()
