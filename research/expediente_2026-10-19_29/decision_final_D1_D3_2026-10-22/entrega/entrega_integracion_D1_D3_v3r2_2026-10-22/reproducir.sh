#!/usr/bin/env bash
# Reproduce las verificaciones de la entrega v3 (decisión final: D1–D3 + trazabilidad CORREGIDA + pruebas sensibles al
# entorno + propuesta opcional de CI) desde una extracción limpia. NO toca el repositorio de origen: lo clona con --no-local en un directorio nuevo.
# NO hace commits, push, despliegues ni operaciones. No escribe fuera de <dir_de_trabajo_nuevo>.
#
# Uso:  bash reproducir.sh <ruta_o_URL_del_repo_Trader-IA> <dir_de_trabajo_nuevo> [rapido|completo] [<dir_codigo_E1>]
#   rapido   (≈ 20 min): base identificada; los parches 01, 02v3 y 03 aplican en cadena y dan los archivos registrados;
#            entorno con restricciones e igual al de referencia; pruebas D1–D3 contra el motor ORIGINAL (8/8 fallan por
#            aserción) y contra el integrado (8/8); trazabilidad (14/14); la sonda de «misma procedencia, otros números»
#            (el 02 corregido la RECHAZA); compatibilidad con registros históricos usando la API REAL de 72ffae5 y la
#            integrada sobre la misma base; mutantes D1–D3 (10, 0 vivos) y de trazabilidad (14, 0 vivos, 1 equivalente);
#            ruff como la CI; las 3 pruebas del parche 03 a 5 horas de reloj fijadas y la de persistencia 3 veces;
#            parche 04 (opcional, CI): aplica y su archivo de restricciones es el de entorno/.
#   completo (≈ 55 min): además, la suite completa como la CI en la base, la obligatoria (01+02v3) y la completa
#            (01+02v3+03), comparadas prueba a prueba; las migraciones desde cero (alembic) en la base y la completa.
#   <dir_codigo_E1> (opcional): con los datos de E1 en la ruta que fija su e1_comun.py, repite la paridad con E1.
# Requisitos: git, python3.11, red hacia PyPI (o un índice equivalente) para instalar las versiones de entorno/ci-py311.txt.
set -euo pipefail
PKG="$(cd "$(dirname "$0")" && pwd)"; REPO="$1"; W="$2"; MODO="${3:-rapido}"; E1COD="${4:-}"
BASE=72ffae5d2698440c8f1afaff12e07bd8adde66fb
[[ -e "$W" ]] && { echo "$W ya existe: usá un directorio nuevo"; exit 1; }
# Sin herencia del entorno de quien llama: ni rutas de Python, ni restricciones de pip, ni bytecode en los árboles.
unset PYTHONPATH PYTHONHOME PYTHONSTARTUP PYTHONSAFEPATH PIP_CONSTRAINT PIP_REQUIRE_VIRTUALENV VIRTUAL_ENV CONDA_PREFIX
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 TMPDIR="$W/tmp"
mkdir -p "$W/salidas" "$W/tmp"; cd "$W"
ok() { echo "OK  $*"; }; mal() { echo "MAL $*"; exit 1; }
P1="$PKG/parches/01_obligatorio_D1_D3_motor_y_pruebas_definitivas.patch"
P2="$PKG/parches/02v3_obligatorio_trazabilidad_version_motor_CORREGIDO.patch"
P4="$PKG/parches/04_opcional_CI_versiones_fijadas.patch"
P3="$PKG/parches/03_opcional_pruebas_reloj_y_persistencia.patch"

echo "== 1. Base y parches"
git clone -q --no-local "$REPO" base && git -C base checkout -q --detach "$BASE"
[[ "$(git -C base rev-parse HEAD)" == "$BASE" ]] && ok "base en $BASE" || mal "la base no es $BASE"
[[ "$(git -C base show HEAD:packages/tia/src/tia/backtest/engine.py | sha256sum | cut -c1-64)" == \
   "547109460bb5734ab7b108dc9387fca802e69b29cc8e74c262b80bdc55533ea4" ]] && ok "engine.py original identificado" || mal "engine.py de la base distinto"
for T in obligatoria completa; do git clone -q --no-local base "$T" && git -C "$T" checkout -q --detach "$BASE"; done
for p in "$P1" "$P2"; do for T in obligatoria completa; do git -C "$T" apply --check "$p" && git -C "$T" apply "$p"; done; done
git -C completa apply --check "$P3" && git -C completa apply "$P3"; ok "los parches aplican limpio en cadena (01, 02; 03 en «completa»)"
( cd obligatoria && sha256sum -c --quiet "$PKG/parches/SHA256_archivos_resultantes_obligatoria_v3.txt" ) && ok "obligatoria: archivos idénticos a los registrados"
( cd completa && sha256sum -c --quiet "$PKG/parches/SHA256_archivos_resultantes_completa_v3.txt" ) && ok "completa: archivos idénticos a los registrados"
[[ "$(git -C obligatoria status --porcelain | wc -l)" == 8 && "$(git -C completa status --porcelain | wc -l)" == 11 ]] \
  && ok "cambian 8 archivos (obligatoria) y 11 (completa)" || mal "número de archivos cambiados inesperado"

echo "== 2. Entorno: restricciones fijas (entorno/ci-py311.txt) e instalación documentada de la CI"
git clone -q --no-local base instalacion && git -C instalacion checkout -q --detach "$BASE"
python3.11 -m venv venv && ( cd instalacion && ../venv/bin/pip install -q -c "$PKG/entorno/ci-py311.txt" -e ".[api,db,postgres,redis,llm,dev]" )
PY="$W/venv/bin/python"; venv/bin/pip freeze --exclude-editable | sort > salidas/pip_freeze.txt
diff <(grep -v '^#' "$PKG/entorno/freeze_referencia.txt" | sort) salidas/pip_freeze.txt > salidas/freeze_diferencias.txt \
  && ok "entorno idéntico al de referencia ($(wc -l < salidas/pip_freeze.txt) paquetes)" || mal "el entorno difiere del de referencia (salidas/freeze_diferencias.txt)"
correr() { ( cd "$1" && PYTHONPATH=packages/tia/src "$PY" -B -m pytest -p no:cacheprovider -o addopts="" -q -rA --tb=line "${@:2}" ); }

echo "== 3. Pruebas D1–D3 definitivas contra el motor ORIGINAL (deben fallar las 8, por aserción)"
cp obligatoria/tests/unit/test_backtest_order_hygiene.py base/tests/unit/
correr base tests/unit/test_backtest_order_hygiene.py > salidas/d1d3_contra_original.txt 2>&1 || true
rm base/tests/unit/test_backtest_order_hygiene.py
grep -q "8 failed" salidas/d1d3_contra_original.txt && [[ "$(grep -c 'AssertionError' salidas/d1d3_contra_original.txt)" -ge 8 ]] \
  && ! grep -q "^ERROR" salidas/d1d3_contra_original.txt && ok "original: 8/8 fallan por aserción" || mal "original: no fallan las 8 por aserción"

echo "== 4. Pruebas D1–D3 y de trazabilidad en el árbol integrado (deben pasar todas)"
correr obligatoria tests/unit/test_backtest_order_hygiene.py > salidas/d1d3_integrado.txt 2>&1 && grep -q "8 passed" salidas/d1d3_integrado.txt \
  && ok "D1–D3: 8/8 pasan" || mal "D1–D3: no pasan las 8"
correr obligatoria tests/integration/test_backtest_provenance.py > salidas/trazabilidad.txt 2>&1 && grep -q "14 passed" salidas/trazabilidad.txt \
  && ok "trazabilidad: 14/14 pasan" || mal "trazabilidad: no pasan las 14"
"$PY" -I -B "$PKG/herramientas/sonda_misma_procedencia.py" "$W/obligatoria" "$W/tmp" > salidas/sonda_misma_procedencia.txt 2>&1
grep -q "segundo guardado: RECHAZADO" salidas/sonda_misma_procedencia.txt && ok "misma procedencia y otros números: el guardado lo rechaza" || mal "la sonda de misma procedencia no fue rechazada"
"$PY" -I -B "$PKG/herramientas/compat_historica.py" "$W/base" "$W/tmp/compat.db" salidas/compat_1.json correr > salidas/compat.log 2>&1 \
  && "$PY" -I -B "$PKG/herramientas/compat_historica.py" "$W/obligatoria" "$W/tmp/compat.db" salidas/compat_2.json correr >> salidas/compat.log 2>&1 \
  && "$PY" -I -B "$PKG/herramientas/compat_historica.py" "$W/base" "$W/tmp/compat.db" salidas/compat_3.json >> salidas/compat.log 2>&1
"$PY" -I - salidas/compat_1.json salidas/compat_2.json salidas/compat_3.json <<'PYX' && ok "registros históricos: la fila de 72ffae5 convive intacta (engine_version null) y la API vieja sigue leyendo" || mal "compatibilidad con registros históricos"
import json, sys
a, b, c = (json.load(open(x)) for x in sys.argv[1:4])
vieja = a["listado"][0]; ids_b = {r["run_id"]: r for r in b["listado"]}; ids_c = {r["run_id"]: r for r in c["listado"]}
ok = (a["post_status"] == b["post_status"] == 200 and b["post_run_id"] != a["post_run_id"] and len(b["listado"]) == 2
      and ids_b[a["post_run_id"]]["engine_version"] is None and ids_b[b["post_run_id"]]["engine_version"]
      and all(ids_b[a["post_run_id"]][k] == vieja[k] for k in vieja) and all(ids_c[a["post_run_id"]][k] == vieja[k] for k in vieja))
sys.exit(0 if ok else 1)
PYX

echo "== 5. Mutantes (cada uno debe hacer fallar al menos una prueba)"
"$PY" -I "$PKG/herramientas/mutantes_v2.py" "$W/obligatoria" "$W/mutantes_d1d3" tests/unit/test_backtest_order_hygiene.py "$PY" salidas/mutantes_d1d3.json > salidas/mutantes_d1d3.txt
"$PY" -I - salidas/mutantes_d1d3.json <<'PYX'
import json, sys
d = json.load(open(sys.argv[1]))["mutantes"]
vivos = [n for n, v in d.items() if len(v["resultados"]) != 8 or all(s == "PASSED" for s in v["resultados"].values())]
print("mutantes D1–D3:", len(d), "· vivos:", vivos or "ninguno"); sys.exit(1 if vivos or len(d) != 10 else 0)
PYX
"$PY" -I "$PKG/herramientas/mutantes_traza_v2.py" "$W/obligatoria" "$W/mutantes_traza" tests/integration/test_backtest_provenance.py "$PY" salidas/mutantes_traza.json > salidas/mutantes_traza.txt \
  && ok "mutantes de trazabilidad: 0 vivos ($(grep -c '^T' salidas/mutantes_traza.txt) mutantes, 1 equivalente justificado)" || mal "mutantes de trazabilidad: hay vivos"

echo "== 5b. Parche 04 (opcional, CI): aplica sobre la base y fija las mismas versiones que entorno/ci-py311.txt"
git clone -q --no-local base ci04 && git -C ci04 checkout -q --detach "$BASE" && git -C ci04 apply --check "$P4" && git -C ci04 apply "$P4"
diff <(grep -v '^#' ci04/constraints/ci-py311.txt) <(grep -v '^#' "$PKG/entorno/ci-py311.txt") > /dev/null && grep -q -- "-c constraints/ci-py311.txt" ci04/.github/workflows/ci.yml \
  && ok "parche 04: ci.yml instala con -c constraints/ci-py311.txt (mismas versiones)" || mal "parche 04"

echo "== 6. Lint como la CI"
for T in obligatoria completa; do ( cd "$T" && "$W/venv/bin/ruff" check packages tests scripts > "$W/salidas/ruff_$T.txt" ) && ok "ruff limpio en $T"; done

echo "== 7. Pruebas sensibles al entorno con el reloj de pared fijado (time-machine en un entorno aparte)"
python3.11 -m venv venv_reloj && ( cd instalacion && ../venv_reloj/bin/pip install -q -c "$PKG/entorno/ci-py311.txt" -e ".[api,db,postgres,redis,llm,dev]" ) \
  && venv_reloj/bin/pip install -q "time-machine==3.5.1"
RELOJ=(tests/integration/test_risk_state_persistence.py::test_five_restored_entries_for_the_symbol_refuse_the_sixth_after_the_restart
       tests/integration/test_account_restore.py::test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_restart)
for H in 00:30 05:30 05:56 12:00 23:59; do for T in base completa; do
  R=$(cd "$T" && PYTHONPATH=packages/tia/src "$W/venv_reloj/bin/python" -B "$PKG/herramientas/con_reloj.py" "2026-10-22T$H:00+00:00" \
        -p no:cacheprovider -o addopts="" -q -rA "${RELOJ[@]}" 2>&1 | grep -cE "^PASSED" || true)
  echo "$H UTC  $T: $R/2 pasan" | tee -a salidas/reloj.txt; done; done
[[ "$(grep -c 'completa: 2/2' salidas/reloj.txt)" == 5 ]] && ok "con el parche 03 las pruebas de reloj pasan a las 5 horas" || mal "parche 03: alguna prueba de reloj no pasa"
for i in 1 2 3; do correr completa tests/integration/test_adverse_recovery.py::test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole 2>&1 | tail -1; done | tee salidas/persistencia.txt
[[ "$(grep -c '1 passed' salidas/persistencia.txt)" == 3 ]] && ok "persistencia: 3/3 con el parche 03" || mal "persistencia: no pasa 3/3"

if [[ "$MODO" == "completo" ]]; then
  echo "== 8. Suite completa como la CI: base, obligatoria y completa"
  for T in base obligatoria completa; do bash "$PKG/herramientas/correr_suite_ci.sh" "$W/$T" "$PY" "$W/salidas/suite_$T.txt" "$W/salidas/suite_$T.xml"; tail -n 2 "salidas/suite_$T.txt"; done
  python3 -I "$PKG/herramientas/comparar_suites_v2.py" salidas/suite_base.xml salidas/suite_obligatoria.xml | tee salidas/comparacion_obligatoria.txt
  python3 -I "$PKG/herramientas/comparar_suites_v2.py" salidas/suite_base.xml salidas/suite_completa.xml --corregidas | tee salidas/comparacion_completa.txt
  echo "== 8b. Migraciones desde cero como la CI (alembic upgrade head), base y completa"
  for T in base completa; do cp -a "$T" "alembic_$T"; ( cd "alembic_$T" && PYTHONPATH=packages/tia/src TIA_DATABASE_URL=sqlite:///./data/runtime/ci.db "$PY" -B -m alembic upgrade head > "$W/salidas/alembic_$T.txt" 2>&1 ) && ok "alembic upgrade head en $T" || mal "alembic en $T"; done
fi
if [[ -n "$E1COD" ]]; then
  echo "== 9. Paridad con E1 (solo comparación con lo registrado; no es un experimento)"
  "$PY" -I -B "$PKG/herramientas/paridad_e1_v2.py" "$W/obligatoria/packages/tia/src" "$E1COD" salidas/paridad.json > salidas/paridad.txt 2>&1
  "$PY" -I - salidas/paridad.json "$PKG/evidencia/P_paridad_v3_venvA.json" <<'PYX' && ok "paridad con E1: mismas huellas que la evidencia" || mal "paridad con E1: huellas distintas"
import json, sys
a, b = (json.load(open(x))["configuraciones"] for x in sys.argv[1:3])
k = ("h_operaciones_completas", "h_equity", "h_metricas", "h_decisiones", "h_registro_de_decisiones")
sys.exit(0 if all(a[n][c] == b[n][c] for n in ("P1", "P2", "P3", "S1") for c in k) else 1)
PYX
fi
echo "REPRODUCCIÓN ($MODO) TERMINADA SIN DIFERENCIAS"
