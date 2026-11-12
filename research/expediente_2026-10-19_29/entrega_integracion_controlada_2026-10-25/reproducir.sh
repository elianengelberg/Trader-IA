#!/usr/bin/env bash
# Reconstruye el árbol candidato de la integración controlada (2026-10-25) en un clon NUEVO y lo verifica.
#
#   bash reproducir.sh <repositorio_origen> [--destino DIR] [--pruebas PYTHON311]
#
# Qué hace:
#   1. verifica MANIFEST.sha256 de este paquete;
#   2. clona <repositorio_origen> con --no-local en un directorio NUEVO fuera de él (solo lectura sobre el origen),
#      fija el commit base 72ffae5 y deja el push apuntando a «no-push://» (un push falla);
#   3. aplica la cadena de parches/CADENA.txt en orden, verificando el sha256 de cada parche y el árbol git
#      esperado después de cada paso (sin commits: el árbol se calcula y el índice se vuelve a vaciar);
#   4. con --pruebas: ruff, la suite completa con el plugin de procedencia y el gate v4, con el intérprete dado
#      (Python 3.11 con constraints/ci-py311.txt instalado). Sin TIA_TEST_POSTGRESQL_URL, 10 pruebas de
#      PostgreSQL se omiten (permitidas en el job python);
#   5. comprueba que el índice (.git/index) del origen no cambió.
#
# No hace commits, push, merge ni deploy, no habilita trading real y no toca el repositorio de origen.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGEN=""; DESTINO=""; PY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --destino) DESTINO="$2"; shift 2 ;;
    --pruebas) PY="$2"; shift 2 ;;
    -h|--help) sed -n 2,17p "$0"; exit 0 ;;
    *) [[ -z "$ORIGEN" ]] && ORIGEN="$1" || { echo "argumento inesperado: $1" >&2; exit 2; }; shift ;;
  esac
done
[[ -n "$ORIGEN" ]] || { echo "uso: bash reproducir.sh <repositorio_origen> [--destino DIR] [--pruebas PYTHON311]" >&2; exit 2; }
ORIGEN="$(cd "$ORIGEN" && pwd)"
BASE=72ffae5d2698440c8f1afaff12e07bd8adde66fb
ARBOL_BASE=44850cfcbf53c3f8223d38a92031f4402f8ffb32
ARBOL_FINAL=17332e1c510d0004f7744bde0a68f008f01652b7
fallas=0

echo "== 1. manifiesto del paquete"
(cd "$AQUI" && sha256sum --quiet -c MANIFEST.sha256) && echo "MANIFEST.sha256: todo verifica" || { echo "MANIFEST.sha256 NO verifica"; exit 3; }

echo "== 2. clon aislado"
git -C "$ORIGEN" cat-file -e "$BASE^{commit}" 2>/dev/null || { echo "el origen no tiene el commit base $BASE"; exit 3; }
INDICE_ANTES=$(sha256sum "$ORIGEN/.git/index" 2>/dev/null | cut -c1-64 || echo "sin-indice")
if [[ -z "$DESTINO" ]]; then DESTINO="$(mktemp -d "${TMPDIR:-/tmp}/tia_reproduccion.XXXXXX")/clon"; fi
# La ruta se resuelve SIN crear nada (realpath -m), y se compara con el origen antes de tocar el disco.
DESTINO="$(realpath -m -- "$DESTINO")"
case "$DESTINO/" in "$(realpath -m -- "$ORIGEN")"/*) echo "el destino no puede estar dentro del origen"; exit 3 ;; esac
[[ -e "$DESTINO" ]] && { echo "el destino $DESTINO ya existe; elegí uno nuevo"; exit 3; }
mkdir -p -- "$(dirname "$DESTINO")"
git clone -q --no-local "$ORIGEN" "$DESTINO"
git -C "$DESTINO" checkout -q --detach "$BASE"
git -C "$DESTINO" remote set-url --push origin no-push://integracion-controlada
arbol() { git -C "$DESTINO" add -A && git -C "$DESTINO" write-tree; git -C "$DESTINO" reset -q; }
t=$(arbol); echo "base: $t $([[ $t == "$ARBOL_BASE" ]] && echo OK || { echo DISTINTO; })"; [[ $t == "$ARBOL_BASE" ]] || fallas=$((fallas+1))

echo "== 3. cadena de parches"
while IFS='|' read -r paso parche sha esperado; do
  [[ "$paso" =~ ^# || -z "$paso" ]] && continue
  real=$(sha256sum "$AQUI/$parche" | cut -c1-64)
  [[ "$real" == "$sha" ]] || { echo "$paso $parche: sha256 DISTINTO ($real)"; fallas=$((fallas+1)); continue; }
  git -C "$DESTINO" apply --check "$AQUI/$parche" && git -C "$DESTINO" apply "$AQUI/$parche" || { echo "$paso $parche: NO APLICA"; exit 4; }
  if [[ "$esperado" == "-" ]]; then echo "$paso $(basename "$parche"): aplicado"; continue; fi
  t=$(arbol); ok=$([[ "$t" == "$esperado" ]] && echo OK || echo DISTINTO)
  echo "$paso $(basename "$parche"): $t $ok"; [[ $ok == OK ]] || fallas=$((fallas+1))
done < "$AQUI/parches/CADENA.txt"
t=$(arbol); echo "árbol final: $t $([[ $t == "$ARBOL_FINAL" ]] && echo 'OK (candidato)' || echo DISTINTO)"; [[ $t == "$ARBOL_FINAL" ]] || fallas=$((fallas+1))

if [[ -n "$PY" ]]; then
  echo "== 4. pruebas con $("$PY" --version 2>&1)"
  ( set +e; cd "$DESTINO" || exit 1
    export PYTHONPATH=packages/tia/src CI_RUN_NONCE="reproduccion-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
    "$PY" -m ruff check packages tests scripts; r1=$?; echo "ruff rc=$r1"
    "$PY" -m pytest tests -q -p scripts.ci_provenance --junitxml=ci-evidence/junit.xml > "$(dirname "$DESTINO")/pytest.txt" 2>&1
    r2=$?; echo "pytest rc=$r2 (salida en $(dirname "$DESTINO")/pytest.txt)"
    "$PY" scripts/ci_gate.py ci-evidence ci-evidence/junit.xml; r3=$?; echo "gate rc=$r3"
    exit $(( r1 + r2 + r3 > 0 )) ) || fallas=$((fallas+1))
fi

echo "== 5. origen intacto"
INDICE_DESPUES=$(sha256sum "$ORIGEN/.git/index" 2>/dev/null | cut -c1-64 || echo "sin-indice")
[[ "$INDICE_ANTES" == "$INDICE_DESPUES" ]] && echo "índice del origen: IGUAL ($INDICE_DESPUES)" || { echo "índice del origen: CAMBIÓ"; fallas=$((fallas+1)); }
echo "clon de trabajo: $DESTINO (borralo cuando termines)"
echo "RESULTADO: $([[ $fallas == 0 ]] && echo 'reproducido sin diferencias' || echo "$fallas diferencia(s)")"
exit $(( fallas > 0 ))
