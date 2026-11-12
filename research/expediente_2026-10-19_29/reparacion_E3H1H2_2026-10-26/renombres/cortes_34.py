"""Tratamiento de los 34 cortes con reanudación de F3 (Adenda 1, regla 3: control de calidad). Solo actividad y textos.
Uso: python -I cortes_34.py <dir_ejecucion_E3> <clasificacion_renombres.json> <salida.json>"""
import datetime as dt, json, re, sys
from pathlib import Path
E3, CLS, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
aud = json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())
saltos = {(c["simbolo"], c["ultimo_activo"]) for c in json.loads((E3 / "resultados/estructural/estructural.json").read_text())["cortes_con_reanudacion"]["lista_saltos"]}
cl = json.loads((E3 / "datos_anuncios/commoncrawl/anuncios_clasificados.json").read_text())
splits = [(c["titulo"], c["url"], str(c.get("publicado") or "")) for c in cl if "Reverse Token Split" in c["titulo"] and "Postpone" not in c["titulo"]]
mapeos2 = {(m["viejo_usdt"], m["E"]): m for m in json.loads(CLS.read_text())["mapeos"] if m["regla"] == 2}
INICIO_A = dt.date(2023, 5, 15)
out = []
for a in aud:
    s = a["simbolo"]
    for c0, c1, h in a.get("cortes_con_reanudacion", []):
        f = {"simbolo": s, "ultimo_activo": c0, "reanuda": c1, "dias": h, "salto_x10_F3": (s, c0) in saltos,
             "dentro_de_A": dt.date.fromisoformat(c1) >= INICIO_A}
        apal = bool(re.fullmatch(r".+(UP|DOWN|BULL|BEAR)USDT", s))
        m = next((m for (v, E), m in mapeos2.items() if v == s and dt.date.fromisoformat(c0) <= dt.date.fromisoformat(E) <= dt.date.fromisoformat(c1)), None)
        if m:
            f.update(tratamiento="Adenda 1, regla 2: posiciones × r y serie continua a través de r", r=m["r"], cita=m["cita"], certeza=m["certeza"])
        elif apal:
            base = s[:-4]
            hit = [t for t in splits if re.search(rf"\b{base}\b", t[0]) and abs((dt.date.fromisoformat(t[2][:10]) - dt.date.fromisoformat(c1)).days) <= 3] if True else []
            f.update(tratamiento="token apalancado: excluido de todo universo (§4.5); sin efecto",
                     anuncio_reverse_split=[t[0] for t in hit] or None)
        else:
            f.update(tratamiento="Adenda 1, regla 3: sin anuncio archivado de canje; mismo listado (corte < 30 días); se informa como limitación")
        out.append(f)
out.sort(key=lambda f: f["ultimo_activo"])
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1))
for f in out:
    print(f["ultimo_activo"], f["reanuda"], f["simbolo"], "x10" if f["salto_x10_F3"] else "   ", "A" if f["dentro_de_A"] else "-", f["tratamiento"][:40], f.get("r", ""), (f.get("anuncio_reverse_split") or [""])[0][:60])
