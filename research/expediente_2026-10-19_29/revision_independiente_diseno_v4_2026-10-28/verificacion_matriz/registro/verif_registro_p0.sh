#!/bin/bash
# Compara los hashes listados en REGISTRO_P0.txt con los archivos actuales y muestra sus mtimes. Desde el scratchpad.
cd /tmp/claude-0/-home-user-Trader-IA/adb27888-5c6a-556a-b45b-2427c90ef46b/scratchpad/experimentos/E3R_desbloqueo_2026-10-26
echo '$ cat REGISTRO_P0.txt'; cat REGISTRO_P0.txt
echo; echo '$ sha256sum -c sobre las líneas con hash'; grep -E '^[0-9a-f]{64}  ' REGISTRO_P0.txt | sha256sum -c -
echo; echo '$ stat -c "%y %n" (mtime) de cada archivo listado y del propio registro'
for f in $(grep -E '^[0-9a-f]{64}  ' REGISTRO_P0.txt | awk '{print $2}') REGISTRO_P0.txt; do stat -c '%y  %n' $f; done
