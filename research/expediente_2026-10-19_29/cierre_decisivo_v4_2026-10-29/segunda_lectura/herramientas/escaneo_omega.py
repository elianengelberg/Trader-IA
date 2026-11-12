"""Segunda lectura (protocolo SL-v1, §7.2) · escaneo Ω de remociones de pares spot X/USDT que la extracción pudo omitir.
Regla fija (no se ajusta después de ver la salida):
  1. Páginas: `publicado` ≥ 2023-04-01, o sin `publicado`.
  2. Texto: el campo `texto` completo (incluye barra lateral: se prefiere recall a precisión).
  3. Ocurrencias de par: «X/USDT» y «XUSDT» (X = 2–15 caracteres [A-Z0-9]).
  4. Contexto: 250 caracteres antes y después. Es candidato si el contexto contiene remoción:
     delist | remov | cease | ceasing | discontinu | no longer.
  5. Se descarta el candidato si el par ya tiene un evento conocido en ESA página (eventos de la primera pasada, omitidos
     de la reparación). Un par conocido en otra página sigue siendo candidato.
  6. Etiquetas, sin filtrar: FUT (perpetual, futures, USDⓈ-M, COIN-M, quarterly, delivery), MARGEN (margin), OTRO
     (trading bot, copy trading, earn, loan, convert, auto-invest).
Salida: candidatos por (par, página) con el primer contexto, y conteos. No lee precios.
Uso: python3 -I -B escaneo_omega.py <dir_ejecucion_E3> <eventos_omitidos_reparacion.json> <salida.json>"""
import hashlib
import json
import re
import sys
from pathlib import Path

E3, OMIT, SAL = (Path(a) for a in sys.argv[1:4])
CC = E3 / "datos_anuncios" / "commoncrawl"
PAR = re.compile(r"\b([A-Z0-9]{2,15})\s*/\s*USDT\b|\b([A-Z0-9]{2,15})USDT\b")
REM = re.compile(r"delist|remov|cease|ceasing|discontinu|no longer", re.I)
TAGS = {"FUT": re.compile(r"perpetual|futures|USDⓈ-M|COIN-M|quarterly|delivery", re.I), "MARGEN": re.compile(r"margin", re.I),
        "OTRO": re.compile(r"trading bot|copy trading|earn|loan|convert|auto-invest", re.I)}

anuncios = json.loads((CC / "anuncios_clasificados.json").read_text())
eventos1 = json.loads((E3 / "resultados" / "conciliacion_pasada1" / "eventos.json").read_text())
por_url = {}
for a in anuncios:
    por_url.setdefault(a["url"], []).append(a["archivo"])
conocidos = {(e["par"], f) for e in eventos1 for u in e["urls"] for f in por_url.get(u, [])}
for o in json.loads(OMIT.read_text()):
    conocidos.add((o["par"], Path(o["fuente"].split(" ")[0]).name))

paginas = [a for a in anuncios if (a.get("publicado") or "9999") >= "2023-04-01"]
cand, vistos = [], set()
for a in sorted(paginas, key=lambda x: x["archivo"]):
    p = CC / "paginas" / a["archivo"]
    texto = json.loads(p.read_text())["texto"] or ""
    for m in PAR.finditer(texto):
        par = (m.group(1) or m.group(2)) + "USDT"
        ctx = texto[max(0, m.start() - 250):m.end() + 250]
        if not REM.search(ctx) or (par, a["archivo"]) in conocidos or (par, a["archivo"]) in vistos:
            continue
        vistos.add((par, a["archivo"]))
        cand.append({"par": par, "archivo": a["archivo"], "sha256_pagina": hashlib.sha256(p.read_bytes()).hexdigest(),
                     "titulo": a["titulo"], "publicado": a.get("publicado"), "tipo_extraccion": a["tipo"],
                     "etiquetas": [k for k, r in TAGS.items() if r.search(ctx)], "contexto": ctx})
res = {"regla": "SL-v1 §7.2", "paginas_escaneadas": len(paginas), "candidatos": len(cand),
       "candidatos_sin_etiqueta": sum(1 for c in cand if not c["etiquetas"]), "lista": cand}
SAL.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps({k: res[k] for k in ("paginas_escaneadas", "candidatos", "candidatos_sin_etiqueta")}))
