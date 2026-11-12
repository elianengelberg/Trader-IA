#!/usr/bin/env bash
# Suite completa como la CI (.github/workflows/ci.yml: PYTHONPATH=packages/tia/src; python -m pytest tests -q),
# sin escribir caché ni bytecode en el árbol, con un informe JUnit para contar resultados exactos
# (el addopts del proyecto ya trae -q; con el -q de la CI la línea final de conteo no se imprime).
# Uso: bash correr_suite_ci.sh <arbol> <venv_python> <salida.txt> <salida.xml>
cd "$1" || exit 2
echo "== árbol $1 · HEAD $(git rev-parse HEAD) · $(git status --porcelain=v1 -uall | wc -l) cambios · inicio $(date -u +%FT%TZ)" > "$3"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/tia/src timeout 3500 "$2" -B -m pytest tests -q -p no:cacheprovider --junitxml="$4" >> "$3" 2>&1
echo "rc=$? · fin $(date -u +%FT%TZ)" >> "$3"
python3 -c "
import sys, xml.etree.ElementTree as ET
r = ET.parse(sys.argv[1]).getroot(); s = r if r.tag == 'testsuite' else r.find('testsuite')
t, f, e, k = (int(s.get(x, 0)) for x in ('tests', 'failures', 'errors', 'skipped'))
print(f'JUnit: {t} pruebas · {t - f - e - k} pasan · {f} fallan · {e} errores · {k} omitidas · {s.get(\"time\")} s')
" "$4" >> "$3"
