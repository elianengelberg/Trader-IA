"""Segunda lectura (protocolo SL-v1, §4) · arma el paquete CIEGO para el lector.
El paquete lleva, por ítem, solo el par y los archivos de página. No lleva fechas, categorías, lecturas previas ni nada de la
ventana. El mapa ítem → clave (con la fecha de la primera pasada) queda fuera del paquete, en `privado/`.
Lee: `eventos.json` de la primera pasada, `resoluciones_manuales.json` de la segunda pasada (solo las claves y el archivo
fuente, para saber qué páginas copiar), `anuncios_clasificados.json` (url → archivo) y las páginas. No lee precios.
Uso: python3 -I -B preparar_paquete.py <dir_ejecucion_E3> <resoluciones_pasada2.json> <dir_salida_segunda_lectura>"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

E3, RES2, OUT = (Path(a) for a in sys.argv[1:4])
CC = E3 / "datos_anuncios" / "commoncrawl"
PAG = CC / "paginas"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


eventos1 = {e["clave"]: e for e in json.loads((E3 / "resultados" / "conciliacion_pasada1" / "eventos.json").read_text())}
claves = sorted(json.loads(RES2.read_text())["eventos"])
assert len(claves) == 47, len(claves)
por_url = {}
for a in json.loads((CC / "anuncios_clasificados.json").read_text()):
    por_url.setdefault(a["url"], []).append(a["archivo"])

fuente2 = {k: v["fuente"]["archivo"] for k, v in json.loads(RES2.read_text())["eventos"].items()}
items, mapa, copias = [], {}, {}
for clave in claves:
    e = eventos1[clave]
    archivos = sorted({f for u in e["urls"] for f in por_url.get(u, [])} | {fuente2[clave]})
    items.append((e["par"], archivos, clave))
items.sort(key=lambda t: (t[0], t[1]))  # orden por par y archivo: no revela fechas
(OUT / "paquete" / "paginas").mkdir(parents=True, exist_ok=False)
(OUT / "privado").mkdir(parents=True, exist_ok=False)
publico = []
for n, (par, archivos, clave) in enumerate(items, 1):
    iid = f"L{n:02d}"
    publico.append({"id": iid, "par": par, "paginas": archivos})
    mapa[iid] = {"clave": clave, "par": par, "paginas": archivos}
    for f in archivos:
        if f not in copias:
            src = PAG / f
            h0 = sha(src)
            shutil.copyfile(src, OUT / "paquete" / "paginas" / f)
            assert sha(OUT / "paquete" / "paginas" / f) == h0 == sha(src)
            copias[f] = h0
(OUT / "paquete" / "ITEMS.json").write_text(json.dumps(publico, ensure_ascii=False, indent=1))
(OUT / "paquete" / "PAGINAS.sha256").write_text("".join(f"{h}  paginas/{f}\n" for f, h in sorted(copias.items())))
(OUT / "privado" / "mapa_items.json").write_text(json.dumps(mapa, ensure_ascii=False, indent=1))
print(json.dumps({"items": len(publico), "paginas_copiadas": len(copias)}, ensure_ascii=False))
