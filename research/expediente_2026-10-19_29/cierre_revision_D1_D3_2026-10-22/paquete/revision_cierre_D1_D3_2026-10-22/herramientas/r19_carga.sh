#!/usr/bin/env bash
# Corre N veces una selección de pruebas bajo K procesos que queman CPU, con o sin el bucle de fondo aparcado (control).
# No toca ningún repositorio: solo lee el árbol dado y escribe en <salida>. Los quemadores se apagan siempre (trap y timeout).
# Uso: r19_carga.sh <árbol> <python> <salida> <N> <K> <park 0|1> <selección pytest...>
set -u
ARBOL="$1"; PY="$2"; OUT="$3"; N="$4"; K="$5"; PARK="$6"; shift 6; SEL=("$@")
HERR="$(cd "$(dirname "$0")" && pwd)"; mkdir -p "$OUT"; export TMPDIR="$OUT/tmp"; mkdir -p "$TMPDIR"
pids=(); for _ in $(seq 1 "$K"); do timeout $(( N * 240 )) python3 -c 'while True: pass' & pids+=($!); done
trap 'kill "${pids[@]}" 2>/dev/null' EXIT
echo "corrida,K,park,salida_pytest,pruebas_falladas,ciclos_fondo,flush_max_s,vencimientos,no_terminaron,errores_escritura,carga_inicio" > "$OUT/resumen.csv"
for i in $(seq 1 "$N"); do
  J="$OUT/r19_K${K}_park${PARK}_$i.json"
  ( cd "$ARBOL" && R19_OUT="$J" R19_PARK="$PARK" PYTHONPATH="packages/tia/src:$HERR" "$PY" -B -m pytest -p sonda_r19 -p no:cacheprovider \
      -o addopts="" -q -rA --tb=line "${SEL[@]}" > "${J%.json}.log" 2>&1 ); rc=$?
  "$PY" -I - "$J" "$i" "$K" "$PARK" "$rc" >> "$OUT/resumen.csv" <<'PYX'
import json, sys
j, i, k, park, rc = sys.argv[1:6]; d = json.load(open(j)); f = d["flushes"]
falladas = [n for n, v in d["pruebas"].items() if v["resultado"] != "passed"]
venc = [x for x in f if not x["ok"]]
print(",".join(map(str, [i, k, park, rc, "|".join(falladas) or "-", d["fondo"], max((x["seg"] for x in f), default=0), len(venc),
                         sum(x.get("no_terminaron", 0) for x in venc), len(d["errores_escritura"]), round(d["carga_inicio"][0], 2)])))
PYX
done
cat "$OUT/resumen.csv"
