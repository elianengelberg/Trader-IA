#!/usr/bin/env bash
# Reproduce la verificación del parche D1–D3 desde una extracción limpia de esta entrega.
# NO toca el repositorio de origen: lo clona con --no-local en un directorio nuevo. NO hace commits, push ni despliegues.
#
# Uso:  bash reproducir.sh <ruta_o_URL_del_repo_Trader-IA> <dir_de_trabajo_nuevo> [rapido|completo]
#   rapido   (≈ 5 min): base identificada, git apply --check, pruebas D1–D3 contra el motor ORIGINAL (deben fallar 6/6)
#                       y contra el PARCHEADO (deben pasar 6/6), mutantes (0 vivos), ruff como la CI.
#   completo (≈ 25 min): además, la suite completa como la CI en la base (1956) y en el árbol integrado (1962).
# Requisitos: git, python3.11, red hacia pypi.org (instalación documentada de la CI).
set -euo pipefail
PKG="$(cd "$(dirname "$0")" && pwd)"; REPO="$1"; W="$2"; MODO="${3:-rapido}"
BASE=72ffae5d2698440c8f1afaff12e07bd8adde66fb
[[ -e "$W" ]] && { echo "$W ya existe: usá un directorio nuevo"; exit 1; }
mkdir -p "$W/salidas"; cd "$W"
ok() { echo "OK  $*"; }; mal() { echo "MAL $*"; exit 1; }

echo "== 1. Base y parche"
git clone -q --no-local "$REPO" base && git -C base checkout -q --detach "$BASE"
[[ "$(git -C base rev-parse HEAD)" == "$BASE" ]] && ok "base en $BASE" || mal "la base no es $BASE"
[[ "$(git -C base show HEAD:packages/tia/src/tia/backtest/engine.py | sha256sum | cut -c1-64)" == \
   "547109460bb5734ab7b108dc9387fca802e69b29cc8e74c262b80bdc55533ea4" ]] && ok "engine.py original identificado" || mal "engine.py de la base distinto"
git clone -q --no-local base integracion && git -C integracion checkout -q --detach "$BASE"
git -C integracion apply --check "$PKG/parche/integracion_D1_D3_72ffae5.patch" && ok "git apply --check limpio"
git -C integracion apply "$PKG/parche/integracion_D1_D3_72ffae5.patch"
( cd integracion && sha256sum -c "$PKG/parche/SHA256_archivos_resultantes.txt" ) && ok "archivos resultantes idénticos a los registrados"

echo "== 2. Entorno (instalación documentada de la CI: pip install -e \".[api,db,postgres,redis,llm,dev]\")"
git clone -q --no-local base instalacion && git -C instalacion checkout -q --detach "$BASE"
python3.11 -m venv venv && ( cd instalacion && ../venv/bin/pip install -q -e ".[api,db,postgres,redis,llm,dev]" )
PY="$W/venv/bin/python"; venv/bin/pip freeze > salidas/pip_freeze.txt

echo "== 3. Pruebas D1–D3 contra el motor ORIGINAL (deben fallar todas, por aserción)"
cp "$PKG/parche/test_backtest_order_hygiene.py" base/tests/unit/
( cd base && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src "$PY" -B -m pytest tests/unit/test_backtest_order_hygiene.py \
    -p no:cacheprovider -rA --tb=line > "$W/salidas/pruebas_contra_original.txt" 2>&1 ) || true
rm base/tests/unit/test_backtest_order_hygiene.py
grep -q "6 failed" salidas/pruebas_contra_original.txt && ! grep -q "^ERROR" salidas/pruebas_contra_original.txt \
  && ok "original: 6/6 fallan" || mal "original: no fallan las 6 (ver salidas/pruebas_contra_original.txt)"

echo "== 4. Pruebas D1–D3 contra el árbol INTEGRADO (deben pasar todas)"
( cd integracion && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src "$PY" -B -m pytest tests/unit/test_backtest_order_hygiene.py \
    -p no:cacheprovider -rA --tb=short > "$W/salidas/pruebas_integrado.txt" 2>&1 ) && grep -q "6 passed" salidas/pruebas_integrado.txt \
  && ok "integrado: 6/6 pasan" || mal "integrado: no pasan las 6"

echo "== 5. Mutantes (cada pieza del parche revertida por separado: ninguno debe sobrevivir)"
python3 "$PKG/herramientas/mutantes.py" "$W/integracion" "$W/mutantes" tests/unit/test_backtest_order_hygiene.py "$PY" salidas/mutantes.json > salidas/mutantes.txt
python3 - salidas/mutantes.json <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))["mutantes"]
vivos = [n for n, v in d.items() if all(s == "PASSED" for s in v["resultados"].values()) or len(v["resultados"]) != 6]
print("mutantes:", len(d), "· vivos:", vivos or "ninguno")
sys.exit(1 if vivos else 0)
PY

echo "== 6. Lint como la CI"
( cd integracion && "$W/venv/bin/ruff" check packages tests scripts ) && ok "ruff check limpio"

if [[ "$MODO" == "completo" ]]; then
  echo "== 7. Suite completa como la CI (base y árbol integrado)"
  # rutas absolutas: correr_suite_ci.sh entra al árbol antes de escribir
  bash "$PKG/herramientas/correr_suite_ci.sh" "$W/base" "$PY" "$W/salidas/suite_base.txt" "$W/salidas/suite_base.xml"
  bash "$PKG/herramientas/correr_suite_ci.sh" "$W/integracion" "$PY" "$W/salidas/suite_integracion.txt" "$W/salidas/suite_integracion.xml"
  tail -n 1 salidas/suite_base.txt salidas/suite_integracion.txt
  # Criterio: ninguna regresión frente a la base corrida en el mismo momento. Dos pruebas de la base dependen del
  # reloj (00:00–≈05:45 UTC) y una tiene un límite fijo de 10 s; con o sin el parche (R11, R13; evidencia E20–E25): por eso se
  # compara prueba a prueba con la base corrida en el mismo momento, en lugar de exigir un número fijo.
  python3 "$PKG/herramientas/comparar_suites.py" "$W/salidas/suite_base.xml" "$W/salidas/suite_integracion.xml"
  ok "suite completa: integrado = base prueba a prueba, más 6 nuevas que pasan"
fi
echo "REPRODUCCIÓN ($MODO) TERMINADA SIN DIFERENCIAS"
