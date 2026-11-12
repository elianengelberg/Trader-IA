"""Lista (par, E, origen de E, título limpio) de los 55 eventos de la primera pasada. Solo texto archivado y JSON.
Uso (desde el scratchpad): python -B -I titulos_eventos.py"""
import importlib.util, json, collections
from pathlib import Path
X = Path("experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3")
spec = importlib.util.spec_from_file_location("cc", X / "codigo/cc_clasificar.py"); CC = importlib.util.module_from_spec(spec); spec.loader.exec_module(CC)
por = collections.defaultdict(list)
for a in json.load(open(X / "datos_anuncios/commoncrawl/anuncios_clasificados.json")): por[a["url"]].append(a["archivo"])
vistos = set()
for e in json.load(open(X / "resultados/conciliacion_pasada1/eventos.json")):
    for url in e["urls"][:1]:
        for arch in por[url][:1]:
            p = json.load(open(X / "datos_anuncios/commoncrawl/paginas" / arch))
            t = CC.limpiar_titulo(p.get("titulo", "")); cuerpo, _, h = CC.cuerpo_de(p.get("titulo", ""), p.get("texto", ""))
            f, origen = CC.fecha_efectiva(t, cuerpo, CC.T_DELIST)
            clave = (e["E"], t)
            if clave in vistos: continue
            vistos.add(clave); print(e["E"], origen, "|", t[:120], "| pares:", [x["par"][:-4] for x in json.load(open(X / "resultados/conciliacion_pasada1/eventos.json")) if x["E"] == e["E"]][:4])
