#!/usr/bin/env bash
# Construye el árbol candidato en un clon NUEVO aplicando la cadena completa de parches y verifica cada árbol intermedio.
# Uso: arbol_candidato.sh <destino>
set -uo pipefail
D="$1"; X=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/revision_adversaria_2026-10-25/extraccion/cierre_integral_2026-10-22/patches; P=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/parches; R=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/registro
[[ -e "$D" ]] && { echo "$D ya existe"; exit 1; }
git clone -q --no-local /home/user/Trader-IA "$D" && git -C "$D" checkout -q --detach 72ffae5d2698440c8f1afaff12e07bd8adde66fb && git -C "$D" remote set-url --push origin no-push://integracion-controlada
arbol() { git -C "$D" add -A && git -C "$D" write-tree; git -C "$D" reset -q; }
paso() { git -C "$D" apply --check "$1" && git -C "$D" apply "$1" || { echo "NO APLICA ${1##*/}"; exit 3; }; }
for p in $X/v3r3/01_*.patch $X/v3r3/02v3_*.patch $X/05v2_guarda_version_motor.patch $X/v3r3/03_*.patch $X/v3r3/04_*.patch; do paso "$p"; done
t=$(arbol); echo "A+B+03+04: $t $([[ $t == 665d0643bd986a5e484192ef50957b64992305cc ]] && echo OK || echo DISTINTO)"
for par in "08_R25_R18_proteccion_de_posiciones:T08" "07:T07" "09_R15_guardado_atomico_backtest:T09" "10_R24H1_largo_de_incidentes:T10" "11_R19_escrituras_confirmadas:T11" "12_gate_v4_procedencia_y_ci_postgresql:T12" "13_R18_reproteccion_al_reiniciar:T13" "15_R25b_transporte_ambiguo_es_estado_desconocido:T15"; do
  n=${par%%:*}; e=$(cat $R/${par#*:}.txt)
  if [[ $n == 07 ]]; then paso $X/07_opcional_pruebas_almacen_postgresql.patch; else paso $P/$n.patch; fi
  t=$(arbol); echo "+$n: $t esperado $e $([[ $t == $e ]] && echo OK || echo DISTINTO)"
done
