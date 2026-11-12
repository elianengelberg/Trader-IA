#!/usr/bin/env bash
# Reconstruye los árboles de integración en clones aislados (git clone --no-local, push deshabilitado, sin commits).
# El identificador de árbol es el objeto git SHA-1 de `git add -A && git write-tree` (el repositorio usa formato sha1).
# Uso: arboles.sh <dir_trabajo> <dir_parches_paquete> <registro>
set -uo pipefail
W="$1"; P="$2"; L="$3"; BASE=72ffae5d2698440c8f1afaff12e07bd8adde66fb
V="$P/v3r3"; P01=$(ls "$V"/01_*.patch); P02=$(ls "$V"/02v3_*.patch); P03=$(ls "$V"/03_*.patch); P04=$(ls "$V"/04_*.patch)
P05="$P/05v2_guarda_version_motor.patch"; P06="$P/06v3_opcional_gate_ci_procedencia.patch"
declare -A ESPERADO=([base]=44850cfcbf53c3f8223d38a92031f4402f8ffb32 [A]=5d6a09549a8314f6e6e9386f82a52ca7628510d1
  [AB]=4ef14d31d686f4b0521207bd1e011d96e6c74822 [ABC]=84f9e349526d061771de74ae799d4ecd6e3732ce
  [A3]=a94be41a9f5d662f58c8ef82f75ab40f4b1ae373 [final]=0477c6a20c5e3831c2da3bf723948b7baafaa518)
declare -A PARCHES=([base]="" [A]="$P01 $P02" [AB]="$P01 $P02 $P05" [ABC]="$P01 $P02 $P05 $P03"
  [A3]="$P01 $P02 $P03" [final]="$P01 $P02 $P05 $P03 $P04 $P06")
{ echo "== IC-A.5 árboles de integración: $(date -u +%FT%TZ)"
  for f in $P01 $P02 $P03 $P04 $P05 $P06; do echo "parche $(sha256sum "$f" | cut -c1-64)  ${f#"$P"/}"; done
  for n in base A AB ABC A3 final; do
    D="$W/$n"
    if [[ -e "$D" ]]; then echo "$n: ya existe, no se toca"; continue; fi
    git clone -q --no-local /home/user/Trader-IA "$D" && git -C "$D" checkout -q --detach "$BASE" \
      && git -C "$D" remote set-url --push origin "no-push://integracion-controlada" || { echo "$n: CLON FALLÓ"; continue; }
    ok=1; for p in ${PARCHES[$n]}; do git -C "$D" apply --check "$p" && git -C "$D" apply "$p" || { ok=0; echo "$n: no aplica ${p##*/}"; }; done
    T=$(git -C "$D" add -A && git -C "$D" write-tree); git -C "$D" reset -q
    echo "$n: parches $(for p in ${PARCHES[$n]}; do printf '%s ' "${p##*/}" | cut -c1-5; done)· cambios $(git -C "$D" status --porcelain | wc -l) · árbol $T · esperado ${ESPERADO[$n]} · $([[ $ok == 1 && $T == "${ESPERADO[$n]}" ]] && echo COINCIDE || echo NO_COINCIDE) · HEAD $(git -C "$D" rev-parse --short HEAD) · push $(git -C "$D" remote get-url --push origin)"
  done
  echo "fin $(date -u +%FT%TZ) · disco libre $(df -h /tmp | awk 'NR==2{print $4}')"; } | tee "$L"
