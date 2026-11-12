"""Para cada evento de la primera pasada, extrae del texto archivado la(s) fecha(s) de cese de negociación (N5) y la frase.
Solo lectura de páginas archivadas locales; sin precios. Uso: fechas_efectivas.py <dir_E3> <salida.json>"""
import glob, json, re, sys
E3, SAL = sys.argv[1], sys.argv[2]
ev = json.load(open(f"{E3}/resultados/conciliacion_pasada1/eventos.json"))
pag = {}
for f in glob.glob(f"{E3}/datos_anuncios/commoncrawl/paginas/*.json"):
    d = json.load(open(f)); pag.setdefault(d["url"], (d, f.split("/")[-1]))
D = r"(20\d\d[-/]\d\d[-/]\d\d)(?:\s*,?\s*(?:at\s*)?(\d{1,2}:\d\d)(?:\s*(?:AM|PM))?\s*\(UTC\))?"
pats = [re.compile(r"(?:delist and cease trading|cease trading|stop trading|remove and cease trading)[^.]{0,260}?at\s+" + D, re.I),
        re.compile(r"At\s+" + D + r"[^.]{0,60}?(?:will )?(?:delist|remove and cease trading|cease trading|stop trading)", re.I)]
out = []
for e in sorted(ev, key=lambda e: (e["E"], e["par"])):
    res = {"par": e["par"], "E_pasada1": e["E"], "categoria_pasada1": e["categoria"], "L": e.get("L"), "fuentes": []}
    for u in e["urls"]:
        if u not in pag: continue
        d, arch = pag[u]
        t = re.sub(r"\s+", " ", d.get("texto", "")); i = t.find("Fellow"); body = t[i:] if i >= 0 else t
        base = e["par"][:-4]
        hallados = []
        for p in pats:
            for m in p.finditer(body):
                frase = body[max(0, m.start() - 40): m.end() + 220]
                hallados.append({"fecha": m.group(1).replace("/", "-"), "hora": m.group(2), "frase": frase,
                                 "menciona_par_o_token": base in frase or base in body[m.end(): m.end() + 600]})
        res["fuentes"].append({"url": u, "archivo": arch, "warc": d.get("url_archivada"), "captura": d.get("captura"), "hallazgos": hallados[:6]})
    out.append(res)
json.dump(out, open(SAL, "w"), ensure_ascii=False, indent=1)
for r in out:
    fechas = sorted({h["fecha"] for s in r["fuentes"] for h in s["hallazgos"]})
    print(f"{r['par']:14s} E1={r['E_pasada1']} {r['categoria_pasada1']:28s} texto={fechas}")
