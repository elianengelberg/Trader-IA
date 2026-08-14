"""Alembic environment.

The URL comes from ``TIA_DATABASE_URL`` (falling back to the project default), with the
async driver suffix stripped — migrations run synchronously on purpose. A migration is an
operator action with a person watching; async buys nothing there and costs a second code
path through the drivers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "tia" / "src"))

from tia.persistence.models import Base  # noqa: E402

target_metadata = Base.metadata

DEFAULT_URL = "sqlite:///./data/runtime/tia.db"


def _database_url() -> str:
    url = os.environ.get("TIA_DATABASE_URL", DEFAULT_URL)
    # The application uses async drivers; migrations use their sync twins.
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    if url.startswith("sqlite"):
        Path(url.split("///", 1)[-1]).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite cannot ALTER most things in place; batch mode rebuilds tables.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
