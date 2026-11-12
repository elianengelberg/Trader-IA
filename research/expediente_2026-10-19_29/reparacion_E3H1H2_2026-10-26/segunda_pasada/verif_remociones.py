import json, sys, re
E3 = sys.argv[1]; A = f"{E3}/datos_anuncios/commoncrawl"
cl = json.load(open(f"{A}/anuncios_clasificados.json"))
print("== 1) avisos de remoción y exclusión con fecha ≥ 2023-04-28: pares X/USDT en el cuerpo")
for c in sorted(cl, key=lambda c: (c.get("fecha_efectiva") or c.get("publicado") or "")):
    f = c.get("fecha_efectiva") or c.get("publicado") or ""
    if c["tipo"] != "exclusion" or f < "2023-04-28": continue
    body = c.get("cuerpo") or ""
    usdt = sorted(set(re.findall(r"\b([A-Z0-9]{2,15})\s*/\s*USDT\b", body)))
    print(f"  {f} {c['titulo'][:70]:70s} | X/USDT en cuerpo: {usdt}")
print("\n== 2) páginas NO clasificadas como exclusión cuyo título sugiere exclusión/remoción/cese, publicadas ≥ 2023-01-01")
pat = re.compile(r"delist|remov|cease|discontinu|suspend trading|halt", re.I)
for c in sorted(cl, key=lambda c: (c.get("publicado") or "")):
    if c["tipo"] == "exclusion" or (c.get("publicado") or "") < "2023-01-01": continue
    if pat.search(c["titulo"]):
        body = c.get("cuerpo") or ""
        usdt = sorted(set(re.findall(r"\b([A-Z0-9]{2,15})\s*/\s*USDT\b", body)))[:12]
        print(f"  {c.get('publicado')} [{c['tipo']}] {c['titulo'][:95]} | X/USDT: {usdt}")
