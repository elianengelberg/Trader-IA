# Comandos para verificar esta entrega (solo lectura y copias nuevas)

```bash
P=<carpeta extraída de este paquete>; W=<directorio nuevo>; B=72ffae5d2698440c8f1afaff12e07bd8adde66fb
PY=<python 3.11 con entorno/ci-py311.txt de v3r3>   # pip install -c entorno/ci-py311.txt -e ".[api,db,postgres,redis,llm,dev]"

# 0. Integridad del paquete y de v3r3
(cd $P && sha256sum -c --quiet SHA256SUMS && echo OK)
(cd $P/fase1 && sha256sum -c entrega_integracion_D1_D3_v3r3_2026-10-22.zip.sha256)   # 25902649…

# 1. Fase 1: reproducción limpia de v3r3 (≈ 30–55 min; agrega el paso 4b, separabilidad de 01 y 02v3)
mkdir $W/x && unzip -q $P/fase1/entrega_integracion_D1_D3_v3r3_2026-10-22.zip -d $W/x
env -i PATH=/usr/bin:/bin HOME=$W/h LANG=C.UTF-8 <variables de red> \
  bash $W/x/entrega_integracion_D1_D3_v3r3_2026-10-22/reproducir.sh /home/user/Trader-IA $W/trabajo completo [<código E1>]

# 2. Fase 2: la guarda, contra 01+02v3 (pasa) y contra 02v3 sin 01 (falla)
E=$W/x/entrega_integracion_D1_D3_v3r3_2026-10-22/parches
for t in obl solo; do git clone -q --no-local /home/user/Trader-IA $W/$t && git -C $W/$t checkout -q --detach $B; done
git -C $W/obl apply $E/01_*.patch && git -C $W/obl apply $E/02v3_*.patch; git -C $W/solo apply $E/02v3_*.patch
for t in obl solo; do git -C $W/$t apply $P/fase2/parche/05_propuesta_guarda_version_motor.patch
  (cd $W/$t && PYTHONPATH=packages/tia/src $PY -m pytest -q -o addopts="" tests/integration/test_engine_version_contract.py); done
# obl: 7 passed · solo: 5 failed, 2 passed
# mutantes (19 casos) y robustez (semillas 1–20, 3 conjuntos de datos):
$PY -I $P/fase2/herramientas/mutantes_guarda.py $W/obl $W/solo $W/mut $PY $W/mut.json
cp -r $P/fase2/herramientas $W/fase2_h   # robustez_guarda.py <árbol con la guarda> <salida.json> 1 20

# 3. Fase 3: la validación sintética de la sonda (no es el experimento)
#    árbol aparte con fase3/validacion_sonda/test_validacion_sonda_r19.py en tests/integration/, y luego:
R19_OUT=$W/v.json R19_PARK=0 R19_EXTRA=3 R19_EXTRA2=2 PYTHONPATH=packages/tia/src:$P/fase3/herramientas \
  unshare -n -- $PY -m pytest -p sonda_r19_v2 -o addopts="" -q tests/integration/test_validacion_sonda_r19.py
# El experimento R19 (enmienda 1) NO se corre sin aprobación: fase3/PLAN_R19_ENMIENDA_1.md, «Cómo correrlo».

# 4. Repositorio original y congelados
bash $P/herramientas/estado_repo.sh /home/user/Trader-IA "verificación"     # comparar con registro/00 y 99
bash $P/herramientas/congelados.sh /home/user/Trader-IA <scratchpad>
```
