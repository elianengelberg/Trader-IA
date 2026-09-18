"""Schema v5 → v6: the market maker's own tables.

The market maker keeps its journal, its simulated fills and its paper ledger in tables
of its own — never in ``fills``, ``edge_outcomes`` or the capital ledger — so the
session's track record, the 27 activation checks and the real-money gate see nothing of
it by construction. Every row is written once; a fill's markouts are filled in later on
the same row, referring to it, never rewriting the decision that produced it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    if "mm_journal" not in existing:
        op.create_table(
            "mm_journal",
            sa.Column("row_id", sa.String(64), primary_key=True),
            sa.Column("run_id", sa.String(64), nullable=False, index=True),
            sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("t_ms", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("kind", sa.String(24), nullable=False, server_default=""),
            sa.Column("payload", sa.JSON(), nullable=False),
        )
        op.create_index("ix_mm_journal_run_t", "mm_journal", ["run_id", "t_ms"])
    if "mm_fills" not in existing:
        op.create_table(
            "mm_fills",
            sa.Column("fill_id", sa.String(64), primary_key=True),
            sa.Column("run_id", sa.String(64), nullable=False, index=True),
            sa.Column("order_id", sa.String(64), nullable=False, server_default=""),
            sa.Column("t_ms", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("side", sa.String(8), nullable=False, server_default=""),
            sa.Column("price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("fee_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("realised_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("mid_at_fill", sa.Float(), nullable=True),
            sa.Column("resolution", sa.String(16), nullable=False, server_default="confirmed"),
            sa.Column("venue_trade_ids", sa.JSON(), nullable=False),
            sa.Column("regimes", sa.JSON(), nullable=False),
            sa.Column("markout_bps", sa.JSON(), nullable=True),
        )
        op.create_index("ix_mm_fills_run_t", "mm_fills", ["run_id", "t_ms"])
    if "mm_ledger" not in existing:
        op.create_table(
            "mm_ledger",
            sa.Column("run_id", sa.String(64), primary_key=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("config_id", sa.String(32), nullable=False, server_default=""),
            sa.Column("profile_id", sa.String(32), nullable=False, server_default=""),
            sa.Column("latency_scenario", sa.String(16), nullable=False, server_default=""),
            sa.Column("state", sa.JSON(), nullable=False),
        )
    bind.execute(sa.text("UPDATE schema_info SET version = 6 WHERE id = 1"))


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for table in ("mm_ledger", "mm_fills", "mm_journal"):
        if table in existing:
            op.drop_table(table)
    bind.execute(sa.text("UPDATE schema_info SET version = 5 WHERE id = 1"))
