#!/usr/bin/env bash
# Verificación del paquete desde una extracción limpia. No usa datos de mercado, no toca ningún repositorio y no
# modifica el paquete: todo lo que genera va a <dir_trabajo>.
#
# Uso:
#   R1_ZIP=<CIERRE_AUDITORIA_v0.5_Y_PLAN_CUANTITATIVO_r1_2026-10-21.zip> \
#   AS1_ZIP=<CALIBRACION_AS1_PEC-1.0_2026-10-21.zip> \
#   [PY=<python con pytest>] [REEJECUTAR_SEC=1] [REEJECUTAR_AS1=1] bash verificar.sh <dir_trabajo_nuevo>
#
# Por defecto (≈ 20–40 min con 1 núcleo): integridad; recuento de A-S1; dependencia entre celdas; consecuencias de δ;
# reanálisis de SEC-1.0 desde sus datos crudos (con 234 trayectorias recalculadas con la regla completa);
# correspondencia entre PEC-1.1 y SEC-1.0; pruebas de PEC-1.1.
# REEJECUTAR_SEC=1 vuelve a simular SEC-1.0 entero (≈ 1,6 h con 4 núcleos) y lo compara byte a byte.
# REEJECUTAR_AS1=1 vuelve a ejecutar A-S1 con su propio reproducir.sh (≈ 30–50 min con 4 núcleos).
set -uo pipefail
AQUI=$(cd "$(dirname "$0")" && pwd)
D=${1:?falta el directorio de trabajo}
PY=${PY:-python3}
export PYTHONDONTWRITEBYTECODE=1
FALLAS=0
ok()    { echo "  OK  $*"; }
falla() { echo "  FALLA  $*"; FALLAS=$((FALLAS + 1)); }
paso()  { echo "== $*"; }
[ ! -e "$D" ] || { echo "ya existe $D"; exit 2; }
mkdir -p "$D"

paso "0. integridad del paquete"
(cd "$AQUI" && sha256sum -c --quiet SHA256SUMS.txt) && ok "SHA256SUMS.txt" || falla "SHA256SUMS.txt"
[ -z "$(find "$AQUI" -name __pycache__ -o -name '*.pyc')" ] && ok "sin __pycache__" || falla "__pycache__ en el paquete"

paso "1. ZIP de entrada (por SHA-256 completo) y extracción limpia"
[ "$(sha256sum < "${R1_ZIP:?falta R1_ZIP}" | cut -d' ' -f1)" = a8056ced047c89d5b6dd96c688d6927373ef474fb408ee25cb4eee3b72cc1a7d ] \
  && ok "r1" || { falla "r1 no es el esperado"; exit 1; }
[ "$(sha256sum < "${AS1_ZIP:?falta AS1_ZIP}" | cut -d' ' -f1)" = 37af592c865dd0379d71fad2f6b52033c019e13b20920557867c6d93548f64e6 ] \
  && ok "A-S1" || { falla "A-S1 no es el esperado"; exit 1; }
unzip -q "$R1_ZIP" -d "$D/r1" && unzip -q "$AS1_ZIP" -d "$D/a_s1"
R1="$D/r1/cierre_auditoria_v0.5_y_plan_cuantitativo_r1_2026-10-21"
A="$D/a_s1/calibracion_AS1_PEC-1.0_2026-10-21"
(cd "$R1" && sha256sum -c --quiet SHA256SUMS.txt) && ok "r1: 80 archivos" || falla "r1 extraído"
(cd "$A" && sha256sum -c --quiet SHA256SUMS.txt) && ok "A-S1: 70 archivos" || falla "A-S1 extraído"

paso "2. fase 1: recuento de A-S1, dependencia entre celdas"
python3 -B -I "$AQUI/codigo/f1/recuento_a_s1.py" "$A" "$R1" > "$D/F1_recuento.json" \
  && cmp -s "$D/F1_recuento.json" "$AQUI/evidencia/F1_recuento_a_s1.json" && ok "recuento idéntico" || falla "recuento"
python3 -B -I "$AQUI/codigo/f1/dependencia_entre_celdas.py" "$R1" > "$D/F1_dep.json" \
  && cmp -s "$D/F1_dep.json" "$AQUI/evidencia/F1_dependencia_entre_celdas.json" && ok "dependencia idéntica" || falla "dependencia"

paso "3. fase 2: consecuencias de δ"
python3 -B -I "$AQUI/codigo/f2/consecuencias_delta.py" "$R1" > "$D/F2.json" \
  && cmp -s "$D/F2.json" "$AQUI/evidencia/F2_consecuencias_delta.json" && ok "tabla de δ idéntica" || falla "δ"

paso "4. fase 3: huellas previas y reanálisis de SEC-1.0 desde los datos crudos empaquetados"
(cd "$AQUI" && sha256sum -c --quiet registro/f3_huellas_previas.txt) && ok "especificación, código y nota previa sin cambios" \
  || falla "huellas previas"
python3 -B -I "$AQUI/codigo/f3/analizar_secuencial.py" "$R1" "$AQUI/codigo/f3/especificacion_CONFIRMATORIA.json" \
  "$AQUI/sec_1_0" "$D/sec_analisis" > "$D/sec_analisis.log" 2>&1 \
  && cmp -s "$D/sec_analisis/resultado_secuencial.json" "$AQUI/sec_1_0/analisis/resultado_secuencial.json" \
  && ok "resultado idéntico; $(tail -1 "$D/sec_analisis.log")" || falla "reanálisis de SEC-1.0"

paso "5. PEC-1.1: el código calibrado y los umbrales son los de SEC-1.0"
(cd "$AQUI/protocolo_cuantitativo_PEC-1.1" && python3 -B -I - "$AQUI/sec_1_0/celdas" <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, ".")
from pec import prospectiva as P
for n in (1096, 1461, 1826):
    u = json.loads((Path(sys.argv[1]) / f"H0_C1_N{n}.json").read_text())["umbrales"]
    p = P.plan_de_miradas(n)
    assert (u["n_k"], u["c_k"], u["a_k"], u["t_k"]) == (p["n_k"], p["c_k"], p["a_k"], p["t_k"]), n
print("umbrales de PEC-1.1 = umbrales almacenados por SEC-1.0 (n_max 1096, 1461, 1826)")
EOF
) && ok "correspondencia PEC-1.1 ↔ SEC-1.0" || falla "correspondencia PEC-1.1 ↔ SEC-1.0"
for f in inferencia sintetico secuencial; do
  cmp -s "$AQUI/protocolo_cuantitativo_PEC-1.1/pec/$f.py" "$R1/protocolo_cuantitativo/pec/$f.py" \
    && ok "pec/$f.py idéntico al de r1" || falla "pec/$f.py distinto de r1"
done

paso "6. pruebas de PEC-1.1"
if "$PY" -c "import pytest" 2>/dev/null; then
  cp -r "$AQUI/protocolo_cuantitativo_PEC-1.1" "$D/pec11_pruebas"
  (cd "$D/pec11_pruebas/pruebas" && "$PY" -B -m pytest -p no:cacheprovider -q) > "$D/pruebas.log" 2>&1 \
    && ok "$(tail -1 "$D/pruebas.log")" || falla "pruebas: $(tail -1 "$D/pruebas.log")"
else
  echo "  --  $PY no tiene pytest: pruebas NO ejecutadas (definí PY)"
fi

if [ "${REEJECUTAR_SEC:-0}" = 1 ]; then
  paso "7. reejecución completa de SEC-1.0"
  python3 -B -I "$AQUI/codigo/f3/secuencial_mc.py" "$R1" "$AQUI/codigo/f3/especificacion_CONFIRMATORIA.json" "$D/sec_1_0" \
    --procesos "${PROCESOS:-4}" > "$D/sec_1_0.log" 2>&1
  n=0; for f in "$AQUI"/sec_1_0/celdas/*.json; do cmp -s "$f" "$D/sec_1_0/celdas/$(basename "$f")" && n=$((n + 1)); done
  [ "$n" = 24 ] && ok "24 / 24 celdas idénticas byte a byte" || falla "solo $n / 24 celdas idénticas"
fi
if [ "${REEJECUTAR_AS1:-0}" = 1 ]; then
  paso "8. reejecución completa de A-S1"
  R1_ZIP="$R1_ZIP" bash "$A/orquestador/reproducir.sh" "$D/a_s1_reproduccion" > "$D/a_s1_reproduccion.log" 2>&1 \
    && ok "A-S1 idéntico (salida y 48 celdas)" || falla "reejecución de A-S1"
fi

paso "9. el paquete no cambió durante su verificación"
(cd "$AQUI" && sha256sum -c --quiet SHA256SUMS.txt) && ok "intacto" || falla "el paquete cambió"
[ -z "$(find "$AQUI" -name __pycache__ -o -name '*.pyc')" ] && ok "sin __pycache__" || falla "__pycache__"
echo "== fin: $FALLAS fallas"
exit $((FALLAS > 0))
