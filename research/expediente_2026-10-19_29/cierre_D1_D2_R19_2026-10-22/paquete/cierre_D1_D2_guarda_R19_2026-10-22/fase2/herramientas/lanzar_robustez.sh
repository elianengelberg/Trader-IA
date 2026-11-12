#!/usr/bin/env bash
# Corre la evaluación de robustez de la guarda: motor correcto con semillas 1–20 y 02v3 sin 01 con semillas 1–10, en 3 procesos.
set -u
M="$1"; PY="$2"; O="$M/fase2/robustez"; mkdir -p "$O"
"$PY" -I -B "$M/fase2/guarda/robustez_guarda.py" "$M/fase2/g_obl" "$O/obl_1_10.json" 1 10 > "$O/obl_1_10.log" 2>&1 &
"$PY" -I -B "$M/fase2/guarda/robustez_guarda.py" "$M/fase2/g_obl" "$O/obl_11_20.json" 11 20 > "$O/obl_11_20.log" 2>&1 &
"$PY" -I -B "$M/fase2/guarda/robustez_guarda.py" "$M/fase2/g_solo02" "$O/solo02_1_10.json" 1 10 > "$O/solo02_1_10.log" 2>&1 &
wait; echo "robustez terminada"; ls -la "$O"
