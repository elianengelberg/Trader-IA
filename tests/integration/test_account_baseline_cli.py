"""``scripts/account_baseline.py``: the dry run writes nothing and shows every refusal the
real run would hit; ``--apply`` writes one event and reports the rebuild afterwards. No
network, no credential printed."""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.integration.test_account_restore import (
    _db,
    _legacy_day,
    _stop_run,
    _write_legacy_fills,
    rebuild,
    register_run,
)
from tia.persistence import AccountJournalRepository

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture(scope="module")
def cli():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("account_baseline")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_the_database_url_is_printed_without_its_password(cli) -> None:  # type: ignore[no-untyped-def]
    assert cli.redact("postgresql+asyncpg://tia:s3cret@postgres:5432/tia") == "postgresql+asyncpg://***@postgres:5432/tia"
    assert cli.redact("sqlite+aiosqlite:///./data/runtime/tia.db") == "sqlite+aiosqlite:///./data/runtime/tia.db"


async def test_dry_run_then_apply_over_a_legacy_record(tmp_path: Path, cli, capsys) -> None:  # type: ignore[no-untyped-def]
    db = _db(tmp_path, "cli.db")
    await db.create_schema()
    url = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    try:
        t0 = datetime.now(UTC) - timedelta(days=2)
        await register_run(db, "run_legacy", started_at=t0)
        await _write_legacy_fills(db, "run_legacy", _legacy_day(t0))
        await _stop_run(db, "run_legacy", t0 + timedelta(hours=12))
    finally:
        await db.close()

    # Dry run: the legacy fills are listed, the baseline is shown, nothing is written.
    assert await cli.run(_args(cli, ["--db", url])) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "nothing written" in out and "s3cret" not in out
    assert out.count("run run_legacy (paper-live)") == 5 and "lf5" in out
    assert "account.* events (0: 0 moving the account" in out
    assert '"legacy_fills": 5' in out
    db = _db(tmp_path, "cli.db")
    try:
        assert (await rebuild(db)).complete is False
        async with db.session() as session:
            assert await AccountJournalRepository(session).account_event_count(modes=("paper-live",)) == 0
    finally:
        await db.close()

    # Apply: one event, and the rebuild afterwards is complete.
    assert await cli.run(_args(cli, ["--db", url, "--apply", "--reason", "fills predate the journal", "--actor", "op"])) == 0
    out = capsys.readouterr().out
    assert "PASS  complete" in out and "checks.legacy_fills_excluded: 5" in out
    db = _db(tmp_path, "cli.db")
    try:
        after = await rebuild(db)
        assert after.complete and after.checks["legacy_fills_excluded"] == 5
        async with db.session() as session:
            assert await AccountJournalRepository(session).account_event_count(modes=("paper-live",)) == 1
    finally:
        await db.close()

    # A second run finds the account complete and does nothing.
    assert await cli.run(_args(cli, ["--db", url, "--apply", "--reason", "again"])) == 0
    assert "nothing to do" in capsys.readouterr().out


async def test_the_dry_run_reports_a_refusal_without_writing(tmp_path: Path, cli, capsys) -> None:  # type: ignore[no-untyped-def]
    db = _db(tmp_path, "cli2.db")
    await db.create_schema()
    url = f"sqlite+aiosqlite:///{tmp_path / 'cli2.db'}"
    try:
        t0 = datetime.now(UTC) - timedelta(days=2)
        await register_run(db, "run_legacy", started_at=t0)
        await _write_legacy_fills(db, "run_legacy", _legacy_day(t0))  # the run is never stopped
    finally:
        await db.close()
    assert await cli.run(_args(cli, ["--db", url])) == 1
    out = capsys.readouterr().out
    assert "REFUSED" in out and "not stopped" in out
    db = _db(tmp_path, "cli2.db")
    try:
        async with db.session() as session:
            assert await AccountJournalRepository(session).account_event_count(modes=("paper-live",)) == 0
    finally:
        await db.close()


async def test_an_unreadable_database_is_exit_code_2(tmp_path: Path, cli, capsys) -> None:  # type: ignore[no-untyped-def]
    url = f"sqlite+aiosqlite:///{tmp_path / 'missing' / 'nope.db'}"
    # The file is created empty by SQLite; no schema means the read fails.
    assert await cli.run(_args(cli, ["--db", url])) == 2
    assert "could not be" in capsys.readouterr().err


def _args(cli, argv: list[str]):  # type: ignore[no-untyped-def]
    return cli.build_parser().parse_args(argv)
