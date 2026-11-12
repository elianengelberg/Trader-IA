#!/usr/bin/env bash
# Matriz R19: 7 condiciones × (base, cand, cand, base) — orden alternado. Carga externa para cpu y suite_concurrente.
# Uso: r19_matriz.sh <dir_salida> <n_escrituras>
set -u
O="$1"; N="$2"; PY=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/venv/bin/python; mkdir -p "$O"
BASE=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/AB; CAND=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/dev
carga_inicio() {
  case "$1" in
    cpu) for i in 1 2 3; do $PY -c "import time; t=time.time()
while time.time()-t<600: pass" & echo $! >> "$O/.carga"; done ;;
    suite_concurrente) mkdir -p "$O/tmp_suite"; ( cd /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/A3 && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src TMPDIR="$O/tmp_suite" timeout 600 $PY -B -m pytest tests/unit -q -p no:cacheprovider > "$O/suite_concurrente.log" 2>&1 ) & echo $! >> "$O/.carga" ;;
  esac
}
carga_fin() { [[ -f "$O/.carga" ]] && { while read -r p; do pkill -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; done < "$O/.carga"; rm -f "$O/.carga"; }; rm -rf -- "${O:?}/tmp_suite"; }
for c in sin_carga cpu suite_concurrente lentas errores interrupcion reinicio; do
  carga_inicio "$c"; sleep 2
  k=0
  for par in "base:$BASE" "cand:$CAND" "cand:$CAND" "base:$BASE"; do
    k=$((k+1)); nom=${par%%:*}; arbol=${par#*:}
    echo "== $c $nom ($k) $(date -u +%FT%TZ) carga $(cut -d' ' -f1 /proc/loadavg)"
    timeout 300 $PY -I /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/casos/r19_matriz.py "$arbol" "$c" "$O/${c}_${nom}_${k}.json" "$((1000+k))" "$N" 2>&1 | grep -E '^\{' || echo "FALLÓ rc=${PIPESTATUS[0]}"
  done
  carga_fin
done
echo "fin $(date -u +%FT%TZ)"
