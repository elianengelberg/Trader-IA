# Cómo reproducir cada resultado de este paquete

**Notación de rutas:**
- `PKG` = este paquete extraído;
- `X` = extracción de `cierre_D1_D2_guarda_R19_2026-10-22.zip` (`410ae629…`);
- `V` = extracción de la entrega v3r3 (`25902649…`, que va dentro de `X/fase1/`);
- `PY` = un Python 3.11 con las 74 versiones de `config/ci-py311.txt`;
- `REPO` = un clon del repositorio en `72ffae5d2698440c8f1afaff12e07bd8adde66fb`.

Ningún comando hace commits, push, PR, merge ni deploy. Los clones de trabajo se hacen con `reproduction/herramientas/clon_seguro.sh`, que deja el push deshabilitado. Nada de esto habilita el trading real.

## A. Integridad
```bash
sha256sum cierre_D1_D2_guarda_R19_2026-10-22.zip          # 410ae629de17957fc6fb60701f94aee9c73631bc3e9238c67a4c75983efba3c5
(cd X && sha256sum -c SHA256SUMS)                         # 67/67
(cd X/fase1 && sha256sum -c entrega_integracion_D1_D3_v3r3_2026-10-22.zip.sha256)   # 25902649…
(cd PKG && sha256sum -c MANIFEST.sha256)                  # este paquete
```

## B. R19 (enmienda 1 congelada; las herramientas son las del paquete `410ae629`, sin cambios)
```bash
# Corrida principal: 252 corridas. Los árboles los fija X/fase3/plan_r19_enmienda1.json (rutas absolutas del congelamiento)
python3 -I X/fase3/herramientas/r19_experimento.py X/fase3/plan_r19_enmienda1.json <salida>
python3 -I reproduction/herramientas/validez_instrumento_r19.py <salida> validez.json   # regla de evidence/registro/B1
PY -I X/fase3/herramientas/r19_analisis.py <salida> analisis.json                      # decisión congelada
# Suplementaria (registro pasivo de la cola; no decide nada)
python3 -I reproduction/herramientas/r19_suplementario.py X/fase3/plan_r19_enmienda1.json <salida_sup> 0,8 3
```
Los árboles `r19_base` y `r19_cand` son los congelados por la misión anterior: base + 01 + 02v3 + 03 (candidata) y base (base), con sus hashes en `X/registro/03_*`. Para reproducir en otra máquina hay que recrearlos y ajustar las rutas del plan. Eso cambia el plan, así que hay que registrarlo como una desviación.

## C. Guarda 05v2
```bash
# Árboles: base, obligatoria (01+02v3), solo02 (02v3 sin 01), solo01 (01 sin 02v3), desde V/parches con clon_seguro.sh
PY -I reproduction/herramientas/mutantes_guarda_v2.py tests/test_engine_version_contract.py <obl> <solo02> <base> <solo01> <dir_trabajo> PY mutantes_v2.json
# Robustez (herramienta del paquete 410ae629): 20 semillas en el motor correcto y 10 en 02v3 sin 01
PY -I -B X/fase2/herramientas/robustez_guarda.py <árbol_con_guarda> salida.json 1 10      # y 11 20
python3 -I X/fase2/herramientas/resumir_robustez.py <dir_salidas>
```

## E. Suites desde una extracción limpia
```bash
# v3r3 completo (base, obligatoria, completa, mutantes, reloj, 4b, paridad E1), con env -i y sin herencia de entorno
bash X/herramientas/verificar_extraccion_limpia.sh X/fase1 entrega_integracion_D1_D3_v3r3_2026-10-22 <dir_nuevo> completo <código_E1> <registro>
# Árbol final (A + 05v2 + 03 + 04 + 06v3), como la CI parcheada
bash reproduction/herramientas/clon_seguro.sh <final> 72ffae5d2698440c8f1afaff12e07bd8adde66fb
for p in V/parches/01_*.patch V/parches/02v3_*.patch patches/05v2_*.patch V/parches/03_*.patch V/parches/04_*.patch patches/06v3_*.patch; do git -C <final> apply "$p"; done
cd <final> && PYTHONPATH=packages/tia/src PY -B -m pytest tests -q -p no:cacheprovider --junitxml=ci-evidence/junit.xml
PYTHONPATH=packages/tia/src PY -B scripts/ci_gate.py ci-evidence ci-evidence/junit.xml
ruff check packages tests scripts
# Pruebas del gate (11 casos con el veredicto fijado de antemano; el último argumento es un Python SIN las dependencias del proyecto)
PY -I reproduction/herramientas/pruebas_gate.py <final> <final>/ci-evidence/junit.xml <base> PY <salida> /usr/bin/python3.11
```

## F. Simulación de integración (sin commits)
```bash
bash reproduction/herramientas/simular_integracion.sh <dir_nuevo> V/parches patches/05v2_guarda_version_motor.patch PY reproduction/herramientas
```

## G. PostgreSQL (R24 y R15) y Binance (R25)
```bash
bash reproduction/herramientas/pg_desechable.sh iniciar <dir>   # PostgreSQL 16, sin TCP, socket local, desechable
L=$(cat <dir>/enlace_socket)
# 14 pruebas existentes de trazabilidad con el almacén en PostgreSQL
(cd <obl> && R24_PG_SOCKET=$L PYTHONPATH=packages/tia/src:reproduction/herramientas PY -B -m pytest -p r24_pg_plugin -p no:cacheprovider -o addopts="" -q -rA tests/integration/test_backtest_provenance.py)
# Módulo 07 (parche 07)
(cd <obl+07> && TIA_TEST_POSTGRESQL_URL="postgresql+asyncpg://postgres@/postgres?host=$L" PYTHONPATH=packages/tia/src PY -B -m pytest -q tests/integration/test_backtest_store_postgresql.py)
# R15: 50 pares de guardados simultáneos
PYTHONPATH=<obl>/packages/tia/src PY -I -B reproduction/herramientas/sonda_r15_pg.py <obl> $L 50 r15.json
bash reproduction/herramientas/pg_desechable.sh detener <dir>
# R25: sonda del adaptador de Binance (sin red, testnet simulado, sin token)
PY -I -B reproduction/herramientas/sonda_binance_stop.py <árbol> sonda.json
```
