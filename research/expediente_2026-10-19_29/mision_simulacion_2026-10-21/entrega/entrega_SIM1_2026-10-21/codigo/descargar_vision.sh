#!/usr/bin/env bash
# Descarga klines mensuales 1h de spot desde data.binance.vision (fuente oficial de Binance) con su .CHECKSUM.
# Uso: bash descargar_vision.sh <dir_destino> <registro.tsv> SIMBOLO AAAA-MM AAAA-MM
# No interpreta el contenido: solo descarga, guarda y anota URL, código HTTP, bytes y hora UTC.
set -u
dest="$1"; log="$2"; sym="$3"; desde="$4"; hasta="$5"
base="https://data.binance.vision/data/spot/monthly/klines/$sym/1h"
mkdir -p "$dest/spot/monthly/klines/$sym/1h"
m="$desde"
while [[ "$m" < "$hasta" || "$m" == "$hasta" ]]; do
  for suf in ".zip" ".zip.CHECKSUM"; do
    f="$sym-1h-$m$suf"; out="$dest/spot/monthly/klines/$sym/1h/$f"
    for intento in 1 2 3 4 5; do
      code=$(curl -sS --retry 2 -o "$out" -w "%{http_code}" "$base/$f") && [[ "$code" == "200" ]] && break
      sleep $((2 ** intento))
    done
    printf "%s\t%s\t%s\t%s\n" "$(date -u +%FT%TZ)" "$base/$f" "$code" "$(stat -c %s "$out" 2>/dev/null || echo 0)" >> "$log"
  done
  m=$(date -u -d "$m-01 +1 month" +%Y-%m)
done
