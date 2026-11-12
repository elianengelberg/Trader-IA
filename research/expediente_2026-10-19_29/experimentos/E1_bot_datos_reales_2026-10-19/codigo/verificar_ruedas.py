"""Compara cada rueda descargada con los metadatos públicos de PyPI (sha256, nombre de archivo, fecha de subida) y con
los rangos del pyproject. No instala nada. Uso: python3 -I verificar_ruedas.py <dir_ruedas>"""
import hashlib, json, sys, urllib.request
from pathlib import Path
RANGOS = {"pydantic": ">=2.7,<3", "pydantic-settings": ">=2.2,<3", "numpy": ">=1.26,<3", "structlog": ">=24.1"}
ok = True
for w in sorted(Path(sys.argv[1]).glob("*.whl")):
    nombre, version = w.name.split("-")[:2]
    proyecto = nombre.replace("_", "-").lower()
    meta = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{proyecto}/{version}/json", timeout=60))
    archivos = {u["filename"]: u for u in meta["urls"]}
    u = archivos.get(w.name)
    h = hashlib.sha256(w.read_bytes()).hexdigest()
    coincide = u is not None and u["digests"]["sha256"] == h
    ok &= coincide and not meta["info"].get("yanked", False)
    print(f"{'OK   ' if coincide else 'FALLA'} {proyecto}=={version} | sha256 {h[:16]}… == PyPI: {coincide} | subido {u['upload_time_iso_8601'][:10] if u else '?'} "
          f"| yanked: {u.get('yanked') if u else '?'} | rango pyproject: {RANGOS.get(proyecto, 'dependencia transitiva')}")
sys.exit(0 if ok else 1)
