"""Single application version (P2: proposal 0001/0002 of the new review, integrated 2026-10-22).

Every application-level version label must come from ``tia.__version__``: pyproject, the FastAPI app,
the health payload, ``Settings.version`` and the ``schema_info.application_version`` row written when a
schema is created. Strategy versions (``Strategy.version``), the schema number, feature and prompt
versions are different labels and stay out, named one by one in ``OTHER_LABELS``.

The static rule refuses a hand-written version literal even when it happens to equal the package
version: a label that is typed twice drifts, and nothing would notice.
"""

from __future__ import annotations

import ast
import asyncio
import tomllib
from pathlib import Path

from sqlalchemy import select

import tia

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "packages" / "tia" / "src" / "tia"
NAMES = {"version", "application_version", "app_version"}
#: Version labels that are NOT the application's (file relative to the package, name).
OTHER_LABELS = {("strategy/base.py", "version"), ("strategy/library.py", "version")}


def _hand_written_versions() -> list[str]:
    found = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            pairs: list[tuple[str, ast.expr | None]] = []
            if isinstance(node, ast.keyword) and node.arg in NAMES:
                pairs.append((node.arg, node.value))
            elif isinstance(node, ast.Dict):
                pairs += [(k.value, v) for k, v in zip(node.keys, node.values, strict=True)
                          if isinstance(k, ast.Constant) and k.value in NAMES]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in NAMES:
                pairs.append((node.target.id, node.value))
            elif isinstance(node, ast.Assign):
                pairs += [(t.id, node.value) for t in node.targets if isinstance(t, ast.Name) and t.id in NAMES]
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                a = node.args
                positional = a.posonlyargs + a.args
                defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
                pairs += [(arg.arg, d) for arg, d in zip(positional + a.kwonlyargs, defaults + list(a.kw_defaults),
                                                         strict=True) if arg.arg in NAMES]
            for name, value in pairs:
                if (isinstance(value, ast.Constant) and isinstance(value.value, str)
                        and (rel, name) not in OTHER_LABELS):
                    found.append(f"{rel}:{value.lineno} {name}={value.value!r}")
    return found


def test_no_application_version_is_hand_written() -> None:
    assert _hand_written_versions() == []


def test_pyproject_takes_the_package_version() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    if "version" in project["project"]:
        assert project["project"]["version"] == tia.__version__
    else:
        assert "version" in project["project"].get("dynamic", [])
        source = ROOT / project["tool"]["hatch"]["version"]["path"]
        assert source.resolve() == (SRC / "__init__.py").resolve()


def test_settings_and_app_report_the_package_version() -> None:
    from tia.api.app import create_app
    from tia.core.config import Environment, settings_for_env

    settings = settings_for_env(Environment.TESTING)
    assert settings.version == tia.__version__
    assert create_app(settings).version == tia.__version__


async def test_the_schema_row_records_the_package_version(tmp_path: Path) -> None:
    from tia.persistence.database import Database
    from tia.persistence.models import SchemaInfo

    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'version.db'}")
    try:
        await db.ensure_schema()  # no argument, the way AppState.startup calls it
        async with db.session() as session:
            row = (await session.execute(select(SchemaInfo))).scalars().one()
        assert row.application_version == tia.__version__
    finally:
        await db.close()


async def test_a_database_another_build_created_reports_the_running_version(tmp_path: Path) -> None:
    """A schema created by an earlier release, or by Alembic (``'alembic-0001'``), records the
    application that runs on it once ``ensure_schema`` — what every boot calls — has run.
    Production creates the schema with Alembic and boots with ``ensure_schema``."""
    import os
    import subprocess
    import sys

    from tia.persistence.database import Database
    from tia.persistence.models import SchemaInfo

    async def stored(db: Database) -> str:
        async with db.session() as session:
            return (await session.execute(select(SchemaInfo))).scalars().one().application_version

    older = Database(f"sqlite+aiosqlite:///{tmp_path / 'older.db'}")
    try:
        await older.create_schema(application_version="0.1.0")  # what every build up to c6339e3 wrote
        assert await stored(older) == "0.1.0"
        await older.ensure_schema()
        assert await stored(older) == tia.__version__
    finally:
        await older.close()

    migrated = tmp_path / "alembic.db"
    result = await asyncio.to_thread(  # the alembic CLI blocks: off the event loop
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, text=True, cwd=ROOT,
        env=dict(os.environ, TIA_DATABASE_URL=f"sqlite:///{migrated}"), timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    db = Database(f"sqlite+aiosqlite:///{migrated}")
    try:
        assert await stored(db) == "alembic-0001", "the migration's own stamp, kept as history"
        await db.ensure_schema()
        assert await stored(db) == tia.__version__
    finally:
        await db.close()
