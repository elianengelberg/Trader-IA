"""Escaneo de completitud para la ventana A: en el CUERPO (A3.1.1) de las 8028 páginas, toda frase de exclusión spot con
una fecha ≥ 2023-04-28, con los pares USDT o tokens que nombra. Se cruza con los eventos de la segunda pasada y con el
listado del bucket. Solo textos y listados; ningún precio. Uso: python -I escaneo_exclusiones_en_A.py <dir_E3> <eventos_pasada2.json> <salida.json>"""
import json
import re
import sys
from pathlib import Path

E3, EV, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CC = E3 / "datos_anuncios/commoncrawl"
usdt = set(json.loads((E3 / "datos_vision/listados/simbolos_usdt.json").read_text()))
eventos = {(e["par"], e["E"]) for e in json.loads(EV.read_text())}
pares_con_evento = {e[0] for e in eventos}
FIN = ("Thanks for your support", "Binance Team", "Related Articles", "Find us on Telegram", "Latest Articles")
EXCL = re.compile(r"(delist and cease trading|remove and cease trading|will delist all existing|suspend and delist|"
                  r"delist and cease trading on all|cease trading on|will delist the following|halt trading)", re.I)
NO_SPOT = re.compile(r"\bmargin\b|futures|perpetual|isolated|cross margin|borrow|P2P|Convert\b|Liquid Swap|Trading Bots|Copy Trading|"
                     r"Gift Card|Simple Earn|Binance Pay|VIP Loan|Auto-Invest|leveraged token", re.I)
FECHA = re.compile(r"(20\d\d)[-/](\d\d)[-/](\d\d)")
TOKEN = re.compile(r"\(([A-Z0-9]{2,12})\)")


def cuerpo(t):
    i = t.find("Fellow Binancians")
    if i < 0:
        return ""
    c = t[i:]
    js = [c.find(m) for m in FIN if c.find(m) > 0]
    return c[:min(js)] if js else c


hall = []
for f in sorted((CC / "paginas").glob("*.json")):
    d = json.loads(f.read_text())
    c = re.sub(r"\s+", " ", cuerpo(re.sub(r"\s+", " ", d.get("texto", ""))))
    if not c:
        continue
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", c):
        if not EXCL.search(s):
            continue
        fechas = ["-".join(m) for m in FECHA.findall(s)]
        if not any(x >= "2023-04-28" for x in fechas):
            continue
        pares = sorted(set(re.findall(r"\b([A-Z0-9]{2,15})/USDT\b", s)))
        toks = sorted(set(TOKEN.findall(s)) - {"UTC"})
        hall.append({"archivo": f.name, "titulo": (d.get("titulo") or "")[:100], "captura": d.get("captura"), "fechas": fechas,
                     "no_spot": bool(NO_SPOT.search(s)), "pares_usdt": pares, "tokens": toks, "frase": s[:500]})
# cruce
for h in hall:
    candidatos = {p + "USDT" for p in h["pares_usdt"]} | {t + "USDT" for t in h["tokens"]}
    h["en_bucket"] = sorted(c for c in candidatos if c in usdt)
    h["sin_evento_pasada2"] = sorted(c for c in h["en_bucket"] if c not in pares_con_evento)
SAL.write_text(json.dumps(hall, ensure_ascii=False, indent=1))
spot = [h for h in hall if not h["no_spot"]]
print("frases de exclusión con fecha ≥ 2023-04-28:", len(hall), "· spot:", len(spot))
vistos = set()
for h in spot:
    k = (h["frase"][:160])
    if k in vistos:
        continue
    vistos.add(k)
    print(f"- {h['fechas'][:3]} bucket={h['en_bucket'][:8]} SIN_EVENTO={h['sin_evento_pasada2'][:8]} | {h['titulo'][:70]}\n    {h['frase'][:300]}")
