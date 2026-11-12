#!/usr/bin/env bash
# Agrega a prerregistro/HUELLAS.txt un bloque con la hora UTC y los SHA-256 de lo que fija el prerregistro.
# Uso: bash fijar_huellas.sh <titulo del bloque>
set -eu
M="$(cd "$(dirname "$0")/.." && pwd)"
E1=/tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/experimentos/E1_bot_datos_reales_2026-10-19
{
  echo "== $1: $(date -u +%FT%TZ)"
  cd "$M"
  sha256sum prerregistro/PRERREGISTRO_SIM1.md codigo/*.py codigo/*.sh parche/parche_motor_D1_D3.diff \
    parche/test_backtest_order_hygiene.py registro/SHA256_datos_vision.txt resultados/calidad_datos.json
  ( cd trader-ia && sha256sum packages/tia/src/tia/backtest/engine.py packages/tia/src/tia/execution/paper.py \
      | sed 's#^\(\S*\)  #\1  trader-ia/#' )
  ( cd "$E1" && sha256sum codigo/e1.py codigo/e1_comun.py entorno/requisitos_con_hash.txt | sed 's#^\(\S*\)  #\1  E1/#' )
  echo "copia de tia: $(cat "$M/registro/origen_copia.txt" | head -1) + parche (git diff contra 5b08a14 en la copia)"
  echo
} >> "$M/prerregistro/HUELLAS.txt"
tail -25 "$M/prerregistro/HUELLAS.txt"
