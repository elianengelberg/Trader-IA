"""Imprime, para cada token pedido, los cuerpos archivados (A3.1.1) que lo nombran «(TOKEN)» o «TOKEN/USDT» junto a
palabras de canje, redenominación, cambio de ticker o retiro, más su actividad (episodios y cortes). Solo textos y
actividad. Uso: python -I evidencia_tokens.py <dir_E3> <salida.json> TOKEN [TOKEN …]"""
import json, re, sys
from pathlib import Path
E3, SAL, TOKS = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())}
SALUDO = ("Fellow Binancians", "Dear Binancians", "Dear Valued", "Dear users", "Dear Users")
FIN = ("Thanks for your support", "Binance Team", "Related Articles", "Find us on Telegram", "Latest Articles")
CLAVE = re.compile(r"swap|redenominat|rebrand|renam|ticker|migrat|conver|split|delist|remov|suspend|cease|airdrop|distribut", re.I)
cuerpos = []
for f in sorted((E3 / "datos_anuncios/commoncrawl/paginas").glob("*.json")):
    d = json.loads(f.read_text())
    t = re.sub(r"\s+", " ", d.get("texto", ""))
    i = min((t.find(s) for s in SALUDO if t.find(s) >= 0), default=-1)
    if i < 0:
        continue
    c = t[i:]
    js = [c.find(m) for m in FIN if c.find(m) > 0]
    cuerpos.append((f.name, str(d.get("captura", "")), (d.get("titulo") or "")[:120], c[:min(js)] if js else c, d.get("url", "")))
out = {}
for tk in TOKS:
    rx = re.compile(r"\(" + re.escape(tk) + r"\)|\b" + re.escape(tk) + r"/USDT\b|\b" + re.escape(tk) + r" \(Old\)|\bold " + re.escape(tk) + r"\b")
    hits, vistos = [], set()
    for n, cap, tit, c, url in cuerpos:
        if rx.search(c) and CLAVE.search(c):
            clave = c[:300]
            if clave in vistos:
                continue
            vistos.add(clave)
            hits.append({"archivo": n, "captura": cap, "titulo": tit if not tit.startswith(".css") else "(ilegible)", "url": url, "cuerpo": c[:1600]})
    a = aud.get(tk + "USDT")
    out[tk] = {"actividad": a and {"episodios": a["episodios"], "cortes": a["cortes_con_reanudacion"]}, "cuerpos": hits}
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1))
for tk, v in out.items():
    print(f"=== {tk}  actividad={v['actividad']}  cuerpos={len(v['cuerpos'])}")
