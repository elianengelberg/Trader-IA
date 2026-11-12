#!/usr/bin/env bash
# Descarga TODOS los ZIP que usa SIM-1 desde data.binance.vision y los verifica dos veces:
# contra el .CHECKSUM oficial y contra SHA256_zips_usados.txt (los bytes exactos usados el 2026-10-21).
# Uso: bash descargar_todo.sh <dir_destino_vacio>
set -eu
aqui="$(cd "$(dirname "$0")" && pwd)"; dest="$1"; mkdir -p "$dest"
base="https://data.binance.vision/data"
while read -r h rel; do
  url="$base/$rel"; out="$dest/$rel"; mkdir -p "$(dirname "$out")"
  for suf in "" ".CHECKSUM"; do
    for i in 1 2 3 4 5; do curl -sSf -o "$out$suf" "$url$suf" && break; sleep $((2**i)); done
  done
  oficial=$(awk '{print $1}' "$out.CHECKSUM"); real=$(sha256sum "$out" | awk '{print $1}')
  [[ "$oficial" == "$real" ]] || { echo "NO coincide con el .CHECKSUM oficial: $rel"; exit 1; }
  [[ "$h" == "$real" ]] || { echo "NO coincide con el hash registrado: $rel"; exit 1; }
done < "$aqui/SHA256_zips_usados.txt"
echo "OK: $(wc -l < "$aqui/SHA256_zips_usados.txt") archivos verificados"
