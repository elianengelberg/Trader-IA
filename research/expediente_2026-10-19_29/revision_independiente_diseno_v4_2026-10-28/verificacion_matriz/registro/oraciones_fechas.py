"""Oraciones (con el patrón de exclusión, sin retiros/depósitos) de cada anuncio de la 1.ª pasada cuya fecha difiere de E.
Solo texto archivado y JSON. Uso (desde el scratchpad): python -B -I oraciones_fechas.py"""
import importlib.util, json, re, collections
from pathlib import Path
X = Path("experimentos/E3_seleccion_posicion_2026-10-19/ejecucion_E3")
spec = importlib.util.spec_from_file_location("cc", X / "codigo/cc_clasificar.py"); CC = importlib.util.module_from_spec(spec); spec.loader.exec_module(CC)
PAG = X / "datos_anuncios/commoncrawl/paginas"
ev = json.load(open(X / "resultados/conciliacion_pasada1/eventos.json"))
por = collections.defaultdict(list)
for a in json.load(open(X / "datos_anuncios/commoncrawl/anuncios_clasificados.json")): por[a["url"]].append(a["archivo"])
vistos = set()
for e in ev:
    clave = (e["E"], tuple(sorted(e["urls"])))
    if clave in vistos: continue
    vistos.add(clave)
    for url in e["urls"]:
        for arch in por[url]:
            p = json.load(open(PAG / arch)); t = CC.limpiar_titulo(p.get("titulo", ""))
            cuerpo, _, h = CC.cuerpo_de(p.get("titulo", ""), p.get("texto", ""))
            hits = []
            for o in re.split(r"(?<=[.!?])\s+", cuerpo if h else ""):
                if CC.T_DELIST.search(o) and not re.search(r"withdraw|deposit", o, re.I):
                    ds = [d.isoformat() for _, d in CC.fechas_en(o)]
                    if any(d != e["E"] for d in ds): hits.append((ds, o.strip()))
            if hits:
                print("=====", e["par"], "E", e["E"], "| titulo:", t[:110])
                for ds, o in hits[:4]: print("   ", ds[:5], ">>", o[:230].replace("\n", " "))
