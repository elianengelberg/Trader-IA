#!/usr/bin/env bash
# Pasos del workflow ci.yml (job python, o job postgresql con "pg"), en un clon aislado, con el venv fijado de la misión.
# Uso: ci_local.sh <clon> <nombre> [pg]
set -u
C="$1"; N="$2"; MODO="${3:-}"; PY=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/venv/bin/python; L=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/logs/J_$N; mkdir -p "$L"
export PATH="/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/venv/bin:/usr/bin:/bin" PYTHONPATH=packages/tia/src TMPDIR="$L/tmp"; mkdir -p "$TMPDIR"
export CI_RUN_NONCE="local-$N-$(head -c8 /dev/urandom | od -An -tx1 | tr -d ' \n')"
if [[ "$MODO" == pg ]]; then export CI_GATE_REQUIRE_POSTGRESQL=1 TIA_TEST_POSTGRESQL_URL="postgresql+asyncpg://postgres@/postgres?host=/tmp/tia_ic_4899e77d"; fi
cd "$C" || exit 2
{ echo "== ci_local $N ($MODO) · árbol $(git add -A && git write-tree; git reset -q) · nonce $CI_RUN_NONCE · inicio $(date -u +%FT%TZ) · carga $(cut -d' ' -f1-3 /proc/loadavg)"
  ruff check packages tests scripts --no-cache > "$L/ruff.txt" 2>&1; echo "ruff rc=$? · $(tail -1 "$L/ruff.txt")"
  T0=$(date +%s); timeout 3000 $PY -m pytest tests -q -p scripts.ci_provenance --junitxml=ci-evidence/junit.xml > "$L/pytest.txt" 2>&1; echo "pytest rc=$? · $(( $(date +%s) - T0 )) s · $(tail -1 "$L/pytest.txt")"
  $PY scripts/ci_gate.py ci-evidence ci-evidence/junit.xml > "$L/gate.txt" 2>&1; echo "gate rc=$?"; cat "$L/gate.txt"
  cp ci-evidence/junit.xml ci-evidence/session.json ci-evidence/provenance.json "$L/" 2>/dev/null
  TIA_DATABASE_URL=sqlite:///./data/runtime/ci.db $PY -m alembic upgrade head > "$L/alembic_sqlite.txt" 2>&1; echo "alembic sqlite upgrade head rc=$?"
  if [[ "$MODO" == pg ]]; then
    $PY -c "import psycopg2; c = psycopg2.connect(host='/tmp/tia_ic_4899e77d', user='postgres', dbname='postgres'); c.autocommit = True; c.cursor().execute('DROP DATABASE IF EXISTS ci_migrations'); c.cursor().execute('CREATE DATABASE ci_migrations')"
    for paso in "upgrade head" "downgrade base" "upgrade head"; do TIA_DATABASE_URL="postgresql://postgres@/ci_migrations?host=/tmp/tia_ic_4899e77d" $PY -m alembic $paso >> "$L/alembic_pg.txt" 2>&1; echo "alembic pg $paso rc=$?"; done
    $PY -c "import psycopg2; c = psycopg2.connect(host='/tmp/tia_ic_4899e77d', user='postgres', dbname='postgres'); c.autocommit = True; c.cursor().execute('DROP DATABASE IF EXISTS ci_migrations WITH (FORCE)')"
  fi
  echo "fin $(date -u +%FT%TZ) · estado del árbol: $(git status --porcelain | wc -l) entradas ($(git status --porcelain | cut -c4- | tr '\n' ' ' | cut -c1-200))"; } > "$L/resumen.txt" 2>&1
rm -rf -- "${TMPDIR:?}"
