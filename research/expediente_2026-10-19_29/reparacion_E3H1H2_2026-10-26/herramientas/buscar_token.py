"""Busca un token en todas las páginas archivadas locales: títulos que lo nombran y menciones de pares XYZ/QQQ o XYZQQQ.
Uso: buscar_token.py <dir_E3> <TOKEN> [<nombre largo>]"""
import glob, json, re, sys
E3, T = sys.argv[1], sys.argv[2]; nombre = sys.argv[3] if len(sys.argv) > 3 else None
rx_par = re.compile(rf"(?<![A-Z0-9]){T}\s*/\s*([A-Z]{{2,6}})(?![A-Z])|(?<![A-Z0-9]){T}(USDT|BTC|BNB|ETH|BUSD|TRY|FDUSD|EUR)(?![A-Z])")
rx_tok = re.compile(rf"\({T}\)|(?<![A-Z0-9]){T}(?![A-Za-z0-9])")
tit, pares = [], set()
for f in glob.glob(f"{E3}/datos_anuncios/commoncrawl/paginas/*.json"):
    d = json.load(open(f)); t = d.get("texto", ""); ti = d.get("titulo", "")
    if rx_tok.search(ti) or (nombre and nombre in ti): tit.append((str(d.get("publicado_ms"))[:10], ti[:120]))
    i = t.find("Fellow"); body = t[i:i + 6000] if i >= 0 else t[:6000]
    for m in rx_par.finditer(body): pares.add(m.group(0).replace(" ", ""))
print(f"== {T}: títulos que lo nombran ({len(set(tit))}):"); [print("   ", x[1]) for x in sorted(set(tit))[:14]]
print(f"   pares mencionados en cuerpos: {sorted(pares)[:20]}")
