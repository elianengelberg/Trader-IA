"""Tercer control, guiado por actividad: para cada símbolo Y del panel cuyo episodio empieza ≤ 60 días después del fin
de un episodio de X (X ≠ Y), busca un cuerpo archivado (A3.1.1) que nombre «(X)» y «(Y)» con palabras de canje o
cambio de ticker. También: para cada corte con reanudación del mismo símbolo, un cuerpo con «(X)» y redenominación o
relación. Solo episodios, cortes y textos; ningún precio. Uso: python -I barrido_por_actividad.py <dir_E3> <salida.json>"""
import datetime as dt, json, re, sys
from pathlib import Path
E3, SAL = Path(sys.argv[1]), Path(sys.argv[2])
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())}
SALUDO = ("Fellow Binancians", "Dear Binancians", "Dear Valued", "Dear users", "Dear Users")
FIN = ("Thanks for your support", "Binance Team", "Related Articles", "Find us on Telegram", "Latest Articles")
CLAVE = re.compile(r"token swap|redenominat|rebrand|renam|ticker|migrat|conversion|mainnet swap|swap", re.I)
RED = re.compile(r"redenominat|ratio|reverse split|split", re.I)
d = dt.date.fromisoformat
cuerpos = []
for f in sorted((E3 / "datos_anuncios/commoncrawl/paginas").glob("*.json")):
    t = re.sub(r"\s+", " ", json.loads(f.read_text()).get("texto", ""))
    i = min((t.find(s) for s in SALUDO if t.find(s) >= 0), default=-1)
    if i < 0:
        continue
    c = t[i:]
    js = [c.find(m) for m in FIN if c.find(m) > 0]
    c = c[:min(js)] if js else c
    if CLAVE.search(c):
        cuerpos.append((f.name, c, set(re.findall(r"\(([A-Z0-9]{2,12})\)", c))))
fines = [(s, d(fin)) for s, a in aud.items() for ini, fin in a["episodios"]]
inicios = [(s, d(ini)) for s, a in aud.items() for ini, fin in a["episodios"]]
pares, vistos = [], set()
for y, F in inicios:
    for x, L in fines:
        if x == y or not (0 <= (F - L).days <= 60):
            continue
        bx, by = x[:-4], y[:-4]
        hits = [n for n, c, toks in cuerpos if bx in toks and by in toks]
        if hits and (bx, by) not in vistos:
            vistos.add((bx, by))
            pares.append({"viejo": x, "fin_viejo": L.isoformat(), "nuevo": y, "inicio_nuevo": F.isoformat(), "archivos": hits[:5]})
cortes = []
for s, a in aud.items():
    for c in a["cortes_con_reanudacion"]:
        b = s[:-4]
        hits = [n for n, cu, toks in cuerpos if b in toks and RED.search(cu)]
        cortes.append({"simbolo": s, "corte": c, "archivos_con_redenominacion": hits[:6]})
SAL.write_text(json.dumps({"pares_actividad_con_cuerpo_comun": pares, "cortes": cortes}, ensure_ascii=False, indent=1))
print("pares por actividad con cuerpo común:", len(pares))
for p in pares:
    print(f"  {p['viejo']:<12} fin {p['fin_viejo']} → {p['nuevo']:<12} inicio {p['inicio_nuevo']} | {p['archivos'][0][:70]}")
print("cortes con reanudación:", len(cortes))
for c in cortes:
    print(f"  {c['simbolo']:<14} {c['corte']} · cuerpos con (X)+redenominación/relación: {len(c['archivos_con_redenominacion'])}")
