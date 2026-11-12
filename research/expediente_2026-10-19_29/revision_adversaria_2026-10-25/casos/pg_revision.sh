#!/usr/bin/env bash
# PostgreSQL 16 DESECHABLE para la revisión: cluster nuevo en <dir>, sin TCP, socket Unix por enlace corto en /tmp,
# log_statement=mod (registra cada escritura) y log_connections. No toca el cluster del sistema. Uso: pg_revision.sh iniciar|detener <dir>
set -euo pipefail
A="$1"; D="$2"; BIN=/usr/lib/postgresql/16/bin; PGU=$(id -u postgres); PGG=$(id -g postgres)
ns() { unshare --user --map-user="$PGU" --map-group="$PGG" -- "$@"; }
case "$A" in
  iniciar)
    [[ -e "$D/datos" ]] && { echo "$D/datos ya existe"; exit 1; }
    mkdir -p "$D/datos" "$D/sock" && chmod 700 "$D/datos"
    L="/tmp/tia_ra_$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"; ln -s "$D/sock" "$L"; echo "$L" > "$D/enlace_socket"
    ns "$BIN/initdb" -D "$D/datos" -U postgres --auth=trust --encoding=UTF8 --locale=C.UTF-8 > "$D/initdb.log" 2>&1
    ns "$BIN/pg_ctl" -D "$D/datos" -l "$D/postgres.log" -w \
      -o "-c listen_addresses='' -c unix_socket_directories='$L' -c fsync=on -c max_connections=60 -c log_statement=mod -c log_connections=on -c log_line_prefix='%m [%p] db=%d '" start
    echo "socket $L" ;;
  detener)
    ns "$BIN/pg_ctl" -D "$D/datos" -m fast -w stop; L=$(cat "$D/enlace_socket"); [[ "$L" == /tmp/tia_ra_* && -L "$L" ]] && unlink "$L" ;;
esac
