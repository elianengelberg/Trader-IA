#!/usr/bin/env bash
# Suite completa como la CI parcheada, en un árbol aislado, con TMPDIR propio. Uso: suite.sh <árbol> <nombre> <dir_logs> <python>
A="$1"; N="$2"; L="$3"; PY="$4"; TMP="$L/../tmp_$N"; mkdir -p "$TMP"
cd "$A" || exit 2
{ echo "== suite $N · árbol $A · write-tree $(git add -A && git write-tree; git reset -q) · inicio $(date -u +%FT%TZ) · carga $(cat /proc/loadavg)"
  echo "python $($PY -V 2>&1) · $PY"
  echo "comando: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src TMPDIR=$TMP $PY -B -m pytest tests -q -p no:cacheprovider -rsxX --junitxml=$L/D_$N.xml"
  C=$(PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src TMPDIR=$TMP $PY -B -m pytest tests -q -p no:cacheprovider --collect-only 2>&1 | grep -cE '::')
  echo "recolectadas (collect-only, nodeids): $C"
  T0=$(date +%s)
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src TMPDIR=$TMP timeout 3500 $PY -B -m pytest tests -q -p no:cacheprovider -rsxX --junitxml=$L/D_$N.xml > $L/D_$N.pytest.txt 2>&1; RC=$?
  echo "rc=$RC · duración $(( $(date +%s) - T0 )) s · fin $(date -u +%FT%TZ) · carga $(cat /proc/loadavg)"
  tail -2 $L/D_$N.pytest.txt
  echo "estado del árbol tras la suite: $(git status --porcelain -uall | wc -l) entradas"; } > "$L/D_$N.log" 2>&1
rm -rf -- "${TMP:?}"
