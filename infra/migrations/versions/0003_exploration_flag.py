"""Schema v2 → v3: mark which closed trades were exploration.

An exploration trade is taken *because* the estimator has no evidence for its bucket, so
it carries no claim about its own outcome. Without a way to tell one apart after the
fact, every such trade was read back as a claim the system had missed by the full cost of
the round trip — which dragged the mean calibration error down, tightened guardrails on
the very buckets the session had gone to investigate, and had the Mentor propose halting
because the system paid the price of the lessons it was told to buy.

The column is the fix, and it must be persisted rather than inferred: after a restart the
retrospective is rebuilt from these rows, and a flag that only lived in memory would have
the same distortion return on every redeploy.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # Guarded by inspection: a database created fresh at v3 already has the column from
    # the current metadata, while a genuine v2 database does not.
    existing = {col["name"] for col in sa.inspect(bind).get_columns("edge_outcomes")}
    if "exploratory" not in existing:
        with op.batch_alter_table("edge_outcomes") as batch:
            batch.add_column(
                sa.Column(
                    "exploratory",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
    # Every row written before this migration predates the exploration budget, so False
    # is the accurate value for all of them, not merely a convenient default.
    bind.execute(sa.text("UPDATE schema_info SET version = 3 WHERE id = 1"))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns("edge_outcomes")}
    if "exploratory" in existing:
        with op.batch_alter_table("edge_outcomes") as batch:
            batch.drop_column("exploratory")
    bind.execute(sa.text("UPDATE schema_info SET version = 2 WHERE id = 1"))
