"""Exclusiones de pares spot USDT en las páginas que la extracción congelada no pudo leer (título no legible).
Cuerpo según A3.1.1: desde «Fellow Binancians» hasta la primera marca de cierre; sin barras laterales. Solo textos.
Uso: python -I paginas_no_extraidas.py <dir_E3> <salida.json>"""
import json
import re
import sys
from pathlib import Path

E3, SAL = Path(sys.argv[1]), Path(sys.argv[2])
CC = E3 / "datos_anuncios/commoncrawl"
FIN = ("Thanks for your support", "Binance Team", "Related Articles", "Find us on Telegram", "Latest Articles", "Risk warning", "Risk Warning")
EXCL = re.compile(r"(delist and cease trading|remove and cease trading|will delist all existing|will delist the|halt trading|cease trading|"
                  r"suspend and delist|delist all|will remove)", re.I)
NO_SPOT = re.compile(r"margin|futures|perpetual|isolated|cross|borrow|P2P|staking|savings|Convert|Liquid Swap|Gift Card|Pay\b|bots?\b|Earn",
                     re.I)
FECHA = re.compile(r"(20\d\d)[-/](\d\d)[-/](\d\d)")


def cuerpo(t):
    i = t.find("Fellow Binancians")
    if i < 0:
        return ""
    c = t[i:]
    j = min([c.find(m) for m in FIN if c.find(m) > 0] or [len(c)])
    return c[:j]


out = []
n = 0
for f in sorted((CC / "paginas").glob("*.json")):
    d = json.loads(f.read_text())
    ti = d.get("titulo", "") or ""
    if not (ti.startswith(".css") or "{" in ti[:80] or not ti.strip()):
        continue
    n += 1
    c = re.sub(r"\s+", " ", cuerpo(re.sub(r"\s+", " ", d.get("texto", ""))))
    for s in re.split(r"(?<=[.!?])\s+", c):
        if not EXCL.search(s):
            continue
        pares = sorted(set(re.findall(r"\b([A-Z0-9]{2,15})/USDT\b", s)) | set(re.findall(r"\b([A-Z0-9]{2,15})USDT\b", s)))
        fechas = ["-".join(m) for m in FECHA.findall(s)]
        out.append({"archivo": f.name, "url": d["url"], "captura": d.get("captura"), "frase": s[:600], "pares_usdt": pares,
                    "fechas": fechas, "no_spot": bool(NO_SPOT.search(s))})
SAL.write_text(json.dumps({"paginas_titulo_roto": n, "frases": out}, ensure_ascii=False, indent=1))
print("páginas:", n, "· frases de exclusión:", len(out), "· con pares USDT:", sum(1 for o in out if o["pares_usdt"]))
relev = [o for o in out if o["pares_usdt"] and any(x >= "2023-04-28" for x in o["fechas"])]
print("con pares USDT y alguna fecha ≥ 2023-04-28:", len(relev))
for o in relev:
    print(f"- {o['archivo'][:60]} | no_spot={o['no_spot']} | {o['pares_usdt'][:10]} | {o['fechas'][:4]}\n    {o['frase'][:420]}")
sin_fecha = [o for o in out if o["pares_usdt"] and not o["fechas"]]
print("con pares USDT y sin fecha en la frase:", len(sin_fecha))
fechas_todas = sorted({x for o in out if o["pares_usdt"] for x in o["fechas"]})
print("rango de fechas con pares USDT:", fechas_todas[:1], fechas_todas[-3:])
