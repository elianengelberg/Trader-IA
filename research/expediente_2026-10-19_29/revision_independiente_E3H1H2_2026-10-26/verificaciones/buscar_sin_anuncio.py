"""Busca en las 8028 páginas archivadas cualquier rastro de los cambios de símbolo no mapeados: páginas que nombran al
viejo y al nuevo, o que mencionan al nuevo con palabras de canje. Solo textos. Uso: python -I buscar_sin_anuncio.py <dir_E3> <salida.json>"""
import json, re, sys
from pathlib import Path
E3, SAL = Path(sys.argv[1]), Path(sys.argv[2])
PARES = [("TOMO", "VIC"), ("GAL", "G"), ("RNDR", "RENDER"), ("KLAY", "KAIA"), ("DAR", "D"), ("FTM", "S"), ("EOS", "A"),
         ("MKR", "SKY"), ("FXS", "FRAX"), ("OM", "MANTRA"), ("AGIX", "FET"), ("OCEAN", "FET"), ("BNX", "FOUR"), ("LUNA", "LUNC"), ("VIDT", "VIDT")]
CLAVE = re.compile(r"swap|rebrand|renam|migrat|ticker|redenominat|merger|convert", re.I)
pags = []
for f in sorted((E3 / "datos_anuncios/commoncrawl/paginas").glob("*.json")):
    d = json.loads(f.read_text()); t = re.sub(r"\s+", " ", d.get("texto", ""))
    i = t.find("Fellow"); cuerpo = t[i:i + 8000] if i >= 0 else ""
    pags.append((f.name, d.get("titulo", ""), cuerpo, d.get("publicado_ms")))
res = {}
for v, n in PARES:
    rv = re.compile(rf"(?<![A-Za-z0-9]){v}(?![A-Za-z0-9])"); rn = re.compile(rf"(?<![A-Za-z0-9]){n}(?:/USDT|USDT|\)|/)")
    hits = []
    for a, ti, c, pub in pags:
        if not c:
            continue
        if rv.search(c) and rn.search(c) and CLAVE.search(c):
            m = CLAVE.search(c)
            hits.append({"archivo": a, "titulo": ti[:110], "frag": c[max(0, m.start() - 150):m.start() + 200]})
    res[f"{v}->{n}"] = hits
SAL.write_text(json.dumps(res, ensure_ascii=False, indent=1))
for k, h in res.items():
    print(k, len(h))
    for x in h[:4]:
        print("    ", x["titulo"], "||", x["frag"][:260].replace("\n", " "))
