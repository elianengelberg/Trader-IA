#!/usr/bin/env bash
# Reproduce la calibración A-S1 desde el ZIP r1 y la compara byte a byte con la empaquetada. Las réplicas son
# deterministas: reproducir no es una segunda calibración ni permite elegir resultados. Dura ≈ 1–1,5 h con 4 núcleos.
# Uso: R1_ZIP=<CIERRE_AUDITORIA_v0.5_Y_PLAN_CUANTITATIVO_r1_2026-10-21.zip> bash orquestador/reproducir.sh <dir_nuevo>
set -euo pipefail
ESPERADO=a8056ced047c89d5b6dd96c688d6927373ef474fb408ee25cb4eee3b72cc1a7d
D=$1
AQUI=$(cd "$(dirname "$0")/.." && pwd)
export PYTHONDONTWRITEBYTECODE=1
[ "$(sha256sum < "$R1_ZIP" | cut -d' ' -f1)" = "$ESPERADO" ] || { echo "el ZIP r1 no es el esperado"; exit 1; }
[ ! -e "$D" ] || { echo "ya existe $D"; exit 1; }
mkdir -p "$D/r1"
unzip -q "$R1_ZIP" -d "$D/r1"
P="$D/r1/cierre_auditoria_v0.5_y_plan_cuantitativo_r1_2026-10-21"
(cd "$P" && sha256sum -c --quiet SHA256SUMS.txt)
REF=$(python3 -B -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["autorizacion"])' "$AQUI/salida/resultado_calibracion.json")
python3 -B -I "$AQUI/orquestador/orquestar_calibracion.py" "$P" "$D/salida" --autorizacion "$REF" --procesos "${PROCESOS:-4}"
cmp "$AQUI/salida/resultado_calibracion.json" "$D/salida/resultado_calibracion.json"
for f in "$AQUI"/salida/celdas/*.json; do cmp "$f" "$D/salida/celdas/$(basename "$f")"; done
echo "IDENTICO: salida y 48 celdas"
python3 -B -I "$AQUI/orquestador/verificar_calibracion.py" "$P" "$D/salida" "$D/verificacion"
