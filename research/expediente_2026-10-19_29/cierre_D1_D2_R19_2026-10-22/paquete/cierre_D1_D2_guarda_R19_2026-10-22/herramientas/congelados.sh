#!/usr/bin/env bash
# Verifica, solo leyendo, que los artefactos congelados coinciden con sus manifiestos registrados:
# T-MULTI / T-papel / H-CARRY (manifiestos versionados en el repo original) y E1/E2/E3 (manifiestos en sus carpetas).
# Uso: congelados.sh <repo_original> <scratchpad>
R="$1"; S="$2"; mal=0
chk() { local dir="$1" man="$2"; if (cd "$dir" && sha256sum -c --quiet "$man" > /dev/null 2>&1); then
          echo "OK   $(cd "$dir" && wc -l < "$man") entradas  $dir/$man"; else echo "MAL  $dir/$man"; mal=1; fi; }
chk "$R/research/tendencia_btc" ARTEFACTOS_SHA256.txt
chk "$R/research/hcarry_next" ARTEFACTOS_SHA256_2026-10-17.txt
chk "$R/research/hcarry_next/recuperado" SHA256SUMS
chk "$R/research/entregas_hcarry" SHA256SUMS
chk "$R/research/entregas_hcarry" SHA256SUMS_2026-10-17
chk "$S/experimentos/E1_bot_datos_reales_2026-10-19" resultados/real/SHA256SUMS
chk "$S/experimentos/E2_descubrimiento_2026-10-19" SHA256SUMS
chk "$S/experimentos/E3_seleccion_posicion_2026-10-19" SHA256SUMS
echo "T-MULTI y T-papel versionados: $(cd "$R" && git status --porcelain -- research/tendencia_btc | wc -l) cambios en research/tendencia_btc (git)"
exit $mal
