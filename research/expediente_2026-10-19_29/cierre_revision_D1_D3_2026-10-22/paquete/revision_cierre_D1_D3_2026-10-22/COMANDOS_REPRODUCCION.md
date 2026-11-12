# Comandos para repetir esta revisión (solo lectura y clones aislados)

```bash
S=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad
E=$S/decision_final_D1_D3_2026-10-22/entrega; N=entrega_integracion_D1_D3_v3r2_2026-10-22
B=72ffae5d2698440c8f1afaff12e07bd8adde66fb; W=/ruta/nueva; mkdir -p $W/x
PY=$S/cierre_D1_D3_2026-10-22/entorno/venv_A/bin/python      # o un venv con: pip install -c entorno/ci-py311.txt -e ".[api,db,postgres,redis,llm,dev]"

# 1. Identidad
sha256sum $E/$N.zip                          # d912c88a59b878520501ff221fd78d2d2eef870ae0b681d2108441ab8cbd5155
(cd $E && sha256sum -c $N.zip.sha256)
unzip -q $E/$N.zip -d $W/x && cd $W/x/$N && sha256sum -c --quiet SHA256SUMS && wc -l < SHA256SUMS     # 98
diff <(find . -type f ! -name SHA256SUMS | sed 's#^\./##' | LC_ALL=C sort) <(awk '{print $2}' SHA256SUMS | LC_ALL=C sort)
sha256sum parches/*.patch parches/originales_v2/*.patch
P=$W/x/$N/parches

# 2. D1: 02v3 aplica sin 01 (debería fallar si fuera inseparable por git; no falla)
nuevo() { git clone -q --no-local /home/user/Trader-IA $W/$1 && git -C $W/$1 checkout -q --detach $B; }
nuevo a && git -C $W/a apply --check $P/02v3_*.patch; echo "código: $?"                    # 0
git -C $W/a apply $P/02v3_*.patch && $PY -I -B <herramientas>/sonda_version.py $W/a       # engine_version=1.1.0 · order_hygiene=False
(cd $W/a && PYTHONPATH=packages/tia/src $PY -m pytest -p no:cacheprovider -o addopts="" -q tests/integration/test_backtest_provenance.py)   # 14 pasan
# 3. 03 reversible solo; la unidad 01+02v3 revertible junta
nuevo c && for p in 01 02v3 03; do git -C $W/c apply $P/${p}_*.patch; done
git -C $W/c apply -R $P/03_*.patch && (cd $W/c && sha256sum -c --quiet $P/SHA256_archivos_resultantes_obligatoria_v3.txt && echo "= obligatoria v3")
nuevo f && git -C $W/f apply --check $P/03_*.patch; echo "03 sobre la base: $?"          # 0
# 4. Auditoría de documentos
grep -n -i "\bCI\b\|verde\|green" $W/x/$N/*.md
for r in R15 R17 R18 R19 R22 R24; do grep -h "^| $r " $W/x/$N/MATRIZ_RIESGOS.md; done
grep -n "no aplica sin 01\|salvo R19" $W/x/$N/*.md
# 5. R19: humo (1 corrida, sin carga) y plan completo en PLAN_R19.md
bash <herramientas>/r19_carga.sh $W/c $PY $W/humo0 1 0 0 "tests/integration/test_account_restore.py::test_partial_fills_and_fees_rebuild_identically_however_often"
bash <herramientas>/r19_carga.sh $W/c $PY $W/humo1 1 0 1 "tests/integration/test_account_restore.py::test_partial_fills_and_fees_rebuild_identically_however_often"
# 6. Repositorio original y congelados
git -C /home/user/Trader-IA rev-parse HEAD; git -C /home/user/Trader-IA status --porcelain -uall | wc -l
bash <herramientas>/congelados.sh /home/user/Trader-IA $S
```
`<herramientas>` = la carpeta `herramientas/` de este paquete de revisión.
