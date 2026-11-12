#!/usr/bin/env bash
# Reproduce SIM-1 desde una extracción limpia del paquete.
#
# Requisitos: Python 3.11, git, curl, red hacia data.binance.vision y pypi.org, y un clon de Trader-IA que contenga 72ffae5.
# Uso:  bash reproduccion/REPRODUCIR.sh <clon_de_Trader-IA> <dir_de_trabajo_nuevo> [rapido]
#   rapido: solo datos, suite de pruebas del motor, paridad P3 y verificación sintética (≈ 30 min);
#           sin «rapido» corre también DEV y OOS completos (≈ 3 h con 4 núcleos).
# El paquete NO trae datos crudos de terceros: se descargan de la fuente oficial y se verifican byte a byte.
set -euo pipefail
PKG="$(cd "$(dirname "$0")/.." && pwd)"; REPO="$1"; W="$2"; MODO="${3:-completo}"
[[ -e "$W" ]] && { echo "$W ya existe: usá un directorio nuevo"; exit 1; }
mkdir -p "$W"; cd "$W"

echo "== 1. tia en 72ffae5 + parche D1–D3"
git clone -q "$REPO" trader-ia && git -C trader-ia checkout -q 72ffae5d2698440c8f1afaff12e07bd8adde66fb
git -C trader-ia apply "$PKG/parche/parche_motor_D1_D3.diff"
cp "$PKG/parche/test_backtest_order_hygiene.py" trader-ia/tests/unit/
sha256sum trader-ia/packages/tia/src/tia/backtest/engine.py trader-ia/packages/tia/src/tia/execution/paper.py

echo "== 2. entorno (requisitos de E1 con hash)"
python3.11 -m venv venv
venv/bin/pip install -q --require-hashes -r "$PKG/E1/requisitos_con_hash.txt"
# entorno aparte solo para pytest (el de E1 no lo trae; el de la simulación queda exactamente con los hashes de E1)
python3.11 -m venv venv_pruebas
venv_pruebas/bin/pip install -q --require-hashes -r "$PKG/E1/requisitos_con_hash.txt" && venv_pruebas/bin/pip install -q pytest httpx websockets  # tests/conftest.py los importa en su fixture de red

echo "== 3. datos oficiales (228 ZIP, doble verificación)"
mkdir -p mision/datos/vision mision/codigo mision/registro mision/resultados mision/evidencia
bash "$PKG/reproduccion/descargar_todo.sh" mision/datos/vision
cp "$PKG"/codigo/*.py "$PKG"/codigo/*.sh mision/codigo/
mkdir -p E1codigo && cp "$PKG"/E1/e1.py "$PKG"/E1/e1_comun.py E1codigo/
PY="$W/venv/bin/python"; export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$W/trader-ia/packages/tia/src:$W/E1codigo:$W/mision/codigo"

echo "== 4. pruebas de regresión D1–D3 (deben pasar 4)"
( cd trader-ia && "$W/venv_pruebas/bin/python" -B -m pytest -c /dev/null --rootdir . -q -p no:cacheprovider \
    tests/unit/test_backtest_order_hygiene.py )

echo "== 5. calidad de datos y comparación con la registrada"
( cd mision/codigo && "$PY" -B calidad_datos.py ../resultados/calidad_datos.json ../datos/vision )
python3 - "$PKG/resultados/calidad_datos.json" mision/resultados/calidad_datos.json <<'PY'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:])
claves = ("velas", "faltantes", "primera_vela", "ultima_vela", "ohlc_incoherentes", "horas_en_conflicto_excluidas")
ok = all(a[s][k] == b[s][k] for s in a for k in claves)
print("calidad idéntica a la registrada:", ok); sys.exit(0 if ok else 1)
PY

echo "== 6. verificación sintética del motor (V1, V2, V3, V6, DET)"
( cd mision/codigo && "$PY" -B verificacion_motor.py ../evidencia/verificacion_sintetica.json 4 )

if [[ "$MODO" == "rapido" ]]; then echo "modo rápido: fin"; exit 0; fi

echo "== 7. DEV completo y comparación de huellas de operaciones"
( cd mision/codigo && SIM1_PROCESOS=4 "$PY" -B sim1.py dev ../resultados/dev )
echo "== 8. OOS-ETH (una lectura en ESTE directorio; el candado vive en mision/registro)"
( cd mision/codigo && SIM1_PROCESOS=4 "$PY" -B sim1.py final ../resultados/final ../resultados/dev/m1_promocion.json )
python3 - "$PKG/resultados" mision/resultados <<'PY'
import json, sys, hashlib
from pathlib import Path
a, b = Path(sys.argv[1]), Path(sys.argv[2])
ok = True
# el orden de las claves depende de qué proceso termina primero: se compara el contenido canónico
canon = lambda p: hashlib.sha256(json.dumps(json.load(open(p)), sort_keys=True).encode()).hexdigest()  # noqa: E731
for f in ("dev/operaciones_dev.json", "final/operaciones_oos.json", "dev/m1_promocion.json"):
    ha, hb = canon(a / f), canon(b / f)
    print(f, "IDÉNTICO" if ha == hb else "DISTINTO", ha[:16], hb[:16]); ok &= ha == hb
sys.exit(0 if ok else 1)
PY
echo "REPRODUCCIÓN COMPLETA: operaciones DEV, OOS y regla M1 idénticas (contenido canónico)"
