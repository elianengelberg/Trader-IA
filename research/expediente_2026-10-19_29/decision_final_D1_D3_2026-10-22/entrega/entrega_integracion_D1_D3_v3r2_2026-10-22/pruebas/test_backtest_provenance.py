"""A backtest result says which engine computed it, and the store never takes one for another.

Before the engine was recorded, ``run_id`` hashed the dataset's *name* and the
configuration: the same experiment re-run after an engine change got the same id, and
``BacktestRepository.save`` — an upsert — replaced the old engine's result with the new
one's without a word. So did one dataset name over other bars (the API's ``bars`` limit).
Now the engine version, a fingerprint of its source, the bars and the instruments are in
the id and in the conditions, and the store refuses to replace a row of another
provenance — or a row of the same provenance with other numbers, which means something the
provenance does not record changed. Rows stored before keep their id and their missing
fields: engine unknown.
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx
import pytest
from asgi_lifespan import LifespanManager

import tia.backtest.engine as engine_module
from tia.api.app import create_app
from tia.backtest import BacktestConfig, BacktestEngine, BacktestResult
from tia.backtest.engine import ENGINE_VERSION
from tia.core.config import Environment, ExecutionSimConfig, settings_for_env
from tia.core.ids import deterministic_id
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.execution.paper import PaperExecutionProvider
from tia.persistence import BacktestRepository, Database

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures"
SERIES = asyncio.run(CsvReplayProvider(FIXTURES).get_candles("BTC-USD", "1h", limit=400))
CONFIG = BacktestConfig(
    dataset="fixtures:BTC-USD:1h",
    timeframe="1h",
    warmup_bars=120,
    execution=ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0),
)
PROVENANCE = ("engine_version", "engine_fingerprint", "data_fingerprint", "universe_digest")


def _run(series=SERIES, **engine_kwargs: Any) -> BacktestResult:  # type: ignore[no-untyped-def]
    return BacktestEngine(CONFIG, DEFAULT_UNIVERSE, **engine_kwargs).run(series)


def _row(result: BacktestResult) -> dict[str, Any]:
    """The columns ``AppState.run_backtest`` stores that this file reads back."""
    c = result.conditions
    return {
        "run_id": c.run_id,
        "created_at": datetime(2026, 10, 22, 12, tzinfo=UTC),
        "dataset": c.dataset,
        "symbols": list(c.symbols),
        "timeframe": c.timeframe,
        "bars": c.bars,
        "seed": c.seed,
        "total_return_pct": result.metrics.total_return_pct,
        "max_drawdown_pct": result.metrics.max_drawdown_pct,
        "sharpe": result.metrics.sharpe,
        "trades": len(result.trades),
        "equity_curve": [round(v, 4) for v in result.equity_curve[::5]],
        "warnings": list(result.warnings),
        "conditions": c.model_dump(mode="json"),
    }


def _legacy_row(result: BacktestResult) -> dict[str, Any]:
    """The same experiment as the engine before the version was recorded stored it: the
    old id (dataset name, symbol, configuration digest), no provenance, its own numbers."""
    row = _row(result)
    row["run_id"] = deterministic_id("bt", CONFIG.dataset, "BTC-USD", CONFIG.digest())
    row["conditions"] = {k: v for k, v in row["conditions"].items() if k not in PROVENANCE}
    row["conditions"]["run_id"] = row["run_id"]
    row["total_return_pct"] = -1.2345  # what the old engine said; it must survive as said
    row["created_at"] = datetime(2026, 10, 1, tzinfo=UTC)
    return row


class _RejectsTheFirstOrder(PaperExecutionProvider):
    """A part of the engine substituted by the caller: invisible to the provenance, visible
    in the numbers — as a change of environment would be."""

    seen: ClassVar[list[int]] = []  # reset by the test; shared because the engine builds the provider

    def _should_reject(self, order):  # type: ignore[no-untyped-def]
        self.seen.append(1)
        return len(self.seen) == 1 or super()._should_reject(order)


async def _store(tmp_path: Path) -> Database:
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'backtests.db'}")
    await db.create_schema()
    return db


async def _save(db: Database, row: dict[str, Any]) -> None:
    async with db.session() as session:
        await BacktestRepository(session).save(row)


async def _rows(db: Database) -> dict[str, Any]:
    async with db.session() as session:
        return {row.run_id: row for row in await BacktestRepository(session).list_recent()}


# ----------------------------------------------------------------- what is in the id


def test_a_result_records_its_engine_its_bars_and_its_instruments() -> None:
    conditions = _run().conditions
    assert conditions.engine_version == ENGINE_VERSION
    assert conditions.engine_fingerprint == engine_module.engine_fingerprint()
    assert len(conditions.engine_fingerprint) == 32
    assert len(conditions.data_fingerprint) == 32
    assert len(conditions.universe_digest) == 32


def test_another_engine_version_is_another_run(monkeypatch: pytest.MonkeyPatch) -> None:
    before = _run().conditions
    monkeypatch.setattr(engine_module, "ENGINE_VERSION", "9.9.9")
    after = _run().conditions
    assert after.engine_version == "9.9.9"
    assert after.run_id != before.run_id


def test_an_engine_change_nobody_versioned_is_another_run(monkeypatch: pytest.MonkeyPatch) -> None:
    before = _run().conditions
    monkeypatch.setattr(engine_module, "engine_fingerprint", lambda: "0" * 32)
    after = _run().conditions
    assert after.engine_version == before.engine_version
    assert after.run_id != before.run_id


def test_the_fingerprint_follows_the_engine_source_and_nothing_else(tmp_path: Path) -> None:
    root = tmp_path / "tia"
    shutil.copytree(
        Path(engine_module.__file__).resolve().parent.parent, root,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    original = engine_module._source_fingerprint(root)
    assert original == engine_module.engine_fingerprint()
    outside = root / "api" / "state.py"
    outside.write_text(outside.read_text() + "\n# not the engine\n")
    assert engine_module._source_fingerprint(root) == original
    inside = root / "execution" / "paper.py"
    inside.write_text(inside.read_text() + "\n# one comment\n")
    assert engine_module._source_fingerprint(root) != original


def test_a_fingerprint_that_cannot_be_read_says_so(tmp_path: Path) -> None:
    assert engine_module._source_fingerprint(tmp_path) == "unavailable"


def test_one_dataset_name_over_other_bars_is_another_run() -> None:
    whole = _run().conditions
    fewer = _run(SERIES[:350]).conditions
    last = SERIES[-1]
    touched = _run([*SERIES[:-1], last.model_copy(update={"volume": last.volume + 1.0})]).conditions
    assert whole.dataset == fewer.dataset == touched.dataset
    assert len({whole.run_id, fewer.run_id, touched.run_id}) == 3
    assert len({whole.data_fingerprint, fewer.data_fingerprint, touched.data_fingerprint}) == 3


def test_another_strategy_set_is_another_run() -> None:
    one = _run(strategies=CONFIG.strategy.enabled[:1]).conditions
    assert one.run_id != _run().conditions.run_id


def test_the_same_engine_on_the_same_bars_is_the_same_run() -> None:
    assert _run().conditions == _run().conditions


# ----------------------------------------------------------------------- the store


async def test_a_result_stored_before_the_engine_was_recorded_stays_beside_the_new_one(
    tmp_path: Path,
) -> None:
    result = _run()
    legacy = _legacy_row(result)
    db = await _store(tmp_path)
    try:
        await _save(db, legacy)
        await _save(db, _row(result))
        rows = await _rows(db)
        assert set(rows) == {legacy["run_id"], result.conditions.run_id}
        old = rows[legacy["run_id"]]
        assert old.total_return_pct == legacy["total_return_pct"]
        assert old.conditions == legacy["conditions"]
        assert not set(PROVENANCE) & set(old.conditions), "unknown, and not backfilled"
        assert rows[result.conditions.run_id].conditions["engine_version"] == ENGINE_VERSION
    finally:
        await db.close()


async def test_the_store_refuses_to_replace_a_result_of_another_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run()
    legacy = _legacy_row(result)
    db = await _store(tmp_path)
    try:
        await _save(db, legacy)
        await _save(db, _row(result))
        # The legacy id with the current engine's result: what the upsert used to accept.
        with pytest.raises(ValueError, match="another provenance"):
            await _save(db, {**_row(result), "run_id": legacy["run_id"]})
        # The current id with another engine's result, however it came to share it.
        monkeypatch.setattr(engine_module, "ENGINE_VERSION", "9.9.9")
        other = _row(_run())
        with pytest.raises(ValueError, match="another provenance"):
            await _save(db, {**other, "run_id": result.conditions.run_id})
        rows = await _rows(db)
        assert rows[legacy["run_id"]].conditions == legacy["conditions"]
        assert rows[legacy["run_id"]].total_return_pct == legacy["total_return_pct"]
        assert rows[result.conditions.run_id].conditions == result.conditions.model_dump(mode="json")
    finally:
        await db.close()


async def test_a_rerun_of_the_same_engine_over_the_same_bars_replaces_only_itself(
    tmp_path: Path,
) -> None:
    first, second = _row(_run()), _row(_run())
    second["created_at"] = datetime(2026, 10, 22, 13, tzinfo=UTC)
    db = await _store(tmp_path)
    try:
        await _save(db, first)
        await _save(db, second)
        rows = await _rows(db)
        assert list(rows) == [first["run_id"]]
        assert rows[first["run_id"]].conditions == first["conditions"]
    finally:
        await db.close()


async def test_other_numbers_under_the_same_provenance_are_refused_not_kept_as_the_last_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the provenance does not record can change the numbers without changing the id.
    The store does not keep whichever ran last: it refuses, and the first result stays."""
    first = _run()
    monkeypatch.setattr(engine_module, "PaperExecutionProvider", _RejectsTheFirstOrder)
    monkeypatch.setattr(_RejectsTheFirstOrder, "seen", [])
    other = _run()
    assert other.conditions == first.conditions, "same id, same recorded provenance"
    assert len(other.trades) != len(first.trades), "and other numbers"
    db = await _store(tmp_path)
    try:
        await _save(db, _row(first))
        with pytest.raises(ValueError, match="same provenance and other results"):
            await _save(db, _row(other))
        kept = (await _rows(db))[first.conditions.run_id]
        assert kept.trades == len(first.trades)
        assert kept.total_return_pct == first.metrics.total_return_pct
    finally:
        await db.close()


async def test_an_undefined_ratio_does_not_make_a_rerun_look_different(tmp_path: Path) -> None:
    """SQLite stores NaN as NULL: a re-run that carries NaN again is still the same run."""
    row = {**_row(_run()), "sharpe": float("nan")}
    db = await _store(tmp_path)
    try:
        await _save(db, row)
        await _save(db, {**row, "created_at": datetime(2026, 10, 22, 13, tzinfo=UTC)})
        assert list(await _rows(db)) == [row["run_id"]]
    finally:
        await db.close()


async def test_the_api_lists_the_engine_of_each_result_and_unknown_for_the_old_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIA_DEMO_USER", "provenance-operator")
    monkeypatch.setenv("TIA_DEMO_PASSWORD", "provenance-password-not-a-secret")
    settings = settings_for_env(Environment.TESTING).model_copy(
        update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"}
    )
    app = create_app(settings)
    result = _run()
    legacy = _legacy_row(result)
    async with LifespanManager(app):
        await _save(app.state.tia.database, legacy)
        await _save(app.state.tia.database, _row(result))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            login = await client.post(
                "/api/auth/login",
                json={"username": "provenance-operator", "password": "provenance-password-not-a-secret"},
            )
            assert login.status_code == 200, login.text
            listed = {row["run_id"]: row for row in (await client.get("/api/backtests")).json()}
    assert listed[legacy["run_id"]]["engine_version"] is None
    assert listed[legacy["run_id"]]["total_return_pct"] == legacy["total_return_pct"]
    assert listed[result.conditions.run_id]["engine_version"] == ENGINE_VERSION
