#!/usr/bin/env bash
# Reproduce TODA la evidencia de este paquete (v0.5). Solo lectura sobre el repositorio (verifica que su estado de git
# no cambia); no ejecuta T, no lee bytes de datos de mercado, no usa la red. Variables:
#   REPO  raíz del repositorio (por defecto /home/user/Trader-IA)      PY   intérprete con pytest
#   PY_CRYPTOGRAPHY  intérprete con la biblioteca cryptography para la prueba diferencial (si falta, se omite)
# Los paquetes v0.3 y v0.4 se extraen de 00_preservado/ a un temporal y se verifican con sus SHA256SUMS.
set -u
PAQ="$(cd "$(dirname "$0")" && pwd)"
REPO=${REPO:-/home/user/Trader-IA}
PY=${PY:-$REPO/research/hcarry_next/.venv/bin/python}
RUFF=${RUFF:-$(dirname "$PY")/ruff}
T="$REPO/research/tendencia_btc"
EVID="$PAQ/evidencia"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$T/src:$REPO/research/hcarry_next/src"
export TMPDIR=${TMPDIR:-$(dirname "$PAQ")}
mkdir -p "$EVID"
cd "$PAQ"
ultima() { tail -n 1 "$1"; }

# Huella del repositorio en solo lectura: refs, estado, CONTENIDO de los cambios sin commit y de los archivos de texto sin
# seguimiento, y METADATOS (sin leer bytes) de los directorios de datos. La última línea es la huella del estado.
estado_git() { bash "$PAQ/pruebas/estado_repositorio.sh" "$REPO"; }
estado_git > "$EVID/90_estado_git_antes.txt"
echo "== $(date -u +%FT%TZ) inicio; estado git: $(tail -1 "$EVID/90_estado_git_antes.txt")"

echo "== 0. paquetes anteriores extraídos de 00_preservado y verificados"
PREV=$(mktemp -d)
trap 'rm -rf "$PREV"' EXIT
(cd "$PREV" && unzip -q "$PAQ/00_preservado/CIERRE_FINAL_P1_P2_P4_2026-10-20.zip" \
  && unzip -q "$PAQ/00_preservado/SOLUCION_VERIFICADA_P1_P2_P4_2026-10-20.zip")
V03="$PREV/cierre_final_P1_P2_P4_2026-10-20"; V04="$PREV/solucion_verificada_P1_P2_P4_2026-10-20"
{ (cd "$V03" && sha256sum -c --quiet SHA256SUMS.txt && echo "v0.3 extraído: SHA256SUMS OK")
  (cd "$V04" && sha256sum -c --quiet SHA256SUMS.txt && echo "v0.4 extraído: SHA256SUMS OK"); } | tee "$EVID/01_paquetes_previos_extraidos.txt"

echo "== 1. estilo (ruff, mismas reglas que v0.3 y v0.4)"
"$RUFF" check --no-cache --select E,F,W,B --line-length 125 codigo/verificacion > "$EVID/12_ruff.txt" 2>&1
echo "código de salida: $?" >> "$EVID/12_ruff.txt"; tail -2 "$EVID/12_ruff.txt"

echo "== 2. suite completa de v0.5 (unitarias, oráculos, fuzzing, concurrencia, fallos, corte de energía, contrato, cruzada, ejecutor, regresión portada)"
mkdir -p "$EVID/14_corte_energia"
(cd pruebas && EVIDENCIA_P4_CORTE="$EVID/14_corte_energia/corte.json" "$PY" -B -m pytest -p no:cacheprovider -q -rs \
  p1 p2 p4 cruzada integracion regresion/p1_v0_3_portadas > "$EVID/11_suite_v0_5.txt" 2>&1; \
  echo "código de salida de pytest: $?" >> "$EVID/11_suite_v0_5.txt")
mkdir -p "$EVID/14_corte_energia"
grep -E "passed|failed" "$EVID/11_suite_v0_5.txt" | tail -1

echo "== 3. matriz antes/después (las mismas pruebas de defectos contra v0.2, v0.3, v0.4 y v0.5)"
EVIDENCIA_P4_FALLOS="$EVID/10_matriz_antes_despues/fallos_es.json" "$PY" -B pruebas/matriz_antes_despues.py \
  "$EVID/10_matriz_antes_despues" > "$EVID/10_matriz_resumen.txt" 2>&1; echo "código de salida: $?" >> "$EVID/10_matriz_resumen.txt"
grep -c "| sí |" "$EVID/10_matriz_antes_despues/MATRIZ_ANTES_DESPUES.md" | sed 's/^/filas que cumplen el patrón: /'
grep -c "\*\*NO\*\*" "$EVID/10_matriz_antes_despues/MATRIZ_ANTES_DESPUES.md" | sed 's/^/filas que NO lo cumplen: /'

echo "== 4. estabilidad: P4, cruzada y ejecutor repetidos 3 veces"
: > "$EVID/13_repeticiones.txt"
for i in 1 2 3; do (cd pruebas && "$PY" -B -m pytest -p no:cacheprovider -q p4 cruzada integracion 2>&1 | tail -1 | sed "s/^/corrida $i: /") >> "$EVID/13_repeticiones.txt"; done
cat "$EVID/13_repeticiones.txt"

echo "== 5. prueba de las pruebas (mutaciones)"
"$PY" -B pruebas/p2/mutacion_p2.py codigo/verificacion "$EVID/31_p2_mutaciones_oraculo.txt" > /dev/null; ultima "$EVID/31_p2_mutaciones_oraculo.txt"
"$PY" -B pruebas/mutacion_cruzada.py codigo/verificacion "$EVID/52_cruzada_mutaciones.txt" > /dev/null; ultima "$EVID/52_cruzada_mutaciones.txt"
"$PY" -B pruebas/p4/mutacion_durabilidad.py codigo/verificacion "$EVID/53_durabilidad_mutaciones.txt" > /dev/null; ultima "$EVID/53_durabilidad_mutaciones.txt"
"$PY" -B pruebas/integracion/mutacion_ejecutor.py codigo/verificacion "$EVID/54_ejecutor_mutaciones.txt" > /dev/null; ultima "$EVID/54_ejecutor_mutaciones.txt"

echo "== 6. regresiones: suites de v0.3 y de v0.4 sin modificar contra v0.5; sondas de v0.2"
PAQ="$PAQ" V03="$V03" V04="$V04" PY="$PY" EVID="$EVID" bash pruebas/regresion/ejecutar_regresiones.sh

echo "== 7. sondas directas de los defectos de v0.4 (fuera de pytest) contra v0.4 y v0.5"
PY="$PY" EVID="$EVID" PAQ="$PAQ" bash pruebas/sondas_v0_4/ejecutar_sondas.sh

echo "== 8. tabla de decisión de P2"
"$PY" -B pruebas/p2/generar_tabla.py tablas > "$EVID/32_p2_tabla_resumen.txt"; sed -n 3,5p "$EVID/32_p2_tabla_resumen.txt"

echo "== 9. Ed25519 contra cryptography/OpenSSL (prueba diferencial; salida detallada)"
(cd pruebas && "$PY" -B -m pytest -p no:cacheprovider -q -s -rs p1/test_confianza_diferencial.py > "$EVID/70_ed25519_diferencial.txt" 2>&1); tail -1 "$EVID/70_ed25519_diferencial.txt"

echo "== 10. trazabilidad de T: regenerada en un temporal y comparada (salvo fechas de generación)"
TT=$(mktemp -d)
"$PY" -I -B trazabilidad_T/generar_trazabilidad.py "$REPO" "$TT" > /dev/null
"$PY" -I -B - "$TT" trazabilidad_T > "$EVID/05_trazabilidad_regenerada.txt" <<'EOF'
import json, sys
from pathlib import Path
nuevo, guardado = Path(sys.argv[1]), Path(sys.argv[2])
a = json.loads((nuevo / "TRAZABILIDAD_FUERA_DE_MUESTRA_T.json").read_text())
b = json.loads((guardado / "TRAZABILIDAD_FUERA_DE_MUESTRA_T.json").read_text())
for x in (a, b):
    x.pop("generado_utc"); x.pop("cronologia_transcripcion_local")
print("trazabilidad (artefactos, git, límites) idéntica a la guardada:", a == b)
print("manifiesto idéntico:", (nuevo / "ARTEFACTOS_FUERA_DE_MUESTRA_T_SHA256.txt").read_bytes()
      == (guardado / "ARTEFACTOS_FUERA_DE_MUESTRA_T_SHA256.txt").read_bytes())
EOF
rm -rf "$TT"; cat "$EVID/05_trazabilidad_regenerada.txt"

echo "== 10b. estado REAL de T en seis dimensiones separadas (solo lectura; sin bytes de datos de mercado)"
"$PY" -I -B trazabilidad_T/evaluar_T_real.py "$REPO" "$PAQ" "$EVID/80_estado_real_de_T.json"

echo "== 11. parches versionados v0.5: construcción y comprobación sobre HEAD y origin exportados"
"$PY" -B parches/construir_y_comprobar.py "$PAQ" "$REPO" "$PY" "$EVID"

echo "== 12. integridad de las entregas anteriores y de los artefactos congelados de T"
{
  (cd 00_preservado && sha256sum -c ../evidencia/00_preservacion_relativa.txt)
  (cd "$T" && sha256sum experimentos/fuera_de_muestra_T.json experimentos/fuera_de_muestra_T.py PRERREGISTRO_FUERA_DE_MUESTRA_T.md experimentos/calidad_datos.json)
} > "$EVID/98_integridad_final.txt" 2>&1; cat "$EVID/98_integridad_final.txt"

echo "== 13. el paquete no cambió durante la ejecución: fuera de evidencia/, ni un byte distinto ni una entrada nueva"
INTACTO=0
if [ -f SHA256SUMS.txt ]; then
  {
    grep -v '  evidencia/' SHA256SUMS.txt | sha256sum -c --quiet || INTACTO=1
    echo "archivos fuera de evidencia/ comprobados contra SHA256SUMS.txt: $(grep -vc '  evidencia/' SHA256SUMS.txt)"
    # v0.5.1 (D-1): sha256sum sigue los enlaces, y find -type f no los lista: una entrada que no es archivo regular ni
    # directorio (enlace simbólico, FIFO, socket) es siempre un cambio, aunque apunte a un contenido idéntico.
    especiales=$(find . -path ./evidencia -prune -o ! -type f ! -type d -print | sed 's|^\./||' | LC_ALL=C sort)
    if [ -n "$especiales" ]; then INTACTO=1; echo "entradas que no son archivos regulares (p. ej. enlaces):"; echo "$especiales"; fi
    find . -path ./evidencia -prune -o -type f -print | sed 's|^\./||' | LC_ALL=C sort > "$PREV/presentes"
    { sed 's/^[0-9a-f]*  //' SHA256SUMS.txt; echo SHA256SUMS.txt; } | LC_ALL=C sort > "$PREV/esperados"
    nuevos=$(LC_ALL=C comm -23 "$PREV/presentes" "$PREV/esperados")
    if [ -n "$nuevos" ]; then INTACTO=1; echo "archivos NUEVOS fuera de evidencia/:"; echo "$nuevos"; fi
    # v0.5.1 (D-1): los únicos directorios admitidos son los que contienen archivos del manifiesto, y evidencia/
    find . -path ./evidencia -prune -o -type d -print | sed 's|^\./||' | grep -vx '\.' | LC_ALL=C sort > "$PREV/dirs_presentes"
    { sed 's/^[0-9a-f]*  //' SHA256SUMS.txt | awk -F/ '{p = ""; for (i = 1; i < NF; i++) {p = (p == "" ? $i : p "/" $i); print p}}'
      echo evidencia; } | LC_ALL=C sort -u > "$PREV/dirs_esperados"
    dnuevos=$(LC_ALL=C comm -23 "$PREV/dirs_presentes" "$PREV/dirs_esperados")
    if [ -n "$dnuevos" ]; then INTACTO=1; echo "directorios NUEVOS fuera de evidencia/:"; echo "$dnuevos"; fi
    [ $INTACTO = 0 ] && echo "paquete intacto: sin cambios ni entradas nuevas (archivos, enlaces ni directorios)" || echo "¡EL PAQUETE CAMBIÓ!"
  } > "$EVID/97_paquete_intacto.txt" 2>&1
else
  echo "sin SHA256SUMS.txt (copia de trabajo sin empaquetar): no se comprueba" > "$EVID/97_paquete_intacto.txt"
fi
cat "$EVID/97_paquete_intacto.txt"

estado_git > "$EVID/91_estado_git_despues.txt"
if cmp -s "$EVID/90_estado_git_antes.txt" "$EVID/91_estado_git_despues.txt"; then
  echo "== estado git intacto: $(tail -1 "$EVID/91_estado_git_despues.txt")" | tee "$EVID/99_estado_git_comparado.txt"
else
  echo "== ¡EL ESTADO GIT CAMBIÓ!" | tee "$EVID/99_estado_git_comparado.txt"; exit 1
fi
[ $INTACTO = 0 ] || exit 1
echo "== $(date -u +%FT%TZ) fin"
