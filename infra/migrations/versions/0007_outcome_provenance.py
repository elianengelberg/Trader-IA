"""Schema v6 → v7: each closed trade says what kind of evidence it is.

Every row of ``edge_outcomes`` is a lesson, but not every lesson comes from the same
world. A training simulation closes trades against a generated scenario through the
paper simulator; the 24/7 session closes them against the venue's own prices, with
simulated fills in paper-live and real ones only over an armed live provider. Until
now a row said only ``source`` (``sim`` / ``paper`` / ``live``), which conflates the
two questions a reader actually asks — *whose prices* and *whose fills* — and left the
strategy scoreboard muting strategies in a real-price session on a scenario
generator's losses.

Three nullable columns, all additive:

* ``market_data``: ``synthetic`` or ``real``.
* ``execution_mode``: ``simulated`` or ``real``.
* ``strategy_version``: the version of the strategy that proposed the entry.

Backfill, by what the existing columns already establish and nothing more:

* ``sim`` and ``paper`` rows were written by the scenario engine: synthetic prices,
  simulated fills.
* ``live`` rows were written by the 24/7 session: real prices. Their fills were
  simulated when the run's mode was ``paper-live`` and real when it was ``live``;
  a live row whose run is not on record keeps ``execution_mode`` null.
* ``strategy_version`` is never reconstructed for historical rows: it stays null.

No row is deleted and no existing column changes meaning. Rows whose provenance stays
null judge nobody under the scoreboard's ``real_only`` policy and count exactly as they
always did under ``legacy``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

COLUMNS = (
    ("market_data", sa.String(16)),
    ("execution_mode", sa.String(16)),
    ("strategy_version", sa.String(64)),
)


def upgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns("edge_outcomes")}
    missing = [(name, kind) for name, kind in COLUMNS if name not in existing]
    if missing:
        with op.batch_alter_table("edge_outcomes") as batch:
            for name, kind in missing:
                batch.add_column(sa.Column(name, kind, nullable=True))

    # Backfill only rows that have no provenance yet, so re-running is harmless and a
    # value the runtime wrote is never overwritten.
    bind.execute(
        sa.text(
            "UPDATE edge_outcomes SET market_data = 'synthetic', execution_mode = 'simulated' "
            "WHERE market_data IS NULL AND source IN ('sim', 'paper')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE edge_outcomes SET market_data = 'real' "
            "WHERE market_data IS NULL AND source = 'live'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE edge_outcomes SET execution_mode = 'simulated' "
            "WHERE execution_mode IS NULL AND source = 'live' "
            "AND run_id IN (SELECT run_id FROM runs WHERE mode = 'paper-live')"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE edge_outcomes SET execution_mode = 'real' "
            "WHERE execution_mode IS NULL AND source = 'live' "
            "AND run_id IN (SELECT run_id FROM runs WHERE mode = 'live')"
        )
    )
    bind.execute(sa.text("UPDATE schema_info SET version = 7 WHERE id = 1"))


def downgrade() -> None:
    bind = op.get_bind()
    existing = {col["name"] for col in sa.inspect(bind).get_columns("edge_outcomes")}
    present = [name for name, _ in COLUMNS if name in existing]
    if present:
        with op.batch_alter_table("edge_outcomes") as batch:
            for name in present:
                batch.drop_column(name)
    bind.execute(sa.text("UPDATE schema_info SET version = 6 WHERE id = 1"))
