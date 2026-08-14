#!/usr/bin/env bash
# Back up the Trader-IA database, whichever one is in use.
#
#   make backup            # or: bash scripts/backup.sh
#
# Three cases, detected in order:
#   1. The production compose stack is running  -> pg_dump inside the postgres container
#   2. TIA_DATABASE_URL points at Postgres      -> pg_dump over the network (needs pg_dump)
#   3. Otherwise                                -> copy the SQLite file(s)
#
# Dumps land in backups/ with a UTC timestamp; retention keeps the newest
# $BACKUP_KEEP (default 14). No credential is ever printed — pg_dump reads
# PGPASSWORD from the environment, never from an argument.
set -euo pipefail

KEEP="${BACKUP_KEEP:-14}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT_DIR="${BACKUP_DIR:-backups}"
mkdir -p "$OUT_DIR"

prune() {
  # $1 = glob prefix
  ls -1t "$OUT_DIR"/$1 2>/dev/null | tail -n +"$((KEEP + 1))" | xargs -r rm -f
}

# ---- case 1: a compose stack (production or local) -----------------------------------
# COMPOSE_FILE pins one explicitly; otherwise whichever stack is actually running wins.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  for compose_file in ${COMPOSE_FILE:-docker-compose.prod.yml docker-compose.local.yml}; do
    [ -f "$compose_file" ] || continue
    if docker compose -f "$compose_file" ps --status running postgres 2>/dev/null | grep -q postgres; then
      out="$OUT_DIR/tia-${STAMP}.sql.gz"
      docker compose -f "$compose_file" exec -T postgres pg_dump -U tia -d tia | gzip > "$out"
      echo "PASS  postgres dump (via $compose_file): $out ($(du -h "$out" | cut -f1))"
      prune "tia-*.sql.gz"
      exit 0
    fi
  done
fi

URL="${TIA_DATABASE_URL:-sqlite+aiosqlite:///./data/runtime/tia.db}"

# ---- case 2: direct Postgres ---------------------------------------------------------
if [[ "$URL" == postgresql* ]]; then
  if ! command -v pg_dump >/dev/null 2>&1; then
    echo "FAIL  TIA_DATABASE_URL is Postgres but pg_dump is not installed" >&2
    exit 1
  fi
  # postgresql+asyncpg://user:pass@host/db -> postgresql://user:pass@host/db
  sync_url="${URL/+asyncpg/}"
  out="$OUT_DIR/tia-${STAMP}.sql.gz"
  pg_dump --dbname="$sync_url" | gzip > "$out"
  echo "PASS  postgres dump: $out ($(du -h "$out" | cut -f1))"
  prune "tia-*.sql.gz"
  exit 0
fi

# ---- case 3: SQLite ------------------------------------------------------------------
# sqlite+aiosqlite:///./data/runtime/tia.db -> ./data/runtime/tia.db
db_path="${URL##*:///}"
if [ ! -f "$db_path" ]; then
  echo "SKIP  no database file at $db_path — nothing to back up yet"
  exit 0
fi
base="$(basename "$db_path" .db)"
out="$OUT_DIR/${base}-${STAMP}.db.gz"
if command -v sqlite3 >/dev/null 2>&1; then
  # .backup takes a consistent snapshot even mid-write; a plain cp can catch a torn page.
  tmp="$(mktemp)"
  sqlite3 "$db_path" ".backup '$tmp'"
  gzip -c "$tmp" > "$out"
  rm -f "$tmp"
else
  gzip -c "$db_path" > "$out"
  echo "WARN  sqlite3 CLI not found; used a plain copy — fine while the app is stopped,"
  echo "      racy while it is writing"
fi
echo "PASS  sqlite backup: $out ($(du -h "$out" | cut -f1))"
prune "${base}-*.db.gz"
