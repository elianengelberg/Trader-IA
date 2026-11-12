#!/usr/bin/env bash
# Clona el repositorio protegido SOLO para leer (--no-local) en <destino> nuevo, en <commit>, y deshabilita el push hacia
# el original: un `git push` accidental desde la copia falla en lugar de escribir en el repositorio protegido.
# Uso: clon_seguro.sh <destino> [commit]
set -euo pipefail
D="$1"; C="${2:-72ffae5d2698440c8f1afaff12e07bd8adde66fb}"
[[ -e "$D" ]] && { echo "$D ya existe"; exit 1; }
git clone -q --no-local /home/user/Trader-IA "$D"
git -C "$D" checkout -q --detach "$C"
git -C "$D" remote set-url --push origin "no-push://deshabilitado-repositorio-protegido"
