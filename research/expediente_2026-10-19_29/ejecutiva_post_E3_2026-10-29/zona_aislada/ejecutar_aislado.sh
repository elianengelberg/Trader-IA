#!/bin/bash
# Zona de ejecución aislada (R-4 / L-25), sin modificar nada en disco.
# Corre el comando dado dentro de un espacio de montaje PRIVADO (unshare --mount --propagation private) donde cada ruta
# de PROTEGIDOS.tsv queda tapada por un directorio o archivo vacío de solo lectura:
#   - las 2 copias reales de las series (757 .npz cada una) se ven vacías;
#   - el tarball de datos y las 15 copias de orquestadores (E3R, v2, v3) se ven como archivos de 0 bytes.
# Antes de ejecutar el comando, comprueba DENTRO que el tapado es efectivo; si no, aborta con código 99 sin ejecutar nada.
# Al terminar el proceso, el espacio de montaje desaparece: nada cambia fuera de él. No cambia permisos ni archivos.
# Límite: solo protege lo que se lance con este script. Una ejecución directa fuera de él no queda protegida.
# Uso: ejecutar_aislado.sh <comando> [argumentos...]
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
LISTA="$AQUI/PROTEGIDOS.tsv"
[ -s "$LISTA" ] || { echo "falta PROTEGIDOS.tsv" >&2; exit 98; }
[ "$#" -ge 1 ] || { echo "uso: $0 <comando> [args]" >&2; exit 2; }
mkdir -p "$AQUI/.vacios"
VACIO_D="$(mktemp -d -p "$AQUI/.vacios")"
VACIO_F="$(mktemp -p "$AQUI/.vacios")"
export LISTA VACIO_D VACIO_F
exec unshare --mount --propagation private bash -c '
  set -euo pipefail
  while IFS=$'"'"'\t'"'"' read -r tipo ruta; do
    [ -e "$ruta" ] || continue
    if [ "$tipo" = dir ]; then mount --bind "$VACIO_D" "$ruta"; else mount --bind "$VACIO_F" "$ruta"; fi
    mount -o remount,bind,ro "$ruta"
  done < "$LISTA"
  falla=0
  while IFS=$'"'"'\t'"'"' read -r tipo ruta; do
    [ -e "$ruta" ] || continue
    if [ "$tipo" = dir ]; then n=$(find "$ruta" -mindepth 1 | wc -l); [ "$n" -eq 0 ] || { echo "TAPADO INEFECTIVO: $ruta ($n entradas)" >&2; falla=1; }
    else s=$(stat -c %s "$ruta"); [ "$s" -eq 0 ] || { echo "TAPADO INEFECTIVO: $ruta ($s bytes)" >&2; falla=1; }; fi
  done < "$LISTA"
  [ "$falla" -eq 0 ] || exit 99
  echo "[zona aislada] $(grep -c . "$LISTA") rutas protegidas tapadas; ejecutando: $*" >&2
  exec "$@"
' bash "$@"
