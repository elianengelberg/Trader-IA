"""Alcance (NO ejecución) de una pasada completa con la regla N5. Para cada evento de la primera pasada:
- el origen de E según la extracción congelada (`fecha_efectiva` de cc_clasificar.py, effe8a2e…: «titulo» o «cuerpo»);
- las fechas del cuerpo que aparecen en oraciones con el patrón de exclusión (candidatas a la fecha de cese según N5);
- si alguna candidata difiere de E.
No recategoriza ningún evento, no recalcula ninguna ventana y no lee series ni precios: solo páginas archivadas (texto) y
los JSON de la conciliación.
Uso: python -B -I alcance_pasada_N5.py <cc_clasificar.py> <dir_ejecucion_E3> <salida.json>"""
import collections
import importlib.util
import json
import re
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("cc_clasificar_congelado", sys.argv[1])
CC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CC)
X, SAL = Path(sys.argv[2]), Path(sys.argv[3])
PAG = X / "datos_anuncios/commoncrawl/paginas"
eventos = json.loads((X / "resultados/conciliacion_pasada1/eventos.json").read_text())
por_url = collections.defaultdict(list)
for a in json.loads((X / "datos_anuncios/commoncrawl/anuncios_clasificados.json").read_text()):
    por_url[a["url"]].append(a["archivo"])

filas = []
for e in eventos:
    E = e["E"]
    candidatas, origenes, paginas = set(), set(), 0
    for url in e.get("urls") or []:
        for arch in por_url.get(url, []):
            p = json.loads((PAG / arch).read_text())
            titulo = CC.limpiar_titulo(p.get("titulo", ""))
            cuerpo, _, hallado = CC.cuerpo_de(p.get("titulo", ""), p.get("texto", ""))
            paginas += 1
            f, origen = CC.fecha_efectiva(titulo, cuerpo, CC.T_DELIST)
            origenes.add(origen)
            for oracion in re.split(r"(?<=[.!?])\s+", cuerpo if hallado else ""):
                if CC.T_DELIST.search(oracion) and not re.search(r"withdraw|deposit", oracion, re.I):
                    candidatas.update(d.isoformat() for _, d in CC.fechas_en(oracion))
    distintas = sorted(c for c in candidatas if c != E)
    filas.append({"par": e["par"], "E": E, "categoria_pasada1": e["categoria"], "L": e.get("L"), "paginas": paginas,
                  "origen_E": sorted(o for o in origenes if o), "fechas_cese_en_cuerpo": sorted(candidatas),
                  "difieren_de_E": distintas})
res = {"eventos": len(filas),
       "con_paginas_leidas": sum(f["paginas"] > 0 for f in filas),
       "E_desde_titulo": sum("titulo" in f["origen_E"] for f in filas),
       "con_fecha_de_cese_distinta_en_el_cuerpo": sum(bool(f["difieren_de_E"]) for f in filas),
       "por_categoria_con_discrepancia": dict(collections.Counter(f["categoria_pasada1"] for f in filas if f["difieren_de_E"])),
       "filas": filas}
SAL.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != "filas"}, ensure_ascii=False))
for f in filas:
    if f["difieren_de_E"]:
        print(f["par"], f["E"], f["categoria_pasada1"], "L", f["L"], "origen", f["origen_E"], "cuerpo:", f["difieren_de_E"][:6])
