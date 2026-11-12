#!/usr/bin/env bash
# Arma el directorio de entrega con la estructura pedida (Fase H), su MANIFEST.sha256, el ZIP y su .sha256.
# Solo copia: no modifica evidencia ni artefactos congelados. Uso: armar_paquete.sh <dir_mision> <scratchpad>
set -euo pipefail
F="$1"; S="$2"; N=cierre_integral_2026-10-22; E="$F/entrega"; P="$E/$N"
X=$F/extraccion_paquete/cierre_D1_D2_guarda_R19_2026-10-22; V=$F/extraccion_v3r3/entrega_integracion_D1_D3_v3r3_2026-10-22
R1=$F/reproduction/E1_v3r3_completo; FIN=$F/reproduction/E2_final_v3/final
[[ -e "$P" ]] && { echo "$P ya existe"; exit 1; }
mkdir -p "$P"/{patches/v3r3,tests/referencia,logs,evidence,reproduction/herramientas,config}
# Documentos principales
cp "$F"/docs/{INFORME_CIERRE_FINAL.md,MATRIZ_RIESGOS.md,RESULTADOS_R19.md,PLAN_INTEGRACION.md} "$P/"
cp "$F/docs/COMANDOS_REPRODUCCION.md" "$P/reproduction/"
cp "$F/docs/LEEME.md" "$P/"
# Parches: nuevos de esta misión y copias idénticas de los de v3r3 (con sus listas de archivos resultantes)
cp "$F"/patches/*.patch "$P/patches/"
cp "$F/trabajo/guarda_v2/guarda_v1_a_v2.diff" "$P/patches/"
cp "$V"/parches/01_*.patch "$V"/parches/02v3_*.patch "$V"/parches/03_*.patch "$V"/parches/04_*.patch "$V"/parches/SHA256_archivos_resultantes_*.txt "$P/patches/v3r3/"
# Pruebas propuestas (contenido de los parches) y la v1 de referencia
cp "$F/trabajo/guarda_v2/test_engine_version_contract.py" "$P/tests/"
cp "$FIN/scripts/ci_gate.py" "$P/tests/ci_gate.py"
cp "$F/trabajo/r24/tests/integration/test_backtest_store_postgresql.py" "$P/tests/"
cp "$X/fase2/guarda/test_engine_version_contract.py" "$P/tests/referencia/test_engine_version_contract_v1.py"
# Herramientas de esta misión
cp "$F"/herramientas/*.py "$F"/herramientas/*.sh "$P/reproduction/herramientas/"
# Evidencia (sin las bases SQLite temporales de R19) y registros
tar -C "$F/evidence" --exclude='./R19_corrida_principal/tmp' --exclude='./R19_suplementaria/tmp' -cf - . | tar -C "$P/evidence" -xf -
cp -r "$F/registro" "$P/evidence/registro"
# Registros de ejecución: los de esta misión (logs/E ya trae las salidas de la reproducción limpia de v3r3 y los ci-evidence)
cp -r "$F/logs/." "$P/logs/"
# Configuración saneada
cp "$FIN/.github/workflows/ci.yml" "$P/config/ci.yml"
cp "$FIN/constraints/ci-py311.txt" "$P/config/ci-py311.txt"
"$S/cierre_D1_D3_2026-10-22/entorno/venv_A/bin/python" -m pip freeze --exclude-editable | sort > "$P/config/pip_freeze_entorno_local.txt"
sed -n '/^\[tool.pytest.ini_options\]/,/^\[tool.ruff\]/p' "$FIN/pyproject.toml" | sed '$d' > "$P/config/pytest_de_pyproject.toml"
cp "$X/fase3/plan_r19_enmienda1.json" "$P/config/plan_r19_enmienda1.json"
# Sin bytecode ni enlaces
find "$P" -name __pycache__ -prune -exec rm -rf {} + ; find "$P" -name '*.pyc' -delete
[[ -z "$(find "$P" -type l)" ]] || { echo "hay enlaces simbólicos"; exit 1; }
# Escaneo de secretos (patrones típicos); cada coincidencia se lista para revisión manual
{ echo "== escaneo de secretos: $(date -u +%FT%TZ)"
  grep -rnIE "BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[0-9A-Za-z]{30,}|xox[baprs]-|(api[_-]?key|secret|password|token)[\"']?[[:space:]]*[:=][[:space:]]*[\"'][^\"' ]{6,}" "$P" \
    | grep -v "/evidence/R19_" | cut -c1-220 || echo "(sin coincidencias)"; } > "$P/config/ESCANEO_SECRETOS.txt"
# Manifiesto, ZIP y hash
(cd "$P" && find . -type f ! -name MANIFEST.sha256 | sed 's#^\./##' | LC_ALL=C sort | xargs -d '\n' sha256sum > MANIFEST.sha256)
(cd "$E" && rm -f "$N.zip" && zip -qrX "$N.zip" "$N" && sha256sum "$N.zip" > "$N.zip.sha256")
echo "archivos: $(wc -l < "$P/MANIFEST.sha256") · ZIP: $(stat -c %s "$E/$N.zip") bytes · $(cat "$E/$N.zip.sha256")"
