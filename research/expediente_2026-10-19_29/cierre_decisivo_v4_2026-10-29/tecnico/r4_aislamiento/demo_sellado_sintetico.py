"""R-4 · Demostración del «sellado por contenido» sobre una RÉPLICA SINTÉTICA (bytes aleatorios con la misma estructura de
rutas). NO toca ningún árbol real ni congelado, no ejecuta ningún orquestador y no lee datos.
Comprueba:
  1. antes del sellado, la ruta que usan v1/E3R, v2 y v3 (`<e3>/resultados/calidad/series/*.npz`) resuelve archivos;
  2. el sellado mueve cada archivo a `sellado/<sha256>` (sin extensión) y escribe un manifiesto `ruta → sha256`;
     después, esa ruta no resuelve nada, tampoco pasando la carpeta como argumento;
  3. los bytes se conservan: el manifiesto verifica 100 %;
  4. el sellado es reversible: la restauración desde el manifiesto reproduce el árbol byte a byte en otra carpeta;
  5. la búsqueda de cualquier carpeta con la estructura `resultados/calidad/series` con .npz da 0 tras el sellado.
Uso: python3 -I -B demo_sellado_sintetico.py <dir_vacio>"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

BASE = Path(sys.argv[1])
assert not BASE.exists() or not any(BASE.iterdir()), "la carpeta tiene que estar vacía"
rng = __import__("random").Random(20261029)
arbol = BASE / "replica" / "ejecucion_E3"
series = arbol / "resultados" / "calidad" / "series"
series.mkdir(parents=True)
(arbol / "codigo").mkdir()
for i in range(25):
    (series / f"SINT{i:02d}USDT.npz").write_bytes(bytes(rng.getrandbits(8) for _ in range(512)))
(arbol / "codigo" / "universo.py").write_text("# réplica sintética\n")


def resolver(e3: Path):
    return sorted((e3 / "resultados" / "calidad" / "series").glob("*.npz"))


def sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def buscar_estructura(raiz: Path):
    return [str(d) for d in raiz.rglob("series") if d.is_dir() and d.parent.name == "calidad" and any(d.glob("*.npz"))]


res = {"antes_resuelve": len(resolver(arbol)), "antes_estructuras": len(buscar_estructura(BASE))}
sellado = BASE / "sellado"
sellado.mkdir()
manifiesto = {}
for p in sorted(arbol.rglob("*")):
    if p.is_file():
        h = sha(p)
        destino = sellado / h
        if destino.exists():
            assert sha(destino) == h
            p.unlink()
        else:
            os.replace(p, destino)  # renombre atómico en el mismo sistema de archivos: no se copia ni se borra contenido
        manifiesto[str(p.relative_to(BASE))] = h
(BASE / "MANIFIESTO_SELLADO.json").write_text(json.dumps(manifiesto, indent=1, sort_keys=True))
res["despues_resuelve_ruta_por_defecto"] = len(resolver(arbol))
res["despues_resuelve_pasando_cualquier_carpeta"] = max([len(resolver(Path(d))) for d, _, _ in os.walk(BASE)] or [0])
res["despues_estructuras"] = len(buscar_estructura(BASE))
res["manifiesto_verifica"] = all(sha(sellado / h) == h for h in manifiesto.values())
restaurado = BASE / "restaurado"
for ruta, h in manifiesto.items():
    q = restaurado / ruta
    q.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sellado / h, q)
res["restauracion_byte_a_byte"] = all(sha(restaurado / r) == h for r, h in manifiesto.items())
res["archivos"] = len(manifiesto)
print(json.dumps(res, ensure_ascii=False, indent=1))
