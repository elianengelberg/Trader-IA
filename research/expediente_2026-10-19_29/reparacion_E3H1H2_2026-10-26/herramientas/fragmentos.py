"""Imprime fragmentos alrededor de palabras clave de una página archivada (solo lectura).
Uso: fragmentos.py <dir_E3> <subcadena_titulo_o_url> <clave1> [<clave2> ...]"""
import glob, json, re, sys, datetime as dt
E3, q, claves = sys.argv[1], sys.argv[2], sys.argv[3:]
vistos = set()
for f in sorted(glob.glob(f"{E3}/datos_anuncios/commoncrawl/paginas/*.json")):
    d = json.load(open(f))
    if q not in d.get("titulo", "") and q not in d.get("url", ""): continue
    t = re.sub(r"\s+", " ", d.get("texto", "")); i = t.find("Fellow"); t = t[i:] if i >= 0 else t
    if t[:3000] in vistos: continue
    vistos.add(t[:3000])
    pub = dt.datetime.fromtimestamp(int(d["publicado_ms"]) / 1000, dt.UTC).date() if str(d.get("publicado_ms") or "").isdigit() else d.get("publicado_ms")
    print(f"== {d['titulo']}\n   url: {d['url']}\n   warc: {d.get('url_archivada','')[:160]}\n   captura {d.get('captura')} · publicado {pub} · archivo {f.split('/')[-1]}")
    for k in claves:
        for m in re.finditer(re.escape(k), t):
            print(f"   [{k}] …{t[max(0, m.start() - 80):m.start() + 300]}…")
    print()
