"""Schema v3 → v4: exit reasons, an ingestion clock, and a source index.

Three columns' worth of questions the record could not answer:

* ``exit_reason`` — how each round trip ended. A win rate alone cannot say whether the
  stops are too tight or the targets too far; this is the first thing to ask of it.
* ``ingested_at`` — the wall-clock moment a row was written, set by the database. The
  session folds new evidence in by itself every minute, and until now "new" meant
  re-reading every row and diffing ids — fine at 3k rows, a full table scan per minute
  at 123k. ``closed_at`` cannot serve: it is *bar* time, and a simulation's bars can
  predate rows written yesterday. A server-side timestamp answers "since last look" in
  one indexed range read, at any size.
* an index on ``source`` — every dollar and journal query groups or filters by it.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns("edge_outcomes")}
    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("edge_outcomes")}
    with op.batch_alter_table("edge_outcomes") as batch:
        if "exit_reason" not in existing:
            batch.add_column(sa.Column("exit_reason", sa.String(64), nullable=True))
        if "ingested_at" not in existing:
            # Existing rows are stamped "now": they are all older than any future look,
            # which is the property the refresher needs from them.
            batch.add_column(
                sa.Column(
                    "ingested_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
    if "ix_edge_outcomes_ingested_at" not in indexes:
        op.create_index("ix_edge_outcomes_ingested_at", "edge_outcomes", ["ingested_at"])
    if "ix_edge_outcomes_source" not in indexes:
        op.create_index("ix_edge_outcomes_source", "edge_outcomes", ["source"])
    bind.execute(sa.text("UPDATE schema_info SET version = 4 WHERE id = 1"))


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {ix["name"] for ix in sa.inspect(bind).get_indexes("edge_outcomes")}
    for name in ("ix_edge_outcomes_source", "ix_edge_outcomes_ingested_at"):
        if name in indexes:
            op.drop_index(name, table_name="edge_outcomes")
    existing = {col["name"] for col in sa.inspect(bind).get_columns("edge_outcomes")}
    with op.batch_alter_table("edge_outcomes") as batch:
        for name in ("ingested_at", "exit_reason"):
            if name in existing:
                batch.drop_column(name)
    bind.execute(sa.text("UPDATE schema_info SET version = 3 WHERE id = 1"))
