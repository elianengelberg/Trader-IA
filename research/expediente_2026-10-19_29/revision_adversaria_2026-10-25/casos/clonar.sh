#!/usr/bin/env bash
# Clon de solo lectura del repositorio protegido (--no-local), en 72ffae5, con push deshabilitado. Uso: clonar.sh <destino>
set -euo pipefail
[[ -e "$1" ]] && { echo "$1 ya existe"; exit 1; }
git clone -q --no-local /home/user/Trader-IA "$1"
git -C "$1" checkout -q --detach 72ffae5d2698440c8f1afaff12e07bd8adde66fb
git -C "$1" remote set-url --push origin "no-push://revision-adversaria"
