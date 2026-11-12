#!/usr/bin/env bash
# Verificación final del ciclo TI: estado del repositorio protegido (solo lectura, sin locks opcionales), procesos y
# enlaces residuales, y limpieza del paquete (sin secretos, bases, sockets, enlaces, cachés). Uso: verificar_final_TI.sh <paquete>
set -u
R=/home/user/Trader-IA; P="$1"
g() { git --no-optional-locks -C "$R" "$@"; }
echo "== Repositorio protegido ($R) · $(date -u +%FT%TZ)"
echo "HEAD                 $(g rev-parse HEAD)            (línea base 72ffae5d2698440c8f1afaff12e07bd8adde66fb)"
echo "sha256 de .git/index $(sha256sum "$R/.git/index" | cut -d' ' -f1)   (línea base 37490035d6706739fd7c9add42ad62c4e0c9260089e8e2e77a486f55e3bdcd1b)"
echo "cambios              $(g status --porcelain | wc -l)   (línea base 0)"
echo "ignorados            $(g status --porcelain --ignored | grep -c '^!!')   (línea base 18)"
echo "reflog               $(g reflog | wc -l)   (línea base 13)"
echo "tags                 $(g tag | wc -l) · stash $(g stash list | wc -l) · ramas $(g branch -a | wc -l)"
echo "validada_para_operar $(grep -rl --exclude-dir=.git 'validada_para_operar' "$R" 2>/dev/null | wc -l) archivos (incluidos los ignorados)"
echo "sha256 de .git/index después de estas lecturas: $(sha256sum "$R/.git/index" | cut -d' ' -f1)"
echo
echo "== Procesos y enlaces residuales"
for patron in 'pytest' 'postgres' 'exp_mutacion' 'simulacion_integral' 'ci_local'; do
  n=0; for pid in $(pgrep -f "$patron"); do [[ "$pid" == "$$" ]] && continue; a=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null); [[ "$a" == *verificar_final_TI* || -z "$a" ]] && continue; n=$((n + 1)); done
  echo "$patron: $n"
done
echo "enlaces /tmp/tia_ic_*: $(find /tmp -maxdepth 1 -name 'tia_ic_*' | wc -l)"
echo
echo "== Paquete ($P)"
echo "archivos             $(find "$P" -type f | wc -l)"
echo "enlaces simbólicos   $(find "$P" -type l | wc -l)"
echo "sockets / fifos      $(find "$P" \( -type s -o -type p \) | wc -l)"
echo "bases de datos       $(find "$P" -type f \( -name '*.db' -o -name '*.sqlite*' -o -name '*.db-wal' -o -name '*.db-shm' \) | wc -l)"
echo "cachés de Python     $(find "$P" \( -name '__pycache__' -o -name '*.pyc' \) | wc -l)"
echo "posibles secretos    $(grep -rIlE '(api[_-]?secret|BINANCE_API_(KEY|SECRET)=[^ \"$]{8,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|ghp_[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,}|sk-ant-[A-Za-z0-9-]{10,})' "$P" | wc -l)"
echo "direcciones de correo $(grep -rIlE '[A-Za-z0-9._%+-]+@(gmail|hotmail|outlook|yahoo)\.' "$P" | wc -l)"
