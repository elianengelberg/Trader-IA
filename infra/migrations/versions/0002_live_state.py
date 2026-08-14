"""Schema v1 → v2: the tables live trading survives on.

Adds edge_outcomes (persisted evidence), activation_attempts (the arming audit trail),
reconciliations, capital_events, incidents and latency_samples, and moves the
application-level schema version to 2 so ``ensure_schema()`` and this migration agree
about what version 2 means.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

V2_TABLES = (
    "edge_outcomes",
    "activation_attempts",
    "reconciliations",
    "capital_events",
    "incidents",
    "latency_samples",
)


def upgrade() -> None:
    from tia.persistence.models import Base

    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in V2_TABLES]
    Base.metadata.create_all(bind, tables=tables, checkfirst=True)

    # v2 also adds the trade-or-not arithmetic to the decision journal. Guarded by an
    # inspection because a database created fresh at v2 already has the columns — its
    # `decisions` table came from the current metadata — while a genuine v1 database
    # does not.
    existing = {col["name"] for col in sa.inspect(bind).get_columns("decisions")}
    with op.batch_alter_table("decisions") as batch:
        if "risk_budget" not in existing:
            batch.add_column(sa.Column("risk_budget", sa.JSON(), nullable=True))
        if "expected_value" not in existing:
            batch.add_column(sa.Column("expected_value", sa.JSON(), nullable=True))

    bind.execute(sa.text("UPDATE schema_info SET version = 2 WHERE id = 1"))


def downgrade() -> None:
    from tia.persistence.models import Base

    bind = op.get_bind()
    tables = [Base.metadata.tables[name] for name in reversed(V2_TABLES)]
    Base.metadata.drop_all(bind, tables=tables, checkfirst=True)
    bind.execute(sa.text("UPDATE schema_info SET version = 1 WHERE id = 1"))
