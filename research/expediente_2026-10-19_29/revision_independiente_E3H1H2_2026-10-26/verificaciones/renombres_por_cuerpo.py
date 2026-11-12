"""Barrido de renombres/redenominaciones por CUERPO en las páginas que NO son candidatas de renombre (cualquier título).
Busca relaciones de canje y cambios de ticker; lista los símbolos con par USDT en el bucket y fechas. Solo textos.
Uso: python -I renombres_por_cuerpo.py <dir_E3> <mapeos_adenda1.json> <salida.json>"""
import json, re, sys
from pathlib import Path
E3, MAP, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CC = E3 / "datos_anuncios/commoncrawl"
cand = {r["url"] for r in json.loads((CC / "renombres_candidatos.json").read_text())}
usdt = set(json.loads((E3 / "datos_vision/listados/simbolos_usdt.json").read_text()))
mapeados = {m["viejo_usdt"][:-4] for m in json.loads(MAP.read_text())["mapeos"]}
FIN = ("Thanks for your support", "Binance Team", "Latest Articles", "Related Articles")
PATS = [re.compile(r"ratio of (?:1 )?([\d,]+) (?:old )?([A-Z0-9]{2,12})(?: \(Old\))? = ([\d,]+) (?:new )?([A-Z0-9]{2,12})"),
        re.compile(r"(?:update|change) the ticker of ([A-Z0-9]{2,12}) to ([A-Z0-9]{2,12})"),
        re.compile(r"([A-Z0-9]{2,12}) tokens? will assume the ticker of ([A-Z0-9]{2,12})"),
        re.compile(r"old ([A-Z0-9]{2,12}) token has assumed ([A-Z0-9]{2,12}) as the ticker"),
        re.compile(r"\(([A-Z0-9]{2,12})\) [^.]{0,60}(?:rebranding|rebrand|renaming|token swap)[^.]{0,40} to [^.(]{0,40}\(([A-Z0-9]{2,12})\)")]
FECHA = re.compile(r"(20\d\d)[-/](\d\d)[-/](\d\d)")
hall = {}
for f in sorted((CC / "paginas").glob("*.json")):
    d = json.loads(f.read_text())
    if d["url"] in cand:
        continue
    t = re.sub(r"\s+", " ", d.get("texto", "")); i = t.find("Fellow Binancians")
    if i < 0:
        continue
    c = t[i:]; js = [c.find(m) for m in FIN if c.find(m) > 0]; c = c[:min(js)] if js else c
    fechas = sorted({"-".join(m) for m in FECHA.findall(c)})
    for rx in PATS:
        for m in rx.finditer(c):
            g = [x for x in m.groups() if re.fullmatch(r"[A-Z][A-Z0-9]{1,11}", x or "")]
            if len(g) < 2:
                continue
            viejo, nuevo = g[0], g[-1]
            if viejo == nuevo and "ratio" not in m.group(0):
                continue
            k = (viejo, nuevo)
            h = hall.setdefault(f"{viejo}->{nuevo}", {"frag": m.group(0)[:200], "archivos": [], "fechas": set(),
                                                    "viejo_usdt_en_bucket": viejo + "USDT" in usdt, "nuevo_usdt_en_bucket": nuevo + "USDT" in usdt,
                                                    "en_tabla_de_22": viejo in mapeados})
            h["archivos"].append(f.name); h["fechas"] |= set(fechas)
out = {k: {**v, "fechas": sorted(v["fechas"]), "archivos": sorted(set(v["archivos"]))[:3]} for k, v in hall.items()}
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1))
for k, v in sorted(out.items()):
    if not (v["viejo_usdt_en_bucket"] or v["nuevo_usdt_en_bucket"]):
        continue
    rel = [x for x in v["fechas"] if "2017" < x < "2027"]
    print(f"{k:<20} tabla22={v['en_tabla_de_22']!s:<5} usdt(v/n)={v['viejo_usdt_en_bucket']}/{v['nuevo_usdt_en_bucket']} "
          f"fechas={rel[:1]}…{rel[-1:]} | {v['frag'][:110]}")
