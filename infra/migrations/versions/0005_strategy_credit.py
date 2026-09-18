"""Schema v4 → v5: each closed trade names the strategy that proposed it.

The edge estimator buckets outcomes by regime, direction and confidence — never by
strategy, because a bucket that also split by strategy would take three times as long to
fill. That leaves two strategies firing in the same regime sharing one record, so a bad
one can trade on a good one's evidence. ``strategy_id`` is how the scoreboard closes that
gap: each strategy answers for its own trades, and one whose record is negative with enough
trades to mean it is muted. Rows written before this column are null and judge nobody.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns("edge_outcomes")}
    if "strategy_id" not in existing:
        with op.batch_alter_table("edge_outcomes") as batch:
            batch.add_column(sa.Column("strategy_id", sa.String(64), nullable=True))
    bind.execute(sa.text("UPDATE schema_info SET version = 5 WHERE id = 1"))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns("edge_outcomes")}
    if "strategy_id" in existing:
        with op.batch_alter_table("edge_outcomes") as batch:
            batch.drop_column("strategy_id")
    bind.execute(sa.text("UPDATE schema_info SET version = 4 WHERE id = 1"))
