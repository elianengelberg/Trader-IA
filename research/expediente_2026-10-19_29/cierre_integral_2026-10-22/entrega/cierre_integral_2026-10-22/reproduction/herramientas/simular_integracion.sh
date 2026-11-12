#!/usr/bin/env bash
# Simula la secuencia de integración SIN commits, en clones aislados (push deshabilitado): unidad A (01+02v3), unidad B
# (guarda 05), reversión de B, reversión conjunta de A, B sin A, archivos exactos, consistencia de versión y árboles
# esperados (git write-tree escribe objetos de árbol en el clon aislado: no crea commits ni toca refs).
# Uso: simular_integracion.sh <dir_trabajo_nuevo> <parches_v3r3> <parche_05> <python> <herramientas>
set -uo pipefail
W="$1"; P="$2"; B05="$3"; PY="$4"; H="$5"; BASE=72ffae5d2698440c8f1afaff12e07bd8adde66fb
OCHO="docs/ARCHITECTURE.md packages/tia/src/tia/api/state.py packages/tia/src/tia/backtest/engine.py packages/tia/src/tia/backtest/result.py packages/tia/src/tia/execution/paper.py packages/tia/src/tia/persistence/repositories.py tests/integration/test_backtest_provenance.py tests/unit/test_backtest_order_hygiene.py"
G=tests/integration/test_engine_version_contract.py
ok() { echo "OK   $*"; }; mal() { echo "MAL  $*"; FALLAS=$((FALLAS+1)); }; FALLAS=0
pt() { (cd "$1" && PYTHONPATH=packages/tia/src "$PY" -B -m pytest -p no:cacheprovider -o addopts="" -q -rA "${@:2}" 2>&1 | tail -1); }
arbol() { git -C "$1" add -A >/dev/null && git -C "$1" write-tree; }   # árbol del contenido (objetos en el clon; sin commit)
mkdir -p "$W"
bash "$H/clon_seguro.sh" "$W/sim" "$BASE"; S="$W/sim"
T0=$(git -C "$S" rev-parse HEAD^{tree}); echo "árbol base 72ffae5: $T0"
echo "== 1. Unidad A: 01 y después 02v3, en ese orden"
git -C "$S" apply --check "$P"/01_*.patch && git -C "$S" apply "$P"/01_*.patch && ok "01 aplica" || mal "01 no aplica"
git -C "$S" apply --check "$P"/02v3_*.patch && git -C "$S" apply "$P"/02v3_*.patch && ok "02v3 aplica sobre 01" || mal "02v3 no aplica"
diff <(git -C "$S" status --porcelain | awk '{print $2}' | LC_ALL=C sort) <(printf "%s\n" $OCHO | LC_ALL=C sort) >/dev/null && ok "A cambia exactamente los 8 archivos previstos" || mal "A no cambia los 8 archivos previstos"
(cd "$S" && sha256sum -c --quiet "$P/SHA256_archivos_resultantes_obligatoria_v3.txt") && ok "archivos de A = los registrados en v3r3" || mal "archivos de A distintos"
V=$(cd "$S" && PYTHONPATH=packages/tia/src "$PY" -I -c "import sys; sys.path.insert(0,'packages/tia/src'); from tia.backtest.engine import ENGINE_VERSION as v; print(v)")
[[ "$V" == "1.1.0" ]] && ok "versión declarada tras A: $V" || mal "versión tras A: $V"
echo "   pruebas de A: higiene $(pt "$S" tests/unit/test_backtest_order_hygiene.py) · trazabilidad $(pt "$S" tests/integration/test_backtest_provenance.py)"
TA=$(arbol "$S"); echo "árbol esperado tras A: $TA"
echo "== 2. Unidad B (guarda 05) sobre A"
git -C "$S" apply --check "$B05" && git -C "$S" apply "$B05" && ok "05 aplica sobre A" || mal "05 no aplica sobre A"
[[ "$(git -C "$S" diff --name-only HEAD -- "$G"; git -C "$S" status --porcelain -- "$G" | awk '{print $2}')" == *"$G"* ]] && ok "B agrega solo $G"
echo "   guarda tras B: $(pt "$S" "$G")"
TB=$(arbol "$S"); echo "árbol esperado tras A+B: $TB"
echo "== 3. Reversión de B"
git -C "$S" apply -R "$B05" && [[ "$(arbol "$S")" == "$TA" ]] && ok "revertir B devuelve exactamente el árbol de A" || mal "revertir B no devuelve el árbol de A"
echo "== 4. Reversión conjunta de A (02v3 y después 01)"
git -C "$S" apply -R "$P"/02v3_*.patch && git -C "$S" apply -R "$P"/01_*.patch && [[ "$(arbol "$S")" == "$T0" ]] && ok "revertir A devuelve exactamente el árbol de 72ffae5" || mal "revertir A no devuelve la base"
[[ -z "$(git -C "$S" status --porcelain)" ]] && ok "sin cambios ajenos tras revertir" || mal "quedan cambios: $(git -C "$S" status --porcelain | head -3)"
echo "== 5. B sin A (combinación inválida) y A a medias"
git -C "$S" apply "$B05" && echo "   base + B: $(pt "$S" "$G")"; git -C "$S" apply -R "$B05"
git -C "$S" apply "$P"/02v3_*.patch && git -C "$S" apply "$B05" && echo "   02v3 sin 01 + B: $(pt "$S" "$G")"; git -C "$S" apply -R "$B05"; git -C "$S" apply -R "$P"/02v3_*.patch
git -C "$S" apply "$P"/01_*.patch && git -C "$S" apply "$B05" && echo "   01 sin 02v3 + B (02v3 revertido solo): $(pt "$S" "$G")"; git -C "$S" apply -R "$B05"; git -C "$S" apply -R "$P"/01_*.patch
[[ "$(arbol "$S")" == "$T0" ]] && ok "el clon vuelve a la base después de las combinaciones" || mal "el clon no volvió a la base"
echo "== 6. Orden: 02v3 antes que 01 también aplica (por eso el orden lo fija el procedimiento)"
git -C "$S" apply --check "$P"/02v3_*.patch && git -C "$S" apply "$P"/02v3_*.patch && git -C "$S" apply --check "$P"/01_*.patch && git -C "$S" apply "$P"/01_*.patch \
  && [[ "$(arbol "$S")" == "$TA" ]] && ok "02v3→01 da el mismo árbol que 01→02v3" || mal "el orden cambia el resultado"
git -C "$S" apply -R "$P"/01_*.patch; git -C "$S" apply -R "$P"/02v3_*.patch
echo "== 7. 03 sobre A+B y árbol completo"
git -C "$S" apply "$P"/01_*.patch && git -C "$S" apply "$P"/02v3_*.patch && git -C "$S" apply "$B05" && git -C "$S" apply --check "$P"/03_*.patch && git -C "$S" apply "$P"/03_*.patch && ok "03 aplica sobre A+B"
TC=$(arbol "$S"); echo "árbol esperado tras A+B+03: $TC"
echo "RESULTADO: $FALLAS problemas"
