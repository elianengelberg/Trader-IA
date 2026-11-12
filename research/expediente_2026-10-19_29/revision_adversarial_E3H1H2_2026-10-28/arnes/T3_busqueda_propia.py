"""Revisión adversarial · T-3: búsqueda propia de renombres, con un método distinto de los del autor.
Método: en cada página, oraciones con vocabulario de canje (swap, rebrand, renam, redenominat, ticker, migrat, convert,
upgrade) y un patrón «(X) … to|into|as|with … (Y)». Se quedan los pares X ≠ Y con XUSDT y/o YUSDT entre los símbolos del
panel (nombres de archivo de las series; NO se abren las series). Se comparan con la tabla y con los 117 pares del autor.
Uso: python -B -I T3_busqueda_propia.py <paginas> <simbolos_panel.txt> <TABLA.json> <clasificacion_barrido.json> <salida.json>"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PAG, SYMS, TABLA, CLAS, SAL = (Path(a) for a in sys.argv[1:6])
panel = set(SYMS.read_text().split())
VOC = re.compile(r"swap|rebrand|renam|redenominat|ticker|migrat|convert|upgrade", re.I)
PAR = re.compile(r"\(\s*([A-Z0-9]{2,12})\s*\)[^.()]{0,90}?\b(?:to|into|as|with|=)\b[^.()]{0,60}?\(\s*([A-Z0-9]{2,12})\s*\)")
tabla = json.loads(TABLA.read_text())["tabla"]
en_tabla = {(t["viejo_usdt"][:-4], (t["nuevo_usdt"] or t["viejo_usdt"])[:-4]) for t in tabla}
clas = json.loads(CLAS.read_text())
en_clas = {(c.get("viejo"), c.get("nuevo")) for c in clas} if isinstance(clas, list) else set()
hall = defaultdict(set)
for p in sorted(PAG.iterdir()):
    t = re.sub(r"\s+", " ", json.loads(p.read_text()).get("texto", ""))
    for oracion in re.split(r"(?<=[.!?])\s", t):
        if not VOC.search(oracion):
            continue
        for x, y in PAR.findall(oracion):
            if x != y and (x + "USDT" in panel or y + "USDT" in panel):
                hall[(x, y)].add(p.name)
nuevos = {f"{x}->{y}": {"XUSDT_en_panel": x + "USDT" in panel, "YUSDT_en_panel": y + "USDT" in panel, "paginas": sorted(v)[:3]}
          for (x, y), v in sorted(hall.items()) if (x, y) not in en_tabla and (x, y) not in en_clas}
res = {"pares_hallados": len(hall), "en_tabla": sum(k in en_tabla for k in hall), "en_los_117": sum(k in en_clas for k in hall),
       "no_vistos_por_el_autor": nuevos}
SAL.write_text(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != "no_vistos_por_el_autor"}, ensure_ascii=False))
for k, v in nuevos.items():
    print(k, v["XUSDT_en_panel"], v["YUSDT_en_panel"], v["paginas"][0])
