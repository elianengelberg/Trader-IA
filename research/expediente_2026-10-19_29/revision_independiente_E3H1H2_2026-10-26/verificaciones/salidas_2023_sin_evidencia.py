"""Lista las salidas en alcance de 2023 sin evidencia (misma lógica que ventana_independiente.py; solo lee «estado»).
Uso: python -I salidas_2023_sin_evidencia.py <dir_E3> <dir_pasada2>"""
import datetime as dt, json, sys
from pathlib import Path
import numpy as np
E3, P2 = Path(sys.argv[1]), Path(sys.argv[2])
INICIO = dt.date(2017, 7, 1)
ev = json.loads((P2 / "eventos.json").read_text()); sal = json.loads((P2 / "salidas.json").read_text())
listas = sorted((dt.date.fromisoformat(x["lunes"]), set(x["lista_fija"]) | set(x["apalancados"])) for x in
                json.loads((E3 / "resultados/estructural/listas_fijas_por_lunes.json").read_text()))
def fuera(s, f):
    l = listas[0][1]
    for lu, x in listas:
        if lu <= f: l = x
    return s in l
ab = {e["par"] for e in ev if e["categoria"] in ("A", "B")}
for x in sal:
    if x.get("motivo") == "renombre_mapeado": continue
    s, L = x["simbolo"], dt.date.fromisoformat(x["ultimo_activo"])
    if L.year != 2023 or fuera(s, L): continue
    z = np.load(E3 / "resultados/calidad/series" / f"{s}.npz"); est = z["estado"]
    i = (L - INICIO).days
    evid = (s in ab) or (i + 1 < len(est) and est[i + 1] == 3) or bool((est[i + 1:i + 31] == 2).any())
    print(s, L, "con_evidencia" if evid else "SIN_EVIDENCIA")
