# Comandos para repetir las comprobaciones (v3)

Todo corre en directorios nuevos. Ningún comando escribe en el repositorio de origen, hace commits o push, ni despliega.

## 0. Integridad
```bash
sha256sum -c entrega_integracion_D1_D3_v3r2_2026-10-22.zip.sha256           # junto al ZIP
mkdir /ruta/nueva && unzip -q <ZIP> -d /ruta/nueva && cd /ruta/nueva/entrega_integracion_D1_D3_v3r2_2026-10-22
sha256sum -c SHA256SUMS
```

## 1. Todo de una vez
```bash
env -i PATH=/usr/bin:/bin HOME=/tmp/h LANG=C.UTF-8 <variables de red del proxy, si las hay> \
  bash reproducir.sh /home/user/Trader-IA /ruta/trabajo/nueva completo <scratchpad>/experimentos/E1_bot_datos_reales_2026-10-19/codigo
# rapido ≈ 20 min · completo ≈ 55 min · el último argumento (código de E1) es opcional y agrega la paridad
```

## 2. Comprobaciones puntuales
```bash
B=72ffae5d2698440c8f1afaff12e07bd8adde66fb; E=<extracción>; W=<trabajo nuevo>
git clone --no-local /home/user/Trader-IA $W/a && cd $W/a && git checkout --detach $B
git apply $E/parches/01_*.patch && git apply $E/parches/02v3_*.patch && sha256sum -c $E/parches/SHA256_archivos_resultantes_obligatoria_v3.txt
python3.11 -m venv $W/v && $W/v/bin/pip install -c $E/entorno/ci-py311.txt -e ".[api,db,postgres,redis,llm,dev]"
# defecto del 02 original frente al 02v3 (sonda; solo SQLite temporal):
$W/v/bin/python -I -B $E/herramientas/sonda_misma_procedencia.py $W/a /tmp            # → «segundo guardado: RECHAZADO»
# compatibilidad histórica con las API reales (base escribe, integrada escribe, base vuelve a leer):
$W/v/bin/python -I -B $E/herramientas/compat_historica.py <árbol 72ffae5> /tmp/c.db 1.json correr
$W/v/bin/python -I -B $E/herramientas/compat_historica.py $W/a /tmp/c.db 2.json correr
$W/v/bin/python -I -B $E/herramientas/compat_historica.py <árbol 72ffae5> /tmp/c.db 3.json
# cobertura de la procedencia:
$W/v/bin/python -I -B $E/herramientas/cobertura_procedencia.py $W/a
# mutantes:
python3 $E/herramientas/mutantes_v2.py $W/a $W/m1 tests/unit/test_backtest_order_hygiene.py $W/v/bin/python $W/m1.json
python3 $E/herramientas/mutantes_traza_v2.py $W/a $W/m2 tests/integration/test_backtest_provenance.py $W/v/bin/python $W/m2.json
# CI, paso a paso:
$W/v/bin/ruff check packages tests scripts
bash $E/herramientas/correr_suite_ci.sh $W/a $W/v/bin/python $W/s.txt $W/s.xml
(PYTHONPATH=packages/tia/src TIA_DATABASE_URL=sqlite:///./data/runtime/ci.db $W/v/bin/python -m alembic upgrade head)
(cd frontend && npm ci --no-fund --no-audit && npm run typecheck && npm run build)
```

## 3. Estado del repositorio original y congelados
```bash
git -C /home/user/Trader-IA rev-parse HEAD; git -C /home/user/Trader-IA status --porcelain -uall | wc -l
bash $E/herramientas/congelados.sh /home/user/Trader-IA <scratchpad>
```
