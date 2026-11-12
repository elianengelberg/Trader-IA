"""Recálculo independiente de la ventana A (v3 §4.11 + Adenda R con R1 literal), escrito sin reutilizar el código del autor.
Lee: eventos y salidas de la segunda pasada (reproducida en el área de revisión), eventos omitidos, listas fijas,
estructural y SOLO el arreglo `estado` de cada serie. Una guarda aborta si se pide cualquier otro arreglo (O, H, L, C, QV…).
También verifica, contra el texto archivado, cada una de las 47 resoluciones de eventos.
Uso: python -I ventana_independiente.py <dir_E3> <dir_pasada2> <eventos_omitidos.json> <resoluciones.json> <salida.json>"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import numpy as np

E3, P2, OMI, RES, SAL = (Path(a) for a in sys.argv[1:6])
INICIO, FIN_H = dt.date(2017, 7, 1), dt.date(2026, 5, 18)


class SoloEstado:
    """Envuelve np.load: solo deja leer «estado» y «simbolo»."""
    def __init__(self, ruta):
        self.z = np.load(ruta)

    def __getitem__(self, k):
        if k not in ("estado", "simbolo"):
            raise AssertionError(f"se intentó leer «{k}»: prohibido en esta revisión")
        return self.z[k]


def d(s):
    return dt.date.fromisoformat(s)


def lunes_sig(x):
    return x + dt.timedelta(days=(7 - x.weekday()) % 7 or 7)


ev = json.loads((P2 / "eventos.json").read_text())
sal = json.loads((P2 / "salidas.json").read_text())
omi = json.loads(OMI.read_text())
listas = sorted((d(x["lunes"]), set(x["lista_fija"]) | set(x["apalancados"])) for x in
                json.loads((E3 / "resultados/estructural/listas_fijas_por_lunes.json").read_text()))
semanas = json.loads((E3 / "resultados/estructural/estructural.json").read_text())["semanas"]


def fuera(sim, fecha):
    lista = listas[0][1]
    for lu, l in listas:
        if lu <= fecha:
            lista = l
    return sim in lista


# (ii) y (ii′)
fallas = [(e["par"], e["E"], e["categoria"]) for e in ev if e["categoria"] in ("T", "D", "C_no_explicada")]
fallas += [(o["par"], o["E"], o["categoria"]) for o in omi if o["categoria"] in ("T", "D", "C_no_explicada")]
alc = [f for f in fallas if not fuera(f[0], d(f[1]))]
ii_v3 = lunes_sig(max(d(f[1]) for f in fallas))
ii_R = lunes_sig(max(d(f[1]) for f in alc))

# (iv′): salidas en alcance sin evidencia; las de renombre mapeado no cuentan (A3.7)
ab = {e["par"] for e in ev if e["categoria"] in ("A", "B")}
anio = {}
for x in sal:
    if x.get("motivo") == "renombre_mapeado":
        continue
    s, L = x["simbolo"], d(x["ultimo_activo"])
    if fuera(s, L):
        continue
    est = SoloEstado(E3 / "resultados/calidad/series" / f"{s}.npz")["estado"]
    i = (L - INICIO).days
    evid = (s in ab) or (i + 1 < len(est) and est[i + 1] == 3) or bool((est[i + 1:i + 31] == 2).any())
    a = anio.setdefault(L.year, [0, 0])
    a[0] += 1
    a[1] += (not evid)
anios = range(2018, 2027)
ok = {y: (anio.get(y, [0, 0])[0] == 0 or anio[y][1] <= 0.10 * anio[y][0]) for y in anios}
iv = next((y for y in anios if all(ok[z] for z in anios if z >= y)), None)
iv_lunes = dt.date(iv, 1, 1) + dt.timedelta(days=(7 - dt.date(iv, 1, 1).weekday()) % 7) if iv else None
i_comp = d(json.loads((E3 / "resultados/estructural/estructural.json").read_text())["inicio_componente_i_13_semanas_evaluables"])
inicio = max(i_comp, ii_R, iv_lunes)
win = [w for w in semanas if inicio <= d(w["lunes"]) <= FIN_H]
ultimo_valido = max(d(w["lunes"]) for w in semanas if d(w["lunes"]) <= FIN_H and
                    sum(v["evaluable"] for v in semanas if d(w["lunes"]) <= d(v["lunes"]) <= FIN_H) >= 156)

# verificación de las 47 resoluciones contra el texto archivado
PAG = E3 / "datos_anuncios/commoncrawl/paginas"


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


res = json.loads(RES.read_text())
chequeo = []
for k, r in res["eventos"].items():
    t = norm(json.loads((PAG / r["fuente"]["archivo"]).read_text()).get("texto", ""))
    E = r.get("E", k.split("|")[1])
    fechas = {"-".join(m) for m in re.findall(r"(20\d\d)[-/](\d\d)[-/](\d\d)", r["cita"])}
    chequeo.append({"clave": k, "accion": r["accion"], "cita_en_pagina": norm(r["cita"]) in t,
                    "E_en_cita": (E in fechas) if r["accion"] in ("confirmar", "fecha_corregida") else None})
malas = [c for c in chequeo if not c["cita_en_pagina"] or c["E_en_cita"] is False]

out = {"ii_v3": ii_v3.isoformat(), "ii_prima": ii_R.isoformat(), "fallas": fallas, "fallas_en_alcance": alc,
       "iv_prima_anio": iv, "salidas_por_anio_en_alcance_[n,sin_evidencia]": anio, "i": i_comp.isoformat(),
       "inicio": inicio.isoformat(), "semanas": len(win), "evaluables": sum(w["evaluable"] for w in win),
       "min_elegibles": min(w["elegibles"] for w in win), "ultimo_inicio_valido": ultimo_valido.isoformat(),
       "resoluciones_verificadas": len(chequeo), "resoluciones_con_problema": malas}
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print(json.dumps({k: v for k, v in out.items() if k not in ("fallas",)}, ensure_ascii=False, indent=1, default=str))
