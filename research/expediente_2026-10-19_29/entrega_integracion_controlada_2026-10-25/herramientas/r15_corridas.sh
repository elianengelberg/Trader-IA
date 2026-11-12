#!/usr/bin/env bash
# R15: base (A+B, save de 02v3) y candidato (dev), orden alternado, dos semillas. Uso: r15_corridas.sh
set -u
cd /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo
for par in "base:/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/AB:11" "cand:/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/dev:11" "cand:/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/dev:12" "base:/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/trabajo/AB:12"; do
  IFS=: read -r nom arbol sem <<< "$par"
  echo "== $nom semilla $sem árbol $arbol inicio $(date -u +%FT%TZ)"
  timeout 1200 /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/venv/bin/python -I /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/casos/r15_pg.py "$arbol" /tmp/tia_ic_4899e77d 20 /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/integracion_controlada_2026-10-25/logs/F1_r15_${nom}_${sem}.json "$sem" 2>&1 | grep -vE "^\S+ \S+ \[(info|warning|debug)|^\s*$"
  echo "rc=${PIPESTATUS[0]}"
done
