#!/usr/bin/env bash
# Prueba de equivalencia de extremo a extremo, en una COPIA con parámetros reducidos y otra semilla (no es la
# calibración): el orquestador debe producir una salida idéntica byte a byte a la del script congelado ejecutado de
# forma secuencial, también tras reanudar, y debe negarse a sobrescribir. El verificador debe detectar un valor p
# alterado.
# Uso: bash prueba_extremo_a_extremo.sh <paquete_r1> <directorio_nuevo>
set -euo pipefail
PAQ=$1
T=$2
ORQ=$(cd "$(dirname "$0")" && pwd)
[ ! -e "$T" ] || { echo "ya existe $T"; exit 1; }
mkdir -p "$T"
cp -r "$PAQ/protocolo_cuantitativo" "$T/"
cp "$PAQ/SHA256SUMS.txt" "$T/"
export PYTHONDONTWRITEBYTECODE=1
cd "$T"
python3 -B -I - <<'EOF'
import json, pathlib
p = pathlib.Path("protocolo_cuantitativo/calibracion/parametros_calibracion.json")
d = json.loads(p.read_text())
d.update(replicas=20, B=99, semilla=1, tamanos=[80, 160])
d["fuente"] = "COPIA DE PRUEBA, NO ES LA CALIBRACION"
p.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
EOF
cat > correr.py <<'EOF'
import importlib.util, pathlib, sys
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("orq", sys.argv[1])
orq = importlib.util.module_from_spec(spec)
sys.modules["orq"] = orq
spec.loader.exec_module(orq)
orq._verificar = lambda paq: {"prueba": True}  # solo en esta copia: sus parámetros no son los congelados
sys.exit(orq.ejecutar(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), "PRUEBA", 4))
EOF
python3 -B -I protocolo_cuantitativo/calibracion/calibracion_mec.py --ejecutar --autorizacion PRUEBA --salida original.json
python3 -B -I correr.py "$ORQ/orquestar_calibracion.py" "$T" "$T/sal" > /dev/null
cmp original.json sal/resultado_calibracion.json && echo "1. IDENTICO: orquestador == script congelado secuencial ($(sha256sum < original.json | cut -c1-16)…)"
rm sal/celdas/respaldo_C4_n160.json sal/resultado_calibracion.json
python3 -B -I correr.py "$ORQ/orquestar_calibracion.py" "$T" "$T/sal" > reanudar.log
cmp original.json sal/resultado_calibracion.json && echo "2. IDENTICO tras borrar una celda y reanudar ($(head -1 reanudar.log))"
if python3 -B -I correr.py "$ORQ/orquestar_calibracion.py" "$T" "$T/sal" > sobrescribir.log 2>&1; then
  echo "3. FALLA: sobrescribió"; exit 1
fi
cmp original.json sal/resultado_calibracion.json && echo "3. se niega a sobrescribir: $(tail -1 sobrescribir.log | cut -c1-30)…"
python3 -B -I "$ORQ/verificar_calibracion.py" "$T" "$T/sal" "$T/verif" > verif.log
echo "4. verificador sobre la copia de prueba: sin fallas"
cp -r sal sal_mal
python3 -B -I - sal_mal/celdas/primaria_C3_n80.json <<'EOF'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
r = next(i for i, (pv, g) in enumerate(d["replicas"]) if pv > 0.05)
d["replicas"][r][0] = 0.001
open(p, "w").write(json.dumps(d) + "\n")
EOF
if python3 -B -I "$ORQ/verificar_calibracion.py" "$T" "$T/sal_mal" "$T/verif_mal" > verif_mal.log 2>&1; then
  echo "5. FALLA: el verificador no detectó la alteración"; exit 1
fi
echo "5. el verificador detecta un valor p alterado: $(python3 -B -I -c "import json,sys;print(json.load(open(sys.argv[1]))['fallas_de_verificacion'])" verif_mal/verificacion.json)"
[ -z "$(find "$T" -name __pycache__)" ] && echo "6. sin __pycache__"
