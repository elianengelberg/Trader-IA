"""Páginas archivadas con título no legible (CSS u otro) y cómo las clasificó la extracción. Solo textos.
Uso: python -I titulos_rotos.py <dir_E3> <salida.json>"""
import json, re, sys, collections
from pathlib import Path
E3, SAL = Path(sys.argv[1]), Path(sys.argv[2])
CC = E3 / "datos_anuncios/commoncrawl"
cl = {c["url"]: c for c in json.loads((CC / "anuncios_clasificados.json").read_text())}
rotas = []
for f in sorted((CC / "paginas").glob("*.json")):
    d = json.loads(f.read_text()); ti = d.get("titulo", "") or ""
    if ti.startswith(".css") or "{" in ti[:80] or not ti.strip():
        t = re.sub(r"\s+", " ", d.get("texto", ""))
        c = cl.get(d["url"], {})
        # título real: el h1 suele repetirse en el texto antes de «Fellow»
        i = t.find("Fellow")
        rotas.append({"archivo": f.name, "url": d["url"], "tipo_extraccion": c.get("tipo"), "titulo_clasificado": (c.get("titulo") or "")[:80],
                      "cuerpo_extraido_len": len(c.get("cuerpo") or ""), "antes_de_fellow": t[max(0, i - 220):i][-220:] if i >= 0 else t[:200],
                      "texto": t})
print("páginas con título roto:", len(rotas), collections.Counter(r["tipo_extraccion"] for r in rotas))
rx = re.compile(r"(remove and cease trading|delist and cease trading|will delist|cease trading|will remove)", re.I)
sospechosas = []
for r in rotas:
    i = r["texto"].find("Fellow")
    cuerpo = r["texto"][i:i + 6000] if i >= 0 else ""
    m = rx.search(cuerpo)
    usdt = sorted(set(re.findall(r"\b([A-Z0-9]{2,12})/USDT\b", cuerpo)))
    if m:
        sospechosas.append({k: r[k] for k in ("archivo", "url", "tipo_extraccion", "cuerpo_extraido_len")} |
                           {"frag": cuerpo[max(0, m.start() - 120):m.start() + 380], "pares_usdt_en_cuerpo": usdt[:20]})
print("con lenguaje de exclusión en el cuerpo:", len(sospechosas))
for s in sospechosas:
    print("-", s["archivo"][:70], "| tipo:", s["tipo_extraccion"], "| cuerpo_ext:", s["cuerpo_extraido_len"], "| USDT:", s["pares_usdt_en_cuerpo"][:8])
    print("     ", s["frag"][:330])
SAL.write_text(json.dumps({"n_rotas": len(rotas), "rotas": [{k: v for k, v in r.items() if k != "texto"} for r in rotas],
                           "con_exclusion": sospechosas}, ensure_ascii=False, indent=1))
