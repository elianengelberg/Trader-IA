#!/usr/bin/env bash
# Reproduce las comprobaciones del paquete de revisión independiente de E3-H1/H2.
#
# Uso:   PY=python3 bash reproducir.sh <paquete>/evidencia [--mutacion]
#
# Qué hace y qué no:
#   - NO ejecuta E3-H1/H2: no llama a ningún orquestador en modo «real» con una autorización.
#   - NO contiene ni crea ninguna autorización.
#   - NO escribe en <evidencia>: todos los temporales van a $OUT (por defecto, un directorio nuevo en $TMPDIR o /tmp).
#     Al final compara la huella de <evidencia> con la del principio.
#   - Corre todo con python -B (sin .pyc) y pytest sin caché.
#   - Las verificaciones con datos (tabla, ventana, mapeos) necesitan el paquete de datos extraído sobre <evidencia>.
#     Esas verificaciones leen de las series solo `estado` y `simbolo` (y los bytes, para hashear).
#
# Variables: PY (intérprete; por defecto python3), OUT (directorio de temporales; tiene que no existir o estar vacío).
set -uo pipefail

[ $# -ge 1 ] || { echo "uso: PY=python3 bash reproducir.sh <paquete>/evidencia [--mutacion]"; exit 2; }
EV=$(cd "$1" && pwd -P) || exit 2
MUTACION=${2:-}
PY=${PY:-python3}
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
AUX="$AQUI/auxiliar.py"
OUT=${OUT:-$(mktemp -d "${TMPDIR:-/tmp}/reproduccion_E3H1H2.XXXXXX")}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd -P)
PAQ=$(cd "$EV/.." && pwd -P)
case "$OUT/" in "$PAQ"/*) echo "ABORTO: los temporales no pueden quedar dentro del paquete ($OUT)"; exit 2 ;; esac
[ -z "$(ls -A "$OUT")" ] || { echo "ABORTO: $OUT no está vacío"; exit 2; }

E3X="$EV/experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3"
REP="$EV/reparacion_E3H1H2_2026-10-26"
RV="$EV/revision_independiente_E3H1H2_2026-10-26"
CB="$EV/cierre_bloqueantes_E3H1H2_2026-10-27"
SERIES="$E3X/resultados/calidad/series"
PAGINAS="$E3X/datos_anuncios/commoncrawl/paginas"
CON_DATOS=0
[ -d "$SERIES" ] && [ -d "$PAGINAS" ] && CON_DATOS=1

RESUMEN="$OUT/RESUMEN.txt"
FALLAS=0
anotar() {  # anotar <paso> <esperado> <obtenido> <OK|FALLA|OMITIDO>
    printf '%-34s | esperado: %-44s | obtenido: %-44s | %s\n' "$1" "$2" "$3" "$4" | tee -a "$RESUMEN"
    [ "$4" = "FALLA" ] && FALLAS=$((FALLAS + 1))
    return 0
}
huella_arbol() { (cd "$1" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64); }
pytest_q() { "$PY" -B -m pytest -p no:cacheprovider -q -W ignore "$@"; }

echo "== entorno"
"$PY" -c 'import sys, numpy, pytest; print("python", sys.version.split()[0], "· numpy", numpy.__version__, "· pytest", pytest.__version__)'
echo "evidencia: $EV"
echo "temporales: $OUT"
echo "paquete de datos extraído: $([ $CON_DATOS = 1 ] && echo sí || echo no)"
HUELLA_INICIO=$(huella_arbol "$EV")
echo "huella de la evidencia al inicio: $HUELLA_INICIO"
: > "$RESUMEN"

echo; echo "== T-1 · integridad"
for par in "$REP:MANIFEST.sha256:92" "$RV:MANIFEST_REVISION.sha256:41" "$CB:MANIFEST_CIERRE.sha256:48"; do
    dir=${par%%:*}; resto=${par#*:}; man=${resto%%:*}; n=${resto#*:}
    ok=$(cd "$dir" && sha256sum -c "$man" 2>/dev/null | grep -c ': OK$')
    anotar "manifiesto $(basename "$dir")" "$n/$n OK" "$ok/$(wc -l < "$dir/$man") OK" "$([ "$ok" = "$n" ] && echo OK || echo FALLA)"
done
if [ -f "$EV/../MANIFEST_PAQUETE.sha256" ]; then
    total=$(wc -l < "$EV/../MANIFEST_PAQUETE.sha256")
    ok=$(cd "$EV/.." && sha256sum -c MANIFEST_PAQUETE.sha256 2>/dev/null | grep -c ': OK$')
    anotar "MANIFEST_PAQUETE" "todos OK" "$ok/$total OK" "$([ "$ok" = "$total" ] && echo OK || echo FALLA)"
fi
for v in "v1:$EV/experimentos/E3R_desbloqueo_2026-10-26/ejecutar_E3R.py:3b64a04d" \
         "v2:$REP/orquestador_v2/ejecutar_E3_v2.py:01fc9344" "v3:$CB/orquestador_v3/ejecutar_E3_v3.py:c089cc6a" \
         "manifiesto v3:$CB/orquestador_v3/ENTRADAS_CONGELADAS_V3.json:a89b6a23" \
         "mapeos completos:$CB/tabla/mapeos_adenda1_completa.json:bd07e7f9" "ventana A:$REP/ventana_A/ventana_A_pasada2.json:dcbd80ab"; do
    nombre=${v%%:*}; resto=${v#*:}; f=${resto%:*}; pref=${resto##*:}
    h=$(sha256sum "$f" | cut -c1-8)
    anotar "sha256 $nombre" "$pref…" "$h…" "$([ "$h" = "$pref" ] && echo OK || echo FALLA)"
done
if [ $CON_DATOS = 1 ]; then
    h=$(huella_arbol "$SERIES" | cut -c1-8)
    anotar "huella series (757)" "6506fb03…" "$h… ($(find "$SERIES" -type f | wc -l) archivos)" "$([ "$h" = 6506fb03 ] && echo OK || echo FALLA)"
    h=$(cd "$PAGINAS" && sha256sum * | sha256sum | cut -c1-8)
    anotar "huella páginas (8028)" "f12afb98…" "$h… ($(ls "$PAGINAS" | wc -l) archivos)" "$([ "$h" = f12afb98 ] && echo OK || echo FALLA)"
else
    anotar "huellas de series y páginas" "paquete de datos" "no extraído" "OMITIDO"
fi

echo; echo "== T-9 · suites (requieren el paquete de datos: algunas pruebas hashean las series reales)"
if [ $CON_DATOS = 1 ]; then
    # Suite del autor (v2), neutralizada con el conftest.py de la revisión del 2026-10-26 (sin frase ni hash reales).
    r=$(cd "$RV" && pytest_q -rxX --rootdir="$RV/copia_aislada" --confcutdir="$RV/copia_aislada" --basetemp="$OUT/tmp_autor" \
        "$RV/copia_aislada/reparacion_E3H1H2_2026-10-26/orquestador_v2/pruebas/test_orquestador_v2.py" 2>&1 | tee "$OUT/suite_autor_v2.txt" | tail -1)
    anotar "suite del autor (v2), neutralizada" "28 passed, 6 xfailed" "$(echo "$r" | sed 's/ in .*//; s/=//g; s/^ *//')" \
        "$(echo "$r" | grep -q '28 passed, 6 xfailed' && ! echo "$r" | grep -q 'failed,\|error' && echo OK || echo FALLA)"
    # Suite de la revisión (v2) y razones de los xfail.
    r=$(cd "$RV/pruebas" && pytest_q -rxX --rootdir="$RV/pruebas" --basetemp="$OUT/tmp_revision" \
        "$RV/pruebas/test_revision_adicional.py" 2>&1 | tee "$OUT/suite_revision_v2.txt" | tail -1)
    anotar "suite de la revisión (v2)" "7 passed, 10 xfailed" "$(echo "$r" | sed 's/ in .*//; s/=//g; s/^ *//')" \
        "$(echo "$r" | grep -q '7 passed, 10 xfailed' && echo OK || echo FALLA)"
    (cd "$RV/pruebas" && pytest_q --runxfail --tb=short --rootdir="$RV/pruebas" --basetemp="$OUT/tmp_revision_runxfail" \
        "$RV/pruebas/test_revision_adicional.py" 2>&1) | grep -E '^E   (AssertionError|Failed)' | LC_ALL=C sort > "$OUT/razones_xfail.txt"
    grep -E '^E   ' "$CB/pruebas/reproduccion/razones_xfail_revision_v2.txt" | LC_ALL=C sort > "$OUT/razones_xfail_esperadas.txt"
    if cmp -s "$OUT/razones_xfail.txt" "$OUT/razones_xfail_esperadas.txt"; then est=OK; else est=FALLA; fi
    anotar "razones de los 10 xfail" "las de reproduccion/razones_xfail…" "$(wc -l < "$OUT/razones_xfail.txt") razones; $([ $est = OK ] && echo iguales || echo distintas)" "$est"
    # Suite del v3.
    r=$(cd "$CB/pruebas" && pytest_q --rootdir="$CB/pruebas" --basetemp="$OUT/tmp_v3" "$CB/pruebas/test_orquestador_v3.py" 2>&1 \
        | tee "$OUT/suite_v3.txt" | tail -1)
    anotar "suite del v3" "51 passed" "$(echo "$r" | sed 's/ in .*//; s/=//g; s/^ *//')" \
        "$(echo "$r" | grep -qE '^=* *51 passed( in|$)' && echo OK || echo FALLA)"
    if [ "$MUTACION" = "--mutacion" ]; then
        "$PY" -B -I "$CB/pruebas/mutantes.py" "$CB/orquestador_v3/ejecutar_E3_v3.py" "$PY" "$OUT/mutantes" > "$OUT/mutantes.txt" 2>&1
        r=$(tail -1 "$OUT/mutantes.txt")
        anotar "mutación (15 del autor)" "mutantes: 15 · sobreviven: 0" "$r" "$([ "$r" = 'mutantes: 15 · sobreviven: 0' ] && echo OK || echo FALLA)"
    else
        anotar "mutación" "--mutacion" "no pedida" "OMITIDO"
    fi
else
    anotar "suites y mutación" "paquete de datos" "no extraído" "OMITIDO"
fi

echo; echo "== T-3, T-7 y T-8 · verificaciones con datos reales (solo textos, actividad, estado y simbolo)"
if [ $CON_DATOS = 1 ]; then
    mkdir -p "$OUT/tabla"
    "$PY" -B -I "$CB/tabla/construir_tabla.py" "$E3X" "$REP/renombres/mapeos_adenda1.json" "$OUT/tabla" > "$OUT/construir_tabla.txt" 2>&1
    for f in TABLA_RENOMBRES_COMPLETA.json mapeos_adenda1_completa.json clasificacion_barrido.json; do
        a=$(sha256sum "$CB/tabla/$f" | cut -c1-8); b=$( [ -f "$OUT/tabla/$f" ] && sha256sum "$OUT/tabla/$f" | cut -c1-8 || echo ausente)
        anotar "tabla: $f" "idéntico ($a…)" "$b…" "$([ "$a" = "$b" ] && echo OK || echo FALLA)"
    done
    "$PY" -B -I "$CB/tabla/tabla_a_markdown.py" "$OUT/tabla/TABLA_RENOMBRES_COMPLETA.json" "$OUT/tabla/clasificacion_barrido.json" \
        "$OUT/tabla/TABLA_RENOMBRES_COMPLETA.md" > /dev/null 2>&1
    a=$(sha256sum "$CB/tabla/TABLA_RENOMBRES_COMPLETA.md" | cut -c1-8); b=$(sha256sum "$OUT/tabla/TABLA_RENOMBRES_COMPLETA.md" 2>/dev/null | cut -c1-8)
    anotar "tabla: TABLA_RENOMBRES_COMPLETA.md" "idéntico ($a…)" "${b:-ausente}…" "$([ "$a" = "$b" ] && echo OK || echo FALLA)"

    "$PY" -B -I "$CB/verificaciones/ventana_tabla_completa.py" "$E3X" "$RV/verificaciones/pasada2_reproducida" \
        "$REP/segunda_pasada/eventos_omitidos.json" "$REP/segunda_pasada/resoluciones_manuales.json" \
        "$OUT/ventana_tabla_completa.json" "$CB/tabla/mapeos_adenda1_completa.json" > "$OUT/ventana_tabla_completa.txt" 2>&1
    r=$("$PY" -I "$AUX" json "$CB/verificaciones/ventana_tabla_completa.json" "$OUT/ventana_tabla_completa.json" 2>&1 | tail -1)
    v=$("$PY" -I -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["inicio"], str(d["evaluables"]) + "/" + str(d["semanas"]), "mín", d["min_elegibles"], "últ", d["ultimo_inicio_valido"], "iv′", d["iv_prima_anio"])' "$OUT/ventana_tabla_completa.json" 2>&1)
    anotar "ventana A con la tabla completa" "2023-05-15 158/158 mín 120 últ 2023-05-29 iv′ 2018" "$v" \
        "$([ "$v" = '2023-05-15 158/158 mín 120 últ 2023-05-29 iv′ 2018' ] && [ "$r" = 'json: IGUALES' ] && echo OK || echo FALLA)"
    anotar "ventana: JSON frente al del autor" "IGUALES" "${r#json: }" "$([ "$r" = 'json: IGUALES' ] && echo OK || echo FALLA)"

    "$PY" -B -I "$CB/verificaciones/mapeos_sobre_estado_real.py" "$CB/orquestador_v3/ejecutar_E3_v3.py" "$E3X" \
        "$REP/ventana_A/ventana_A_pasada2.json" "$REP" "$OUT/mapeos_sobre_estado_real.json" > "$OUT/mapeos_sobre_estado_real.txt" 2>&1
    r=$("$PY" -I "$AUX" json "$CB/verificaciones/mapeos_sobre_estado_real.json" "$OUT/mapeos_sobre_estado_real.json" 2>&1 | tail -1)
    l=$("$PY" -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["arreglos_leidos"])' "$OUT/mapeos_sobre_estado_real.json" 2>&1)
    anotar "mapeos sobre la actividad real" "JSON igual al del autor" "${r#json: }" "$([ "$r" = 'json: IGUALES' ] && echo OK || echo FALLA)"
    anotar "arreglos leídos de las series" "['estado', 'simbolo']" "$l" "$([ "$l" = "['estado', 'simbolo']" ] && echo OK || echo FALLA)"
else
    anotar "verificaciones con datos" "paquete de datos" "no extraído" "OMITIDO"
fi

echo; echo "== T-10 · higiene de autorizaciones (temporales y evidencia)"
"$PY" -I "$AUX" higiene "$EV" "$OUT" > "$OUT/higiene.txt" 2>&1; rc=$?
cat "$OUT/higiene.txt"
anotar "higiene de frases" "0 fallas" "$(tail -1 "$OUT/higiene.txt" | sed 's/.*fallas: /fallas: /')" "$([ $rc = 0 ] && echo OK || echo FALLA)"
n=$(find "$EV" -name 'INTENTOS_E3.jsonl' | wc -l)  # en $OUT sí hay: los crean las pruebas, con frases de prueba
anotar "registros de intentos en la evidencia" "ninguno" "$n" "$([ "$n" = 0 ] && echo OK || echo FALLA)"

echo; echo "== evidencia sin modificar"
n=$(find "$EV" \( -name '__pycache__' -o -name '.pytest_cache' -o -name '*.pyc' \) | wc -l)
anotar "cachés en la evidencia" "ninguna" "$n" "$([ "$n" = 0 ] && echo OK || echo FALLA)"
HUELLA_FIN=$(huella_arbol "$EV")
anotar "huella de la evidencia" "${HUELLA_INICIO:0:16}…" "${HUELLA_FIN:0:16}…" "$([ "$HUELLA_INICIO" = "$HUELLA_FIN" ] && echo OK || echo FALLA)"

echo; echo "== RESUMEN ($RESUMEN)"
cat "$RESUMEN"
echo "fallas: $FALLAS"
echo "Los temporales quedan en $OUT para inspección. Contienen copias del código de los mutantes (con la FRASE del v3, como el"
echo "código original), pero ninguna autorización. Borralos cuando termines."
echo "Que todo dé OK no prueba que esté bien: es el punto de partida de la revisión."
[ $FALLAS = 0 ]
