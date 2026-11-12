#!/usr/bin/env bash
# Registra, solo leyendo, el estado del repositorio original (mismos campos y comandos que los registros 00/99 anteriores).
# Uso: estado_repo.sh <repo> <título>
cd "$1" || exit 2
echo "== $2: $(date -u +%FT%TZ)"
echo "ruta: $(pwd)"
echo "HEAD: $(git rev-parse HEAD)"
echo "rama: $(git rev-parse --abbrev-ref HEAD)"
echo "refs: $(git for-each-ref --format='%(refname) %(objectname)' | tr '\n' ';')"
echo "cambios (porcelain -uall): $(git status --porcelain=v1 -uall | wc -l)"
echo "stash: $(git stash list | wc -l)"
echo "índice (ls-files -s) sha256: $(git ls-files -s | sha256sum | cut -d' ' -f1)"
echo "árbol de HEAD: $(git rev-parse HEAD^{tree})"
echo "reflog (sha256 completo): $(git reflog --format='%H %gs' | sha256sum | cut -d' ' -f1) · entradas: $(git reflog | wc -l)"
echo "remotos: $(git remote -v | tr '\n' ';')"
echo "engine.py disco: $(sha256sum packages/tia/src/tia/backtest/engine.py | cut -d' ' -f1)"
echo "paper.py disco:  $(sha256sum packages/tia/src/tia/execution/paper.py | cut -d' ' -f1)"
echo "archivos no rastreados ignorados (conteo, solo informativo): $(git status --porcelain=v1 --ignored | grep -c '^!!')"
