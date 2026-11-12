#!/usr/bin/env bash
# Verifica el paquete final desde una extracción limpia e independiente, usando SOLO lo extraído (más el repositorio protegido,
# leído con clone --no-local). Uso: verificar_paquete_final.sh <dir_con_zip> <dir_nuevo> <python_del_entorno> <v3r3_SHA256SUMS>
set -uo pipefail
E="$1"; D="$2"; PY="$3"; V3SUMS="$4"; N=cierre_integral_2026-10-22; BASE=72ffae5d2698440c8f1afaff12e07bd8adde66fb
[[ -e "$D" ]] && { echo "$D ya existe"; exit 1; }
FALLAS=0; ok() { echo "OK   $*"; }; mal() { echo "MAL  $*"; FALLAS=$((FALLAS+1)); }
mkdir -p "$D/extraido" "$D/trabajo"
echo "== $(date -u +%FT%TZ) · verificación de $N desde una extracción limpia"
(cd "$E" && sha256sum -c "$N.zip.sha256") && ok "SHA-256 del ZIP: $(cut -c1-64 "$E/$N.zip.sha256")" || mal "SHA-256 del ZIP"
echo "entradas en el directorio de extracción antes: $(ls -A "$D/extraido" | wc -l)"
unzip -q "$E/$N.zip" -d "$D/extraido"; X="$D/extraido/$N"
(cd "$X" && sha256sum -c --quiet MANIFEST.sha256) && ok "MANIFEST.sha256: $(wc -l < "$X/MANIFEST.sha256") de $(wc -l < "$X/MANIFEST.sha256") verifican" || mal "MANIFEST"
diff <(cd "$X" && find . -type f ! -name MANIFEST.sha256 | sed 's#^\./##' | LC_ALL=C sort) <(awk '{print $2}' "$X/MANIFEST.sha256" | LC_ALL=C sort) >/dev/null && ok "sin archivos de más ni de menos" || mal "archivos de más o de menos"
[[ -z "$(find "$X" -type l -o -name '*.pyc' -o -name __pycache__)" ]] && ok "0 enlaces y 0 bytecode" || mal "hay enlaces o bytecode"
for f in INFORME_CIERRE_FINAL.md MATRIZ_RIESGOS.md RESULTADOS_R19.md PLAN_INTEGRACION.md MANIFEST.sha256; do [[ -f "$X/$f" ]] || mal "falta $f"; done
for d in patches tests logs evidence reproduction config; do [[ -d "$X/$d" ]] || mal "falta $d/"; done; ok "estructura pedida presente"
echo "== copias de v3r3 byte a byte"
for f in "$X"/patches/v3r3/*; do b=$(basename "$f"); h=$(sha256sum < "$f" | cut -c1-64)
  grep -q "^$h  parches/$b$" "$V3SUMS" && echo "   = v3r3: $b" || mal "patches/v3r3/$b difiere de v3r3"; done
echo "== árboles esperados reconstruidos SOLO con los parches extraídos"
H="$X/reproduction/herramientas"; P="$X/patches"; Q="$X/patches/v3r3"; T="$D/trabajo/final"
bash "$H/clon_seguro.sh" "$T" "$BASE" >/dev/null 2>&1
arbol() { git -C "$T" add -A >/dev/null && git -C "$T" write-tree; git -C "$T" reset -q; }
git -C "$T" apply "$Q"/01_*.patch && git -C "$T" apply "$Q"/02v3_*.patch; [[ "$(arbol)" == 5d6a09549a8314f6e6e9386f82a52ca7628510d1 ]] && ok "A = 5d6a0954…" || mal "árbol de A"
(cd "$T" && sha256sum -c --quiet "$Q/SHA256_archivos_resultantes_obligatoria_v3.txt") && ok "archivos de A = los registrados en v3r3" || mal "archivos de A"
git -C "$T" apply "$P"/05v2_*.patch; [[ "$(arbol)" == 4ef14d31d686f4b0521207bd1e011d96e6c74822 ]] && ok "A+B = 4ef14d31…" || mal "árbol de A+B"
git -C "$T" apply "$Q"/03_*.patch; [[ "$(arbol)" == 84f9e349526d061771de74ae799d4ecd6e3732ce ]] && ok "A+B+03 = 84f9e349…" || mal "árbol de A+B+03"
git -C "$T" apply "$Q"/04_*.patch && git -C "$T" apply "$P"/06v3_*.patch; [[ "$(arbol)" == 0477c6a20c5e3831c2da3bf723948b7baafaa518 ]] && ok "A+B+03+04+06v3 = 0477c6a2… (el árbol de la suite final)" || mal "árbol final"
[[ "$(git -C "$T" remote get-url --push origin)" == no-push://* ]] && ok "clon con push deshabilitado"
echo "== tests/ = el contenido que dejan los parches"
cmp -s "$X/tests/test_engine_version_contract.py" "$T/tests/integration/test_engine_version_contract.py" && ok "tests/test_engine_version_contract.py = 05v2" || mal "guarda distinta"
cmp -s "$X/tests/ci_gate.py" "$T/scripts/ci_gate.py" && ok "tests/ci_gate.py = 06v3" || mal "gate distinto"
git -C "$T" apply --check "$P"/07_*.patch && git -C "$T" apply "$P"/07_*.patch && cmp -s "$X/tests/test_backtest_store_postgresql.py" "$T/tests/integration/test_backtest_store_postgresql.py" && ok "tests/test_backtest_store_postgresql.py = 07 (y 07 aplica sobre el árbol final)" || mal "07"
git -C "$T" apply -R "$P"/07_*.patch
cmp -s "$X/config/ci.yml" "$T/.github/workflows/ci.yml" && cmp -s "$X/config/ci-py311.txt" "$T/constraints/ci-py311.txt" && ok "config/ci.yml y config/ci-py311.txt = los del árbol final" || mal "config distinta"
echo "== ejecución desde lo extraído"
(cd "$T" && "$(dirname "$PY")/ruff" check packages tests scripts >/dev/null) && ok "ruff (packages tests scripts) limpio en el árbol final" || mal "ruff"
R=$(cd "$T" && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src "$PY" -B -m pytest -p no:cacheprovider -o addopts="" -q tests/integration/test_engine_version_contract.py 2>&1 | tail -1)
[[ "$R" == "7 passed"* ]] && ok "guarda 05v2: $R" || mal "guarda: $R"
bash "$H/clon_seguro.sh" "$D/trabajo/base_ref" "$BASE" >/dev/null 2>&1
"$PY" -I -B "$H/pruebas_gate.py" "$T" "$X/logs/E/E4_final_v3_06v3_ci_evidence/junit.xml" "$D/trabajo/base_ref" "$PY" "$D/trabajo/gate" /usr/bin/python3.11 > "$D/trabajo/gate.txt" 2>&1 \
  || true
grep -q "RESULTADO: 11/11" "$D/trabajo/gate.txt" && ok "pruebas del gate 06v3 con el JUnit de logs/: $(grep RESULTADO "$D/trabajo/gate.txt")" || { mal "pruebas del gate"; tail -5 "$D/trabajo/gate.txt"; }
bash "$H/simular_integracion.sh" "$D/trabajo/sim" "$Q" "$P/05v2_guarda_version_motor.patch" "$PY" "$H" > "$D/trabajo/sim.txt" 2>&1
grep -q "RESULTADO: 0 problemas" "$D/trabajo/sim.txt" && ok "simulación de integración desde lo extraído: 0 problemas" || { mal "simulación"; grep MAL "$D/trabajo/sim.txt"; }
echo "== referencias de los documentos a rutas del paquete"
faltan=$(cd "$X" && grep -ohE '`(evidence|logs|patches|tests|reproduction|config)/[^`*<> ]+`' *.md reproduction/*.md | tr -d '`' | sed 's#[:,].*##' | sort -u | while read -r r; do [[ -e "$r" ]] || echo "$r"; done)
[[ -z "$faltan" ]] && ok "todas las rutas citadas en los documentos existen" || { echo "rutas citadas que no existen:"; echo "$faltan" | sed 's/^/   /'; mal "rutas citadas inexistentes"; }
echo "RESULTADO: $FALLAS problemas · fin $(date -u +%FT%TZ)"
