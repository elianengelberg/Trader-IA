"""The validation session through the API: ``max_hours`` sets a deadline the runtime
enforces, the run row carries it, and a boot that finds an interrupted run decides from
it — resume under the same deadline, or not at all once it has passed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.integration.test_live_api import PASSWORD, USERNAME, _client, _settings
from tia.api.app import create_app
from tia.persistence import Database
from tia.runtime.session_limits import decode_session_deadline, encode_session_notes


@pytest.fixture(autouse=True)
def _feed_and_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    import tia.data.providers.binance_public as binance_public
    from tests.integration.test_live_api import _FakePublicFeed

    monkeypatch.setenv("TIA_DEMO_USER", USERNAME)
    monkeypatch.setenv("TIA_DEMO_PASSWORD", PASSWORD)
    monkeypatch.setattr(binance_public, "BinancePublicProvider", _FakePublicFeed)


async def _run_rows(tmp_path: Path) -> list[tuple[str, str | None, object]]:
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'live.db'}")
    try:
        async with db.session() as session:
            rows = (
                await session.execute(
                    text("SELECT run_id, notes, stopped_at FROM runs WHERE mode = 'paper-live' ORDER BY started_at")
                )
            ).all()
        return [(str(r[0]), r[1], r[2]) for r in rows]
    finally:
        await db.close()


async def test_max_hours_sets_a_deadline_the_snapshot_shows_and_the_run_row_carries(tmp_path: Path) -> None:
    before = datetime.now(UTC)
    async for http in _client(create_app(_settings(tmp_path))):
        started = await http.post("/api/live/paper-start?max_hours=8")
        assert started.status_code == 200, started.text
        session = started.json()["session"]
        deadline = datetime.fromisoformat(session["deadline_at"])
        assert timedelta(hours=7, minutes=59) < deadline - before < timedelta(hours=8, minutes=1)
        assert session["max_hours"] == 8.0
        assert session["winding_down"] is False
        assert (await http.post("/api/live/stop")).status_code == 200

    rows = await _run_rows(tmp_path)
    assert len(rows) == 1
    assert decode_session_deadline(rows[0][1]) == deadline
    assert rows[0][2] is not None, "an operator stop stamps the row"


async def test_without_max_hours_the_session_has_no_deadline(tmp_path: Path) -> None:
    async for http in _client(create_app(_settings(tmp_path))):
        started = await http.post("/api/live/paper-start")
        assert started.status_code == 200, started.text
        assert started.json()["session"]["deadline_at"] is None
        assert (await http.post("/api/live/stop")).status_code == 200
    rows = await _run_rows(tmp_path)
    assert rows[0][1] in ("", None)


async def test_max_hours_is_validated(tmp_path: Path) -> None:
    async for http in _client(create_app(_settings(tmp_path))):
        assert (await http.post("/api/live/paper-start?max_hours=-1")).status_code == 422
        assert (await http.post("/api/live/paper-start?max_hours=10000")).status_code == 422
        assert (await http.get("/api/live")).json()["active"] is False


async def test_a_crash_interrupted_validation_session_resumes_under_the_same_deadline(tmp_path: Path) -> None:
    """Boot 1 starts an 8-hour session and the process dies (lifespan exit, no stamp).
    Boot 2 resumes it — under the deadline boot 1 set, not a fresh eight hours."""
    async for http in _client(create_app(_settings(tmp_path))):
        started = await http.post("/api/live/paper-start?max_hours=8")
        assert started.status_code == 200, started.text
        first_deadline = started.json()["session"]["deadline_at"]

    async for http in _client(create_app(_settings(tmp_path))):
        snapshot = (await http.get("/api/live")).json()
        assert snapshot["active"] is True
        assert snapshot["session"]["deadline_at"] == first_deadline
        assert snapshot["session"]["max_hours"] is None, "resumed under a deadline, not a span"
        assert (await http.post("/api/live/stop")).status_code == 200

    rows = await _run_rows(tmp_path)
    assert len(rows) == 2, "the interrupted run and the resumed one"
    assert decode_session_deadline(rows[1][1]) == datetime.fromisoformat(first_deadline)


async def test_an_interrupted_session_whose_deadline_has_passed_is_not_resumed(tmp_path: Path) -> None:
    """A run row left unstamped with an expired deadline: the boot stamps it and starts
    nothing — a new session is a person's decision."""
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'live.db'}")
    try:
        await db.ensure_schema()
        async with db.session() as session:
            await session.execute(
                text(
                    "INSERT INTO runs (run_id, mode, scenario, started_at, initial_capital, seed, "
                    "symbols, config_digest, notes) VALUES (:id, 'paper-live', 'realtime', :at, "
                    "10000.0, 1, '[\"BTC-USD\"]', '', :notes)"
                ),
                {
                    "id": "live_expired",
                    "at": datetime.now(UTC) - timedelta(hours=9),
                    "notes": encode_session_notes(
                        deadline=datetime.now(UTC) - timedelta(hours=1), max_hours=8.0
                    ),
                },
            )
    finally:
        await db.close()

    async for http in _client(create_app(_settings(tmp_path))):
        assert (await http.get("/api/live")).json()["active"] is False

    rows = await _run_rows(tmp_path)
    assert len(rows) == 1 and rows[0][0] == "live_expired"
    assert rows[0][2] is not None, "stamped as over"
