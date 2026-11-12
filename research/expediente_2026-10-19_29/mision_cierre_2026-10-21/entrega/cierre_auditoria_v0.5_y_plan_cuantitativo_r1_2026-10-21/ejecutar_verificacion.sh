#!/usr/bin/env bash
# Regenera la evidencia NUEVA de esta entrega. La de v0.5 la reproduce su propio ejecutar_todo.sh: ver
# 07_MANIFIESTO_EVIDENCIA.md. Solo lee el repositorio y las entregas anteriores; escribe únicamente en evidencia/ y en
# un temporal propio que borra al terminar. No usa la red ni lee datos de mercado. Variables:
#   V05_ZIP   ZIP v0.5 (obligatorio): se exige SHA-256 5bf9bc5d… y se extrae a un temporal
#   PY        intérprete con pytest (por defecto, el venv de hcarry_next)
#   REPO      raíz del repositorio (opcional: huella, inventario, declaración de T y colección de v0.5)
#   SCRATCH   carpeta con las entregas anteriores (opcional: inventario)
#   PEC_PY_NUMPY  intérprete con numpy para el contraste diferencial con E3 (opcional; si falta, se omite)
set -u
PAQ="$(cd "$(dirname "$0")" && pwd)"
EV="$PAQ/evidencia"
PY=${PY:-/home/user/Trader-IA/research/hcarry_next/.venv/bin/python}
V05_ZIP=${V05_ZIP:?indicá el ZIP v0.5}
REPO=${REPO:-}
SCRATCH=${SCRATCH:-}
SHA_V05=5bf9bc5d004b51188fdd407ae71eaae2ccefec7251af7001f8d89b264b4f5308
export PYTHONDONTWRITEBYTECODE=1
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP"
mkdir -p "$EV"
cd "$PAQ"
FALLAS=0
DESVIACIONES=0
paso() { echo "== $*"; }
falla() { FALLAS=$((FALLAS + 1)); echo "FALLA: $*"; }

paso "0. integridad del paquete antes de empezar"
if [ -f SHA256SUMS.txt ]; then sha256sum -c --quiet SHA256SUMS.txt && echo "SHA256SUMS OK" || falla "SHA256SUMS"; fi

paso "1. v0.5: SHA-256 y extracción"
[ "$(sha256sum < "$V05_ZIP" | cut -c1-64)" = "$SHA_V05" ] || { echo "el ZIP v0.5 no es el esperado"; exit 2; }
(cd "$TMP" && unzip -q "$V05_ZIP")
V="$TMP/solucion_final_trader_ia_v0.5_2026-10-20"
(cd "$V" && sha256sum -c --quiet SHA256SUMS.txt) || falla "SHA256SUMS de v0.5"

paso "B1. ZIP v0.5: verificar_zip.py del paquete, unzip -t y comprobación independiente"
{ (cd "$TMP" && "$PY" -I -B "$V/verificar_zip.py" "$V05_ZIP" solucion_final_trader_ia_v0.5_2026-10-20 | sed "s#$TMP#<tmp>#g")
  unzip -tq "$V05_ZIP" | sed 's#.*/##'
  "$PY" -I -B auditoria/comprobaciones_v05.py zip "$V05_ZIP"; } > "$EV/B1_zip_v05.txt" 2>&1 || falla B1
paso "B2. registro de acciones de v0.5"
"$PY" -I -B auditoria/comprobaciones_v05.py registro "$V" > "$EV/B2_registro_acciones_v05.txt" 2>&1 || falla B2
paso "B4. etapa 13: v0.5 frente a la corrección propuesta (12 escenarios en copias nuevas)"
for v in original corregido; do
  sed -n '/^echo "== 13\./,/^cat "\$EVID\/97_paquete_intacto.txt"/p' "correcciones_propuestas_v0.5.1/$v/ejecutar_todo.sh" > "$TMP/etapa13_$v.sh"
done
cmp -s <(sed -n '/^echo "== 13\./,/^cat "\$EVID\/97_paquete_intacto.txt"/p' "$V/ejecutar_todo.sh") "$TMP/etapa13_original.sh" \
  || falla "la etapa 13 «original» no es la de v0.5"
mkdir -p "$TMP/e13"
{ echo "-- ANTES (etapa 13 de v0.5)"; bash correcciones_propuestas_v0.5.1/probar_etapa13.sh "$V" "$TMP/etapa13_original.sh" "$TMP/e13"
  echo "-- DESPUÉS (etapa 13 corregida, propuesta v0.5.1)"; bash correcciones_propuestas_v0.5.1/probar_etapa13.sh "$V" "$TMP/etapa13_corregido.sh" "$TMP/e13"
} > "$EV/B4_etapa13_antes_despues.txt" 2>&1
[ "$(grep -c 'DIFERENCIA' "$EV/B4_etapa13_antes_despues.txt")" = 3 ] || falla "B4: se esperaban 3 diferencias antes y 0 después"
paso "B5. afirmaciones de v0.5 frente a su evidencia empaquetada (y a la colección real de pytest)"
COL=""
if [ -n "$REPO" ]; then
  (cd "$V/pruebas" && PYTHONPATH="$REPO/research/tendencia_btc/src:$REPO/research/hcarry_next/src" "$PY" -B -m pytest \
    -p no:cacheprovider --collect-only -q p1 p2 p4 cruzada integracion regresion/p1_v0_3_portadas) > "$TMP/coleccion.txt" 2>&1
  COL="$TMP/coleccion.txt"
fi
"$PY" -I -B auditoria/afirmaciones_vs_evidencia.py "$V" "$V/evidencia" $COL > "$EV/B5_afirmaciones_vs_evidencia_v05.md" 2>&1
echo "salida: $? (1 = hay discrepancias; se esperan exactamente las documentadas: C14/D-3)" >> "$EV/B5_afirmaciones_vs_evidencia_v05.md"
paso "B6. análisis estático del código de v0.5"
"$PY" -I -B auditoria/comprobaciones_v05.py estatico "$V/codigo/verificacion" > "$EV/B6_estatico_v05.txt" 2>&1 || falla B6
paso "C1. declaración de T para firmar"
"$PY" -I -B auditoria/comprobaciones_v05.py declaracion documentos_para_autorizar/R3_declaracion_T \
  ${REPO:+"$REPO/research/tendencia_btc"} > "$EV/C1_declaracion_T.txt" 2>&1 || falla C1
cmp -s documentos_para_autorizar/R3_declaracion_T/DECLARACION_A_FIRMAR_FUERA_DE_MUESTRA_T.bin \
  "$V/trazabilidad_T/DECLARACION_A_FIRMAR_FUERA_DE_MUESTRA_T.bin" && echo "la copia del .bin es idéntica a la de v0.5" \
  >> "$EV/C1_declaracion_T.txt" || falla "C1: la copia del .bin difiere de v0.5"

paso "F1. pruebas del protocolo cuantitativo (sintéticas)"
(cd protocolo_cuantitativo/pruebas && "$PY" -B -m pytest -p no:cacheprovider -q -rs) > "$EV/F1_pruebas_protocolo.txt" 2>&1 \
  || falla F1
tail -1 "$EV/F1_pruebas_protocolo.txt"
paso "F2. estilo (ruff, mismas reglas que v0.5)"
RUFF=${RUFF:-$(dirname "$PY")/ruff}
if [ -x "$RUFF" ]; then
  "$RUFF" check --no-cache --select E,F,W,B --line-length 125 --exclude referencia_E3 protocolo_cuantitativo auditoria \
    > "$EV/F2_ruff.txt" 2>&1 || falla F2
else echo "ruff no disponible: no se comprueba" > "$EV/F2_ruff.txt"; fi
paso "F4. calibración: plan de costo y prueba de humo (NO se ejecuta la calibración: requiere A-S1)"
{ "$PY" -I -B protocolo_cuantitativo/calibracion/calibracion_mec.py --plan
  "$PY" -I -B protocolo_cuantitativo/calibracion/calibracion_mec.py --prueba-humo
  "$PY" -I -B protocolo_cuantitativo/calibracion/calibracion_mec.py --ejecutar; echo "sin autorización: salida $?"
  sha256sum protocolo_cuantitativo/calibracion/parametros_calibracion.json; } > "$EV/F4_calibracion_plan.txt" 2>&1
paso "F5. criba de detectabilidad y tabla de δ"
"$PY" -I -B auditoria/criba_candidatas.py protocolo_cuantitativo > "$EV/F5_criba_candidatas.txt" 2>&1 || falla F5

if [ -n "$REPO" ]; then
  paso "G1–G2. estado del repositorio y huella fuerte, comparados con el inicio de la misión"
  { echo "HEAD $(git -C "$REPO" rev-parse HEAD)"; echo "rama $(git -C "$REPO" branch --show-current)"
    echo "huella porcelain: $(git -C "$REPO" status --porcelain --ignored | sha256sum)"
    echo "commits locales no publicados:"; git -C "$REPO" log --oneline origin/claude/algo-trading-simulation-platform-ngf7xo..HEAD
    echo "stash: $(git -C "$REPO" stash list | wc -l)"; } > "$EV/G1_repo_estado.txt" 2>&1
  bash "$V/pruebas/estado_repositorio.sh" "$REPO" > "$EV/G2_huella_fuerte.txt" 2>&1
  if cmp -s "$EV/G2_huella_fuerte.txt" "$EV/A2_huella_fuerte_inicial.txt"; then
    echo "huella fuerte idéntica a la inicial (A2)" >> "$EV/G1_repo_estado.txt"
  else
    diff "$EV/A2_huella_fuerte_inicial.txt" "$EV/G2_huella_fuerte.txt" >> "$EV/G1_repo_estado.txt"
    if [ -z "$(diff "$EV/A2_huella_fuerte_inicial.txt" "$EV/G2_huella_fuerte.txt" | grep '^[<>]' \
          | grep -v '!! research/hcarry_next/.venv/ metadatos:')" ]; then
      echo "DESVIACIÓN CONOCIDA I-1: la huella difiere SOLO en los metadatos de research/hcarry_next/.venv/ (un .pyc" \
        "creado por error por esta misión y revertido; queda distinto el mtime de un directorio). No se oculta:" \
        "01_RESULTADOS_AUDITORIA.md §5." >> "$EV/G1_repo_estado.txt"
      DESVIACIONES=$((DESVIACIONES + 1))
    else
      falla "la huella del repositorio cambió fuera de la desviación conocida I-1"
    fi
  fi
fi
if [ -n "$REPO" ] && [ -n "$SCRATCH" ]; then
  paso "G3–G4. inventario de entregas y originales, comparado con el inicial (A3)"
  (cd "$TMP" && "$PY" -I -B "$PAQ/auditoria/inventario_preservacion.py" "$SCRATCH" "$REPO" "$V" "$TMP/inventario.json") \
    > "$EV/G3_inventario.txt" 2>&1 || falla G3
  "$PY" -I -B - "$EV/A3_inventario_inicial.json" "$TMP/inventario.json" > "$EV/G4_inventario_comparado.txt" <<'EOF' || falla G4
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
print("inventario final == inicial (repositorio, T, T-MULTI, ZIP y manifiestos):", a == b)
for k in sorted(set(a) | set(b)):
    if a.get(k) != b.get(k):
        print("DIFIERE:", k)
sys.exit(0 if a == b else 1)
EOF
fi

paso "G5. el paquete no cambió durante su propia verificación (lógica de la etapa 13 corregida)"
if [ -f SHA256SUMS.txt ]; then
  {
    I=0
    grep -v '  evidencia/' SHA256SUMS.txt | sha256sum -c --quiet || I=1
    esp=$(find . -path ./evidencia -prune -o ! -type f ! -type d -print)
    [ -n "$esp" ] && { I=1; echo "entradas no regulares:"; echo "$esp"; }
    find . -path ./evidencia -prune -o -type f -print | sed 's|^\./||' | LC_ALL=C sort > "$TMP/pres"
    { sed 's/^[0-9a-f]*  //' SHA256SUMS.txt; echo SHA256SUMS.txt; } | LC_ALL=C sort > "$TMP/esp"
    nuevos=$(LC_ALL=C comm -23 "$TMP/pres" "$TMP/esp")
    [ -n "$nuevos" ] && { I=1; echo "archivos nuevos:"; echo "$nuevos"; }
    find . -path ./evidencia -prune -o -type d -print | sed 's|^\./||' | grep -vx '\.' | LC_ALL=C sort > "$TMP/dpres"
    { sed 's/^[0-9a-f]*  //' SHA256SUMS.txt | awk -F/ '{p = ""; for (i = 1; i < NF; i++) {p = (p == "" ? $i : p "/" $i); print p}}'
      echo evidencia; } | LC_ALL=C sort -u > "$TMP/desp"
    dn=$(LC_ALL=C comm -23 "$TMP/dpres" "$TMP/desp")
    [ -n "$dn" ] && { I=1; echo "directorios nuevos:"; echo "$dn"; }
    [ $I = 0 ] && echo "paquete intacto fuera de evidencia/: ni un byte distinto ni una entrada nueva" || echo "¡EL PAQUETE CAMBIÓ!"
  } > "$EV/G5_paquete_intacto.txt" 2>&1
  grep -q "paquete intacto" "$EV/G5_paquete_intacto.txt" || falla G5
else
  echo "sin SHA256SUMS.txt (copia de trabajo): no se comprueba" > "$EV/G5_paquete_intacto.txt"
fi
cat "$EV/G5_paquete_intacto.txt"
echo "== fin: $FALLAS fallas; $DESVIACIONES desviaciones conocidas (documentadas)"
exit $(( FALLAS > 0 ))
