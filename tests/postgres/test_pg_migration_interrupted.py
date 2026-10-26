"""Phase M — a migration interrupted halfway leaves the schema it started from, on PostgreSQL.

``alembic upgrade head`` runs on every production boot. Here the process is killed (SIGKILL: no
cleanup, no rollback of its own) *after* 0008 altered ``incidents.kind`` and *before* it could
stamp the schema version: another session holds ``schema_info`` locked, so 0008's ``UPDATE`` waits
and the kill lands exactly there. PostgreSQL's transactional DDL must undo the ALTER: the database
is what 0007 left, and the next boot's upgrade completes it. (SQLite rebuilds tables in batch mode
and has no such guarantee for DDL; production runs PostgreSQL.)
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time

from sqlalchemy import text

from tests.postgres.support import REPO_ROOT, PgDatabases, alembic


def _state(pg: PgDatabases) -> tuple[int, int, str]:
    engine = pg.engine()
    try:
        with engine.connect() as conn:
            width = conn.execute(text("SELECT character_maximum_length FROM information_schema.columns "
                                      "WHERE table_name = 'incidents' AND column_name = 'kind'")).scalar_one()
            version = conn.execute(text("SELECT version FROM schema_info")).scalar_one()
            head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()
    return width, version, head


def test_a_migration_killed_after_its_alter_leaves_the_previous_schema_and_resumes(pg: PgDatabases) -> None:
    assert alembic(pg.url(), "upgrade", "0007").returncode == 0
    setup = pg.engine()
    with setup.begin() as conn:  # the width 0007 left in a real v7 database
        conn.execute(text("ALTER TABLE incidents ALTER COLUMN kind TYPE VARCHAR(32)"))
        conn.execute(text("INSERT INTO incidents (incident_id, at, kind, actor, reason, run_id, detail) "
                          "VALUES ('inc_kept', now(), 'safe_mode', 'system', '', '', '{}')"))
    setup.dispose()
    assert _state(pg) == (32, 7, "0007")

    holder = pg.engine()
    lock = holder.connect()
    trans = lock.begin()
    lock.execute(text("LOCK TABLE schema_info IN ACCESS EXCLUSIVE MODE"))
    env = dict(os.environ, TIA_DATABASE_URL=pg.url())
    proc = subprocess.Popen([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=REPO_ROOT, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        watcher = pg.engine()
        waited = False
        try:
            for _ in range(200):  # until 0008 has altered the column and waits on schema_info
                with watcher.connect() as conn:
                    waiting = conn.execute(text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                        "AND wait_event_type = 'Lock' AND query ILIKE 'UPDATE schema_info%'")).scalar_one()
                if waiting:
                    waited = True
                    break
                time.sleep(0.05)
        finally:
            watcher.dispose()
        assert waited, "the migration never reached the schema stamp"
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=30)
        assert proc.returncode == -signal.SIGKILL
    finally:
        trans.rollback()
        lock.close()
        holder.dispose()
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
    for _ in range(100):  # the server notices the dead client and rolls its transaction back
        with contextlib.suppress(Exception):  # the backend may still hold the lock for a moment
            if _state(pg) == (32, 7, "0007"):
                break
        time.sleep(0.05)
    assert _state(pg) == (32, 7, "0007"), "the half-done migration was undone"
    resumed = alembic(pg.url(), "upgrade", "head")
    assert resumed.returncode == 0, resumed.stderr
    assert _state(pg) == (64, 8, "0008")
    engine = pg.engine()
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT kind FROM incidents")).scalars().all() == ["safe_mode"]
    finally:
        engine.dispose()
