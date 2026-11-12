#!/usr/bin/env bash
# PostgreSQL 16 DESECHABLE y aislado para R24: un cluster nuevo en <dir>, sin TCP (listen_addresses=''), solo un socket Unix
# dentro de <dir>/sock, autenticación trust solo local. Corre dentro de un espacio de nombres de usuario donde el proceso
# aparece como el usuario postgres, así no hace falta cambiar permisos del scratchpad ni usar el cluster del sistema
# (16/main, que no se toca). Uso: pg_desechable.sh iniciar|detener|estado <dir>
set -euo pipefail
ACCION="$1"; D="$2"; BIN=/usr/lib/postgresql/16/bin; PGU=$(id -u postgres); PGG=$(id -g postgres)
ns() { unshare --user --map-user="$PGU" --map-group="$PGG" -- "$@"; }
case "$ACCION" in
  iniciar)
    [[ -e "$D/datos" ]] && { echo "$D/datos ya existe"; exit 1; }
    mkdir -p "$D/datos" "$D/sock" && chmod 700 "$D/datos"
    # Un socket Unix admite rutas de hasta 107 bytes: el socket vive en $D/sock y se publica por un enlace corto.
    L="/tmp/tia_r24_$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"; ln -s "$D/sock" "$L"; echo "$L" > "$D/enlace_socket"
    ns "$BIN/initdb" -D "$D/datos" -U postgres --auth=trust --encoding=UTF8 --locale=C.UTF-8 > "$D/initdb.log" 2>&1
    ns "$BIN/pg_ctl" -D "$D/datos" -l "$D/postgres.log" -w \
      -o "-c listen_addresses='' -c unix_socket_directories='$L' -c fsync=on -c max_connections=50" start
    echo "socket: $L -> $D/sock · URL async: postgresql+asyncpg://postgres@/postgres?host=$L" ;;
  detener)
    ns "$BIN/pg_ctl" -D "$D/datos" -m fast -w stop; L=$(cat "$D/enlace_socket"); [[ "$L" == /tmp/tia_r24_* && -L "$L" ]] && unlink "$L" ;;
  estado)
    ns "$BIN/pg_ctl" -D "$D/datos" status || true ;;
esac
