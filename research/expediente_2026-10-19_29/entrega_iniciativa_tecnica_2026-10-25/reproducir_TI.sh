#!/usr/bin/env bash
# Reconstruye el árbol candidato T22 desde cero, solo con lo que trae este paquete:
#   clona el repositorio de origen (solo lectura), fija el commit 72ffae5, aplica parches/base_01_15 (sin cambios
#   respecto de la entrega anterior) y parches/ciclo_TI, y compara CADA árbol intermedio con registro/.
#   Con un intérprete de Python (3er argumento), corre además ruff y las pruebas que agrega o modifica cada parche
#   del ciclo (16..22).
# No escribe en el repositorio de origen: solo lo clona. Compara el sha256 de su .git/index antes y después.
# No conecta con ningún exchange ni usa credenciales. No hace commit, push ni PR.
# Uso: bash reproducir_TI.sh <repositorio_origen> <destino_nuevo> [python_con_dependencias]
set -uo pipefail
ORIGEN="${1:?repositorio de origen}"; D="${2:?destino (no debe existir)}"; PY="${3:-}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; R="$AQUI/registro"
BASE=72ffae5d2698440c8f1afaff12e07bd8adde66fb
[[ -e "$D" ]] && { echo "$D ya existe: elegí un destino nuevo"; exit 1; }
indice() { [[ -f "$ORIGEN/.git/index" ]] && sha256sum "$ORIGEN/.git/index" | cut -d' ' -f1 || echo "(sin .git/index)"; }
ANTES=$(indice)
git clone -q --no-local "$ORIGEN" "$D" || exit 2
git -C "$D" checkout -q --detach "$BASE" || exit 2
git -C "$D" remote set-url --push origin no-push://reproduccion-TI
arbol() { git -C "$D" add -A && git -C "$D" write-tree; git -C "$D" reset -q; }
aplicar() { git -C "$D" apply --check "$1" && git -C "$D" apply "$1" || { echo "NO APLICA $(basename "$1")"; exit 3; }; }
fallas=0
verificar() {  # $1 = nombre, $2 = árbol esperado
  local t; t=$(arbol)
  if [[ "$t" == "$2" ]]; then echo "OK        $1 $t"; else echo "DISTINTO  $1 $t (esperado $2)"; fallas=$((fallas + 1)); fi
}
# Cadena base 01..15: el árbol después del 5.º parche es A+B+03+04; los siguientes, T08 T07 T09 T10 T11 T12 T13 T15.
ESPERADOS=(- - - - 665d0643bd986a5e484192ef50957b64992305cc T08 T07 T09 T10 T11 T12 T13 T15)
i=0
for p in "$AQUI"/parches/base_01_15/*.patch; do
  aplicar "$p"; e=${ESPERADOS[$i]}; i=$((i + 1))
  [[ "$e" == - ]] && continue
  [[ "$e" == T* ]] && e=$(cat "$R/$e.txt")
  verificar "$(basename "$p")" "$e"
done
for p in "$AQUI"/parches/ciclo_TI/*.patch; do
  n=$(basename "$p"); aplicar "$p"; verificar "$n" "$(cat "$R/T${n:0:2}.txt")"
  if [[ -n "$PY" ]]; then
    pruebas=$(grep '^+++ b/tests/' "$p" | cut -c7- | tr '\n' ' ')
    (cd "$D" && "$(dirname "$PY")/ruff" check packages tests scripts --no-cache > /dev/null 2>&1); r=$?
    q=0; [[ -n "$pruebas" ]] && { (cd "$D" && PYTHONPATH=packages/tia/src timeout 1200 "$PY" -m pytest $pruebas -q -p no:cacheprovider > /dev/null 2>&1); q=$?; }
    echo "          ruff rc=$r · pruebas del parche rc=$q"
    [[ $r -ne 0 || $q -ne 0 ]] && fallas=$((fallas + 1))
  fi
done
DESPUES=$(indice)
echo "árbol final: $(arbol) · esperado $(cat "$R/T22.txt")"
echo "índice del origen: antes $ANTES · después $DESPUES · $([[ "$ANTES" == "$DESPUES" ]] && echo SIN CAMBIOS || echo CAMBIÓ)"
[[ "$ANTES" != "$DESPUES" ]] && fallas=$((fallas + 1))
echo "RESULTADO: $([[ $fallas -eq 0 ]] && echo REPRODUCIDO || echo "NO REPRODUCIDO ($fallas fallas)")"
exit $(( fallas > 0 ? 4 : 0 ))
