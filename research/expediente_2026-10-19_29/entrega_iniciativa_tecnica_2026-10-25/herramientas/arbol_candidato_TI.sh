#!/usr/bin/env bash
# Árbol candidato del ciclo de iniciativa técnica: cadena 01..15 (arbol_candidato.sh, sin cambios) y luego 16..22, en un
# clon NUEVO. Verifica cada árbol intermedio contra el registro y, en cada paso 16..22, ruff y las pruebas que el parche
# agrega o modifica. No escribe en el repositorio protegido (solo lo clona).
# Uso: arbol_candidato_TI.sh <destino>
set -uo pipefail
D="$1"; M=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25
P=$M/parches; R=$M/registro; PY=$M/venv/bin/python; L=$M/logs/TI/arbol_candidato; mkdir -p "$L"
bash $M/casos/arbol_candidato.sh "$D" || exit $?
arbol() { git -C "$D" add -A && git -C "$D" write-tree; git -C "$D" reset -q; }
for n in 16_TI_controles_de_emergencia_conservan_la_proteccion 17_TI_compuerta_de_evidencia_real \
         18_TI_metricas_de_la_sesion_24x7 19_TI_contrato_de_persistencia_y_alertas \
         20_TI_pruebas_que_cierran_huecos_de_deteccion 21_TI_watchdog_al_reanudar_tras_una_pausa \
         22_TI_documentacion_del_kill_switch; do
  git -C "$D" apply --check "$P/$n.patch" && git -C "$D" apply "$P/$n.patch" || { echo "NO APLICA $n"; exit 3; }
  t=$(arbol); e=$(cat "$R/T${n:0:2}.txt")
  echo "+${n:0:2}: $t esperado $e $([[ $t == "$e" ]] && echo OK || echo DISTINTO)"
  pruebas=$(grep '^+++ b/tests/' "$P/$n.patch" | cut -c7- | tr '\n' ' ')
  (cd "$D" && PATH=$M/venv/bin:/usr/bin:/bin ruff check packages tests scripts --no-cache > "$L/ruff_${n:0:2}.txt" 2>&1); r=$?
  if [[ -z "$pruebas" ]]; then echo "(el parche no toca pruebas)" > "$L/pytest_${n:0:2}.txt"; p=0
  else (cd "$D" && PYTHONPATH=packages/tia/src timeout 1200 $PY -m pytest $pruebas -q -p no:cacheprovider > "$L/pytest_${n:0:2}.txt" 2>&1); p=$?; fi
  echo "   ruff rc=$r · pruebas del parche rc=$p · $(tail -1 "$L/pytest_${n:0:2}.txt")"
done
