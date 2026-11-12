#!/usr/bin/env bash
# Árbol candidato de la misión de dirección técnica: cadena 01..22 (arbol_candidato_TI.sh, sin cambios) y luego 23..25, en
# un clon NUEVO. Verifica T23..T25 contra el registro y, en cada paso, ruff y las pruebas que el parche agrega o modifica.
# No escribe en el repositorio protegido (solo lo clona).
# Uso: arbol_candidato_DT.sh <destino>
set -uo pipefail
D="$1"; M=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25
P=$M/parches; R=$M/registro; PY=$M/venv/bin/python; L=$M/logs/DT/arbol_candidato; mkdir -p "$L"
bash $M/casos/arbol_candidato_TI.sh "$D" || exit $?
arbol() { git -C "$D" add -A && git -C "$D" write-tree; git -C "$D" reset -q; }
for n in 23_DT_una_sola_sesion_viva_por_cuenta_entre_procesos 24_DT_un_resto_menor_que_un_lote_no_es_una_posicion \
         25_DT_el_stop_cubre_los_lotes_enteros_que_hay_en_la_cuenta; do
  git -C "$D" apply --check "$P/$n.patch" && git -C "$D" apply "$P/$n.patch" || { echo "NO APLICA $n"; exit 3; }
  t=$(arbol); e=$(cat "$R/T${n:0:2}.txt")
  echo "+${n:0:2}: $t esperado $e $([[ $t == "$e" ]] && echo OK || echo DISTINTO)"
  pruebas=$(grep '^+++ b/tests/' "$P/$n.patch" | cut -c7- | tr '\n' ' ')
  (cd "$D" && PATH=$M/venv/bin:/usr/bin:/bin ruff check packages tests scripts --no-cache > "$L/ruff_${n:0:2}.txt" 2>&1); r=$?
  (cd "$D" && PYTHONPATH=packages/tia/src timeout 1200 $PY -m pytest $pruebas -q -p no:cacheprovider > "$L/pytest_${n:0:2}.txt" 2>&1); p=$?
  echo "   ruff rc=$r · pruebas del parche rc=$p · $(tail -1 "$L/pytest_${n:0:2}.txt")"
done
