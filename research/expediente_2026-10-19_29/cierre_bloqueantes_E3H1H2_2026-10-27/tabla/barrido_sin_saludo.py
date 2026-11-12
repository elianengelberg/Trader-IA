"""Segundo barrido: páginas SIN saludo (cuerpo no delimitable por A3.1.1). Texto completo, mismos patrones que
barrido_renombres.py. Solo informa pares NUEVOS (no hallados en el primer barrido) como pistas, sin valor de evidencia
hasta comprobar que el fragmento no es una barra lateral. Uso: python -I barrido_sin_saludo.py <dir_E3> <barrido_renombres.json> <salida.json>"""
import importlib.util, json, re, sys
from pathlib import Path
E3, PREV, SAL = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("b", Path(__file__).with_name("barrido_renombres.py"))
src = Path(__file__).with_name("barrido_renombres.py").read_text()
ns = {}
exec(compile(src.split("pares = defaultdict")[0].replace("E3, SAL = Path(sys.argv[1]), Path(sys.argv[2])", "E3 = Path(sys.argv[1])"), "b", "exec"), ns)
prev = {(p["viejo"], p["nuevo"]) for p in json.loads(PREV.read_text())["pares"]}
out = {}
for f in sorted((E3 / "datos_anuncios/commoncrawl/paginas").glob("*.json")):
    d = json.loads(f.read_text())
    t = re.sub(r"\s+", " ", d.get("texto", ""))
    if ns["cuerpo"](t) is not None:
        continue
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", t):
        if not ns["CLAVE"].search(s):
            continue
        cands = []
        for m in ns["RELACION"][0].finditer(s):
            a, x, b, y = m.groups()
            if x not in ns["NO_TOKEN"] and y not in ns["NO_TOKEN"]:
                cands.append((x, y, m.group(0)))
        for rx in ns["TICKER"]:
            for m in rx.finditer(s):
                x, y = m.groups()[0], m.groups()[-1]
                if x != y and x not in ns["NO_TOKEN"] and y not in ns["NO_TOKEN"]:
                    cands.append((x, y, m.group(0)))
        for x, y, frag in cands:
            if (x, y) in prev or (x + "USDT" not in ns["PANEL"] and y + "USDT" not in ns["PANEL"]):
                continue
            o = out.setdefault(f"{x}->{y}", {"archivos": [], "frag": frag[:300], "contexto": s[:400]})
            if f.name not in o["archivos"]:
                o["archivos"].append(f.name)
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1))
for k, v in sorted(out.items()):
    print(f"{k:<20} n={len(v['archivos'])} | {v['contexto'][:230]}")
