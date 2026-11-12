# Comandos para repetir las comprobaciones

Todo corre en directorios nuevos. Ninguno escribe en el repositorio de origen, hace commits o push, ni despliega.

## 0. Integridad de la entrega
```bash
sha256sum -c entrega_integracion_D1_D3_v2_2026-10-22.zip.sha256     # junto al ZIP, fuera de él
mkdir /ruta/nueva && cd /ruta/nueva && unzip -q <ZIP> && cd entrega_integracion_D1_D3_v2_2026-10-22
sha256sum -c SHA256SUMS                                              # cada archivo de la entrega
```

## 1. Todo de una vez
```bash
bash reproducir.sh /home/user/Trader-IA /ruta/de/trabajo/nueva rapido      # ≈ 15 min
bash reproducir.sh /home/user/Trader-IA /ruta/de/trabajo/nueva2 completo   # ≈ 50 min: además, las 3 suites
# con la paridad con E1 (los datos de E1 deben estar donde los busca su e1_comun.py):
bash reproducir.sh /home/user/Trader-IA /ruta/nueva3 rapido <scratchpad>/experimentos/E1_bot_datos_reales_2026-10-19/codigo
```
Cada paso imprime `OK …` o se detiene con `MAL …`. Las salidas quedan en `<trabajo>/salidas/`.

## 2. Paso a paso
```bash
B=72ffae5d2698440c8f1afaff12e07bd8adde66fb; E=<extracción>; W=<trabajo nuevo>
git clone --no-local /home/user/Trader-IA $W/arbol && cd $W/arbol && git checkout --detach $B
git apply --check $E/parches/01_*.patch && git apply $E/parches/01_*.patch
git apply --check $E/parches/02_*.patch && git apply $E/parches/02_*.patch
sha256sum -c $E/parches/SHA256_archivos_resultantes_obligatoria.txt
git apply $E/parches/03_*.patch && sha256sum -c $E/parches/SHA256_archivos_resultantes_completa.txt   # opcional
python3.11 -m venv $W/v && (unset PYTHONPATH PIP_CONSTRAINT; $W/v/bin/pip install -c $E/entorno/ci-py311.txt -e ".[api,db,postgres,redis,llm,dev]")
$W/v/bin/ruff check packages tests scripts
PYTHONPATH=packages/tia/src $W/v/bin/python -m pytest -p no:cacheprovider -o addopts="" -q tests/unit/test_backtest_order_hygiene.py      # 8 pasan
PYTHONPATH=packages/tia/src $W/v/bin/python -m pytest -p no:cacheprovider -o addopts="" -q tests/integration/test_backtest_provenance.py # 12 pasan
python3 $E/herramientas/mutantes_v2.py $W/arbol $W/mut tests/unit/test_backtest_order_hygiene.py $W/v/bin/python $W/mut.json             # 10, 0 vivos
python3 $E/herramientas/mutantes_traza.py $W/arbol $W/mt tests/integration/test_backtest_provenance.py $W/v/bin/python $W/mt.json         # 12, 0 vivos, 1 equivalente
bash $E/herramientas/correr_suite_ci.sh $W/arbol $W/v/bin/python $W/suite.txt $W/suite.xml                                              # suite como la CI
python3 $E/herramientas/comparar_suites_v2.py <suite_base.xml> $W/suite.xml [--corregidas]
```

## 3. Diagnósticos de B3 (solo miden; no cambian el comportamiento)
```bash
cd <árbol> && SONDA_SALIDA=/tmp/s.json PYTHONPATH=packages/tia/src:$E/herramientas python -m pytest -p sonda_persistencia -o addopts="" -q \
  "tests/integration/test_adverse_recovery.py::test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole"
SONDA_CICLOS=/tmp/c.json PYTHONPATH=packages/tia/src:$E/herramientas python -m pytest -p sonda_ciclos -o addopts="" -q "<la misma prueba>"
python $E/herramientas/con_reloj.py 2026-10-22T05:30:00+00:00 -p no:cacheprovider -o addopts="" -q <prueba de reloj>   # requiere time-machine 3.5.1
```

## 4. Estado del repositorio original y archivos congelados
```bash
git -C /home/user/Trader-IA rev-parse HEAD; git -C /home/user/Trader-IA status --porcelain -uall | wc -l   # 72ffae5…, 0
bash $E/herramientas/congelados.sh /home/user/Trader-IA <scratchpad>                                      # 8 manifiestos OK
```
