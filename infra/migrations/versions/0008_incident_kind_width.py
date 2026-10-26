"""Schema v7 → v8: ``incidents.kind`` holds every kind the code writes (R24-H1).

The column was ``VARCHAR(32)``. The live runtime writes ``entries_blocked:<cause>`` incidents of
up to 37 characters (``entries_blocked:protection_unverified``). SQLite does not enforce VARCHAR
lengths, so every suite stored them; PostgreSQL, which production runs, refused them with
SQLSTATE 22001 and the dispatcher absorbed the error: the incidents existed only in memory.

Upgrade: widen to ``VARCHAR(64)`` (``INCIDENT_KIND_MAX_LENGTH``). On PostgreSQL, growing a
``varchar`` limit is a catalog change: no table rewrite, no index rebuild, existing rows untouched.
SQLite gets the same declared type through batch mode, so the two schemas do not drift.

Downgrade: narrowing back would cut or refuse rows. It is done only when no row is longer than
32 characters; otherwise the downgrade stops with the count and changes nothing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

OLD_WIDTH = 32
NEW_WIDTH = 64  # tia.persistence.models.INCIDENT_KIND_MAX_LENGTH, fixed here as migrations are


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("incidents") as batch:
        batch.alter_column(
            "kind", existing_type=sa.String(OLD_WIDTH), type_=sa.String(NEW_WIDTH), existing_nullable=False,
        )
    bind.execute(sa.text("UPDATE schema_info SET version = 8 WHERE id = 1"))


def downgrade() -> None:
    bind = op.get_bind()
    too_long = bind.execute(
        sa.text("SELECT COUNT(*) FROM incidents WHERE LENGTH(kind) > :width").bindparams(width=OLD_WIDTH)
    ).scalar_one()
    if too_long:
        raise RuntimeError(
            f"cannot narrow incidents.kind back to {OLD_WIDTH}: {too_long} row(s) have a kind longer "
            f"than {OLD_WIDTH} characters and would be cut or refused; nothing was changed"
        )
    with op.batch_alter_table("incidents") as batch:
        batch.alter_column(
            "kind", existing_type=sa.String(NEW_WIDTH), type_=sa.String(OLD_WIDTH), existing_nullable=False,
        )
    bind.execute(sa.text("UPDATE schema_info SET version = 7 WHERE id = 1"))
