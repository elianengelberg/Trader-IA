#!/usr/bin/env bash
# B3: pruebas de reloj con el reloj de pared fijado (time-machine) en base y copia corregida, y la prueba
# de persistencia repetida. Uso: verificar_b3.sh <C> <salida>
set -u
C="$1"; OUT="$2"; PYT="$C/entorno/venv_T/bin/python"; PYA="$C/entorno/venv_A/bin/python"
export TMPDIR="$C/tmp_disco"
RELOJ=(
 "tests/integration/test_risk_state_persistence.py::test_five_restored_entries_for_the_symbol_refuse_the_sixth_after_the_restart"
 "tests/integration/test_account_restore.py::test_a_day_that_hit_the_loss_limit_still_refuses_entries_after_a_restart")
PERS="tests/integration/test_adverse_recovery.py::test_rejects_and_partials_over_hundreds_of_bars_keep_the_invariants_and_the_record_whole"
{
echo "== $(date -u +%FT%TZ) · B3 · venv_T (constraints ci-py311 + time-machine) para reloj; venv_A para persistencia"
echo "-- pruebas de reloj con reloj de pared fijado (tick=True). Resultado por árbol: <pasan>/<fallan>/<omitidas>"
for T in 2026-10-22T00:30:00+00:00 2026-10-22T02:30:00+00:00 2026-10-22T05:30:00+00:00 2026-10-22T05:50:00+00:00 2026-10-22T05:56:00+00:00 2026-10-22T12:00:00+00:00 2026-10-22T18:00:00+00:00 2026-10-22T23:59:00+00:00; do
  for ARBOL in base b3; do
    R=$(cd "$C/$ARBOL" && PYTHONPATH=packages/tia/src:"$C/herramientas_cierre" "$PYT" -B "$C/herramientas_cierre/con_reloj.py" "$T" -p no:cacheprovider -o addopts="" -q -rA "${RELOJ[@]}" 2>&1 | grep -E "^(PASSED|FAILED|SKIPPED|ERROR)" | awk '{print $1}' | sort | uniq -c | tr '\n' ' ')
    echo "$T  $ARBOL: $R"
  done
done
echo "-- reloj real ($(date -u +%FT%TZ))"
for ARBOL in base b3; do
  R=$(cd "$C/$ARBOL" && PYTHONPATH=packages/tia/src "$PYA" -B -m pytest -p no:cacheprovider -o addopts="" -q -rA "${RELOJ[@]}" 2>&1 | grep -E "^(PASSED|FAILED|SKIPPED|ERROR)" | awk '{print $1}' | sort | uniq -c | tr '\n' ' ')
  echo "real  $ARBOL: $R"
done
echo "-- persistencia (límite 10 s), 6 corridas por árbol, alternadas"
for i in 1 2 3 4 5 6; do
  for ARBOL in base b3; do
    R=$(cd "$C/$ARBOL" && PYTHONPATH=packages/tia/src "$PYA" -B -m pytest -p no:cacheprovider -o addopts="" -q "$PERS" 2>&1 | tail -1)
    echo "#$i $ARBOL: $R"
  done
done
echo "== fin $(date -u +%FT%TZ)"
} > "$OUT" 2>&1
