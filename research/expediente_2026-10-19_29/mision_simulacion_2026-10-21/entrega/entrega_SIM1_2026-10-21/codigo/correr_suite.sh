#!/usr/bin/env bash
# Corre la suite de la plataforma como la CI (pytest tests, con el addopts del proyecto), sin caché ni bytecode.
# Uso: bash correr_suite.sh <copia> <salida>
cd "$1" && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src timeout 3500 \
  /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/mision_simulacion_2026-10-21/venv/bin/python -B -m pytest tests -p no:cacheprovider > "$2" 2>&1
echo "rc=$?" >> "$2"
