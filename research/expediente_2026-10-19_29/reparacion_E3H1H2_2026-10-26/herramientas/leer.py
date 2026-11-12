"""Lee páginas archivadas locales de E3 (solo lectura). Uso: leer.py <dir_E3> <subcadena_titulo_o_url> [n_caracteres]
Imprime título, url, url_archivada (WARC), captura, publicación y el cuerpo limpio desde «Fellow»."""
import glob, json, re, sys, datetime as dt
E3, q = sys.argv[1], sys.argv[2]; n = int(sys.argv[3]) if len(sys.argv) > 3 else 1800
vistos = set()
for f in sorted(glob.glob(f"{E3}/datos_anuncios/commoncrawl/paginas/*.json")):
    d = json.load(open(f))
    if q not in d.get("titulo", "") and q not in d.get("url", ""): continue
    t = re.sub(r"\s+", " ", d.get("texto", "")); i = t.find("Fellow"); cuerpo = t[i:i + n] if i >= 0 else t[:n]
    if cuerpo in vistos: continue
    vistos.add(cuerpo)
    pub = dt.datetime.fromtimestamp(int(d["publicado_ms"]) / 1000, dt.UTC).date() if str(d.get("publicado_ms") or "").isdigit() else d.get("publicado_ms")
    print(f"== {d['titulo']}\n   url: {d['url']}\n   warc: {d.get('url_archivada','')[:150]} · captura {d.get('captura')} · publicado {pub} · archivo {f.split('/')[-1]}\n   {cuerpo}\n")
