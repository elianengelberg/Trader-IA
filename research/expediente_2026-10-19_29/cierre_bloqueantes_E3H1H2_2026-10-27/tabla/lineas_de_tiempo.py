"""Para cada (token, patrón) imprime las oraciones con fecha «At AAAA-MM-DD …», con relación de canje o con cambio de
ticker, del cuerpo de las páginas de evidencia_tokens.json que cumplen el patrón. Solo textos.
Uso: python -I lineas_de_tiempo.py <paginas> <evidencia_tokens.json> TOKEN=regex [TOKEN=regex …]"""
import json, re, sys
from pathlib import Path
P, EV = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
for arg in sys.argv[3:]:
    tk, pat = arg.split("=", 1)
    vistos = set()
    for c in EV[tk]["cuerpos"]:
        if not re.search(pat, c["cuerpo"]):
            continue
        t = re.sub(r"\s+", " ", json.loads((P / c["archivo"]).read_text())["texto"])
        i = t.find("Fellow Binancians")
        cu = t[i:i + 6000]
        fin = min([cu.find(m) for m in ("Thanks for your support", "Binance Team") if cu.find(m) > 0] or [len(cu)])
        cu = cu[:fin]
        if cu[:200] in vistos:
            continue
        vistos.add(cu[:200])
        print(f"===== {tk} | {c['archivo'][:80]} | cap {c['captura'][:8]}")
        print("   inicio:", cu[:260])
        for m in re.finditer(r"(?:At|On|From|Starting from|Before) 20\d\d[-/]\d\d[-/]\d\d[^.]{0,240}\.|[^.]{0,140}(?:ratio|ticker|renamed|rebrand)[^.]{0,200}\.", cu):
            print("   *", m.group(0)[:330])
