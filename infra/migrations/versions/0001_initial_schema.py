"""Initial schema — every table of schema version 1.

Created from the declarative metadata rather than hand-written DDL, with ``checkfirst``
on: a database that ``ensure_schema()`` already created adopts this revision cleanly
instead of failing on the first CREATE TABLE. That adoption path matters because every
deployment that predates Alembic is exactly such a database.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

#: The tables that existed at schema version 1, in dependency order.
V1_TABLES = (
    "schema_info",
    "runs",
    "events",
    "decisions",
    "orders",
    "fills",
    "positions",
    "equity_points",
    "assessments",
    "logs",
    "backtests",
    "news",
)


def upgrade() -> None:
    from tia.persistence.models import Base

    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in V1_TABLES]
    Base.metadata.create_all(bind, tables=tables, checkfirst=True)

    # Stamp the application-level version row if this is a fresh database. An existing
    # row is left alone — 0002 owns moving it forward.
    has_row = bind.execute(sa.text("SELECT COUNT(*) FROM schema_info")).scalar()
    if not has_row:
        bind.execute(
            sa.text(
                "INSERT INTO schema_info (id, version, applied_at, application_version) "
                "VALUES (1, 1, CURRENT_TIMESTAMP, 'alembic-0001')"
            )
        )


def downgrade() -> None:
    from tia.persistence.models import Base

    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in reversed(V1_TABLES)]
    Base.metadata.drop_all(bind, tables=tables, checkfirst=True)
