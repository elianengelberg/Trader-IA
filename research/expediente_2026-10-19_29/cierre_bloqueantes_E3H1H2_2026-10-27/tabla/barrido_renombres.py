"""Barrido de renombres, canjes y redenominaciones en el CUERPO de las 8.028 páginas archivadas (no depende del título).
Solo textos y datos de actividad (episodios y cortes de `auditoria_por_simbolo.json`); ningún precio ni volumen.

Detecta, en oraciones del cuerpo con palabras de canje/cambio de ticker:
  - relaciones «N X = M Y», «N X : M Y», «N X (Old) = M Y», «ratio of N:M» (con decimales y separadores de miles);
  - cambios de ticker: «ticker of X to Y», «X … will assume the ticker of Y», «renamed as/to Y», «(X) … rebrand/renam/
    ticker change/token swap/migration … to Nombre (Y)».
Cruza cada par (X, Y) con las 757 series USDT del panel, sus episodios y sus cortes con reanudación.
Uso: python -I barrido_renombres.py <dir_ejecucion_E3> <salida.json>
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

E3, SAL = Path(sys.argv[1]), Path(sys.argv[2])
PAG = E3 / "datos_anuncios/commoncrawl/paginas"
aud = {a["simbolo"]: a for a in json.loads((E3 / "resultados/calidad/auditoria_por_simbolo.json").read_text())}
PANEL = set(aud)
SALUDO = ("Fellow Binancians", "Dear Binancians", "Dear Valued", "Dear users", "Dear Users")
FIN = ("Thanks for your support", "Binance Team", "Related Articles", "Find us on Telegram", "Latest Articles")
CLAVE = re.compile(r"token swap|swap|redenominat|rebrand|renam|ticker|migrat|conver(?:t|sion)|split|consolidat|"
                   r"distribution|distribute|airdrop", re.I)
NUM = r"(\d[\d,]*(?:\.\d+)?)"
TK = r"([A-Z][A-Z0-9]{1,11})"
VIEJO = r"(?:\s*\((?:old|Old|OLD)\))?"
RELACION = [re.compile(NUM + r"\s+(?:old\s+|new\s+)?" + TK + VIEJO + r"\s*(?:=|:)\s*" + NUM + r"\s+(?:old\s+|new\s+)?" + TK),
            re.compile(r"ratio of\s+" + NUM + r"\s*:\s*" + NUM)]
TICKER = [re.compile(r"ticker (?:of )?" + TK + r" (?:will be |has been )?(?:changed |updated )?to " + TK),
          re.compile(TK + r" tokens? will (?:assume|adopt) the (?:new )?ticker (?:of )?" + TK),
          re.compile(r"\(" + TK + r"\)[^.]{0,160}?(?:rebrand\w*|renam\w*|ticker change|token swap|migration|swap)[^.]{0,120}?"
                     r"\bto\b[^.(]{0,60}\(" + TK + r"\)"),
          re.compile(r"(?:old\s+)?" + TK + r"[^.]{0,60}?(?:will be|has been|was|is) (?:renamed|rebranded) (?:as|to) " + TK),
          re.compile(r"old " + TK + r" token has assumed " + TK)]
FECHA = re.compile(r"(20\d\d)[-/](\d\d)[-/](\d\d)")
NO_TOKEN = {"UTC", "USD", "NFT", "API", "KYC", "VIP", "P2P", "ETF", "EEA", "UK", "EU", "FAQ", "AM", "PM", "OTC", "AMA", "DEX",
            "CEX", "BEP", "ERC", "TRC", "SPL", "APR", "APY", "ID", "OLD", "NEW"}


def cuerpo(t):
    i = min((t.find(s) for s in SALUDO if t.find(s) >= 0), default=-1)
    if i < 0:
        return None
    c = t[i:]
    js = [c.find(m) for m in FIN if c.find(m) > 0]
    return c[:min(js)] if js else c


def num(x):
    return float(x.replace(",", ""))


pares = defaultdict(lambda: {"archivos": set(), "frases": [], "relaciones": set(), "fechas": set(), "capturas": set()})
sin_saludo = 0
for f in sorted(PAG.glob("*.json")):
    d = json.loads(f.read_text())
    c = cuerpo(re.sub(r"\s+", " ", d.get("texto", "")))
    if c is None:
        sin_saludo += 1
        continue
    fechas = {"-".join(m) for m in FECHA.findall(c)}
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", c):
        if not CLAVE.search(s):
            continue
        hall = []
        for rx in RELACION[:1]:
            for m in rx.finditer(s):
                a, x, b, y = m.groups()
                if x in NO_TOKEN or y in NO_TOKEN:
                    continue
                try:
                    hall.append((x, y, num(b) / num(a), m.group(0)))
                except (ValueError, ZeroDivisionError):
                    pass
        for rx in TICKER:
            for m in rx.finditer(s):
                x, y = m.groups()[0], m.groups()[-1]
                if x != y and x not in NO_TOKEN and y not in NO_TOKEN:
                    hall.append((x, y, None, m.group(0)))
        rat = [(num(a), num(b)) for a, b in RELACION[1].findall(s)]
        if rat:
            toks = [t for t in re.findall(r"\(" + TK + r"\)", s) if t not in NO_TOKEN]
            for t in set(toks):
                hall.append((t, t, None, f"ratio of {rat[0][0]:g}:{rat[0][1]:g} [{s[:160]}]"))
        for x, y, r, frag in hall:
            p = pares[(x, y)]
            p["archivos"].add(f.name)
            p["capturas"].add(str(d.get("captura", ""))[:8])
            p["fechas"] |= fechas
            if r is not None:
                p["relaciones"].add(round(r, 10))
            if len(p["frases"]) < 4 and frag not in p["frases"]:
                p["frases"].append(frag[:300])


def act(s):
    a = aud.get(s)
    return None if a is None else {"episodios": a["episodios"], "cortes": a["cortes_con_reanudacion"]}


out = []
for (x, y), p in sorted(pares.items()):
    xu, yu = x + "USDT", y + "USDT"
    if xu not in PANEL and yu not in PANEL:
        continue
    out.append({"viejo": x, "nuevo": y, "viejo_usdt_en_panel": xu in PANEL, "nuevo_usdt_en_panel": yu in PANEL,
                "relaciones_nuevo_por_viejo": sorted(p["relaciones"]), "frases": p["frases"],
                "fechas_en_cuerpos": sorted(p["fechas"])[:40], "capturas": sorted(p["capturas"]),
                "archivos": sorted(p["archivos"])[:8], "n_archivos": len(p["archivos"]),
                "actividad_viejo": act(xu), "actividad_nuevo": act(yu) if yu != xu else None})
SAL.write_text(json.dumps({"paginas_sin_saludo": sin_saludo, "pares_con_par_usdt_en_panel": len(out), "pares": out},
                          ensure_ascii=False, indent=1))
print("páginas sin saludo (cuerpo no delimitable):", sin_saludo, "· pares con algún lado USDT en el panel:", len(out))
for o in out:
    print(f"{o['viejo']:>10} → {o['nuevo']:<10} panel(v/n)={int(o['viejo_usdt_en_panel'])}/{int(o['nuevo_usdt_en_panel'])} "
          f"r={o['relaciones_nuevo_por_viejo'][:3]} n={o['n_archivos']} | {o['frases'][0][:110]}")
