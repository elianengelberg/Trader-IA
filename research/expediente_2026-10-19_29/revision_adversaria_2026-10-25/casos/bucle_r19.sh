#!/usr/bin/env bash
# La prueba de R19 sola, N veces, MIENTRAS corren otras suites completas (carga de procesos pytest, como en R10).
A="$1"; N="$2"; L="$3"; PY="$4"; TMP="$L/../tmp_r19"; mkdir -p "$TMP"; cd "$A" || exit 2
K=tests/integration/test_account_restore.py::test_partial_fills_and_fees_rebuild_identically_however_often
for i in $(seq 1 "$N"); do
  T0=$(date +%s.%N); C0=$(cut -d' ' -f1 /proc/loadavg)
  OUT=$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src TMPDIR=$TMP $PY -B -m pytest -q -p no:cacheprovider -o addopts="" "$K" 2>&1); RC=$?
  echo "$i rc=$RC seg=$(echo "$(date +%s.%N) - $T0" | bc) carga=$C0 $(echo "$OUT" | tail -1 | cut -c1-80) $(echo "$OUT" | grep -o 'persistence writes still in flight' | head -1)"
done > "$L/D_bucle_r19.txt" 2>&1
rm -rf -- "${TMP:?}"
