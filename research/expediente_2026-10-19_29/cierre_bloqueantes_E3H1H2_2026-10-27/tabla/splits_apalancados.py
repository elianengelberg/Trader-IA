"""Empareja cada corte con reanudación de un token apalancado (sufijo UP/DOWN/BULL/BEAR) con los cuerpos archivados de
reverse split: el anuncio («will undergo a N-for-1 reverse token split», con fecha de inicio) y la finalización
(«resume trading activity for X/USDT at FECHA»). Solo textos y actividad. Uso: python -I splits_apalancados.py <dir_E3> <salida.json>"""
import datetime as dt, json, re, sys
from pathlib import Path
E3, SAL = Path(sys.argv[1]), Path(sys.argv[2])
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())}
cuerpos = []
for f in sorted((E3 / "datos_anuncios/commoncrawl/paginas").glob("*.json")):
    d = json.loads(f.read_text())
    t = re.sub(r"\s+", " ", d.get("texto", ""))
    i = t.find("Fellow Binancians")
    if i < 0:
        continue
    c = t[i:]
    j = min([c.find(x) for x in ("Thanks for your support", "Binance Team") if c.find(x) > 0] or [len(c)])
    c = c[:j]
    if re.search(r"token split", c, re.I):
        cuerpos.append((f.name, str(d.get("captura", ""))[:8], c))
out = []
for s, a in sorted(aud.items()):
    b = s[:-4]
    if not re.search(r"(UP|DOWN|BULL|BEAR)$", b):
        continue
    for L, F, n in a["cortes_con_reanudacion"]:
        e_ini = dt.date.fromisoformat(L) + dt.timedelta(days=1)
        anuncio, fin = None, None
        for nombre, cap, c in cuerpos:
            if not re.search(r"\b" + b + r"\b", c):
                continue
            m = re.search(r"(\d[\d,]*)-for-1 reverse token split(?:, starting at (20\d\d-\d\d-\d\d))?", c)
            fechas = set(re.findall(r"20\d\d-\d\d-\d\d", c))
            if m and (e_ini.isoformat() in fechas or F in fechas) and "postpone" not in c.lower():
                anuncio = anuncio or {"archivo": nombre, "captura": cap, "relacion_N_por_1": int(m.group(1).replace(",", "")),
                                      "cita": m.group(0), "fechas": sorted(fechas)}
            r = re.search(r"resume trading activity for [^.]*\b" + b + r"/USDT[^.]* at (20\d\d-\d\d-\d\d)", c)
            if r and r.group(1) == F:
                fin = fin or {"archivo": nombre, "captura": cap, "cita": r.group(0)[:200]}
        out.append({"simbolo": s, "ultimo_activo": L, "reanuda": F, "anuncio": anuncio, "finalizacion": fin})
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1))
for o in out:
    an, fi = o["anuncio"], o["finalizacion"]
    print(f"{o['simbolo']:<14} {o['ultimo_activo']} → {o['reanuda']}  N={an and an['relacion_N_por_1']}  "
          f"anuncio={'sí' if an else 'NO'}  finalización={'sí' if fi else 'NO'}  | {(an or {}).get('cita', '')[:70]}")
