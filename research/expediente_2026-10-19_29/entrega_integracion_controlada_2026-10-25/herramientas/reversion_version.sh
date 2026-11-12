#!/usr/bin/env bash
# E15: el candidato escribe (esquema v8 por alembic), el código anterior (A+B+03, esquema v7) intenta leer;
# la reversión del esquema se niega mientras haya incidentes largos; se exportan, se revierte y el código anterior opera.
# Uso: reversion_version.sh <dir_salida>
set -u
O="$1"; mkdir -p "$O"; PY=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/venv/bin/python; C=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/dev; B=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/ABC; DB="$O/e15.db"; rm -f "$DB"
al() { ( cd "$1" && TIA_DATABASE_URL="sqlite:///$DB" PATH=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/venv/bin:/usr/bin:/bin $PY -m alembic "${@:2}" ) > "$O/alembic_$3_$(date +%s%N).txt" 2>&1; local rc=$?; echo "alembic ${*:2} (árbol ${1##*/}) rc=$rc"; }
al $C upgrade head
$PY -I /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/casos/reversion_version.py $C escribir "$DB" "$O/1_candidato_escribe.json" | cut -c1-300
$PY -I /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/casos/reversion_version.py $B leer "$DB" "$O/2_anterior_lee_sin_revertir.json" | cut -c1-400
al $C downgrade 0007
grep -h "would cut" "$O"/alembic_* | tail -1 | cut -c1-200
$PY -I /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/casos/reversion_version.py $C exportar "$DB" "$O/3_exportar.json" | cut -c1-200
al $C downgrade 0007
$PY -I /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/casos/reversion_version.py $B leer "$DB" "$O/4_anterior_lee_revertido.json" | cut -c1-400
al $C upgrade head
$PY -I /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/casos/reversion_version.py $C leer "$DB" "$O/5_candidato_lee_tras_reaplicar.json" | cut -c1-400
rm -f "$DB"
