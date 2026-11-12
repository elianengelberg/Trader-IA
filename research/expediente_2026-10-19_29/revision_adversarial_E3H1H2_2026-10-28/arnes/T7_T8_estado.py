"""Revisión adversarial · T-7 y T-8, solo con `estado` y `simbolo`.
- T-8: para cada mapeo de regla 1 de la tabla completa, último día activo de X, primer día activo de Y y hueco, desde
  `estado == 1`, leído con una guarda que aborta ante cualquier otro arreglo (el .npz se abre en modo perezoso: solo se
  descomprime el miembro pedido). Se compara con `chequeo_actividad` de la tabla.
- T-7: aritmética de la ventana: lunes entre el inicio y la última formación; (ii′) desde las fallas en alcance del
  archivo de ventana; (iv′) recalculado desde la lista de salidas del archivo de ventana fijado.
Uso: python -B -I T7_T8_estado.py <dir_series> <mapeos_completos.json> <TABLA.json> <ventana_A_pasada2.json> <salida.json>"""
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

SER, MAP, TABLA, VENT, SAL = (Path(a) for a in sys.argv[1:6])
INICIO = dt.date(2017, 7, 1)  # universo.INICIO (día 0 de las series), verificado abajo contra la tabla
leidos = set()


class SoloEstado:
    def __init__(self, ruta):
        self.z = np.load(ruta, allow_pickle=False)

    def __getitem__(self, k):
        if k not in ("estado", "simbolo"):
            raise AssertionError(f"prohibido leer «{k}»")
        leidos.add(k)
        return self.z[k]


def actividad(sym):
    z = SoloEstado(SER / f"{sym}.npz")
    assert str(z["simbolo"]) == sym
    a = np.flatnonzero(z["estado"] == 1)
    return a


out = {"T8": [], "T7": {}}
tabla = {(t["viejo_usdt"], t["nuevo_usdt"]): t for t in json.loads(TABLA.read_text())["tabla"]}
for m in json.loads(MAP.read_text())["mapeos"]:
    if m.get("regla") != 1:
        continue
    x, y = m["viejo_usdt"], m["nuevo_usdt"]
    ax, ay = actividad(x), actividad(y)
    lx, fy = INICIO + dt.timedelta(days=int(ax[-1])), INICIO + dt.timedelta(days=int(ay[0]))
    t = tabla.get((x, y), {})
    ch = t.get("chequeo_actividad") or {}
    out["T8"].append({"x": x, "y": y, "E": m.get("E"), "ultimo_activo_x": lx.isoformat(), "primer_activo_y": fy.isoformat(),
                      "hueco_dias": (fy - lx).days - 1, "y_empieza_despues_de_x": fy > lx,
                      "coincide_con_tabla": (ch.get("ultimo_activo_viejo"), ch.get("primer_activo_nuevo")) == (lx.isoformat(), fy.isoformat())})
v = json.loads(VENT.read_text())
lunes = lambda a, b: [a + dt.timedelta(days=7 * k) for k in range(((b - a).days // 7) + 1)]
fin = dt.date.fromisoformat(v["fin_H_ultimo_lunes"])
fallas = [f for f in v["fallas_2_3"] if f["en_alcance"]]
ult = max(dt.date.fromisoformat(f["E"]) for f in fallas)
sig_lunes = ult + dt.timedelta(days=7 - ult.weekday()) if ult.weekday() != 0 else ult + dt.timedelta(days=7)
por_anio = defaultdict(lambda: [0, 0])
for s in v["salidas"]:
    if s["en_alcance"] and not s.get("renombre_mapeado"):
        por_anio[s["anio"]][0] += 1
        por_anio[s["anio"]][1] += not s["con_evidencia"]
anios = sorted(por_anio)
ok = {a: por_anio[a][1] <= 0.10 * por_anio[a][0] for a in anios}
ivp = next(a for a in anios if all(ok[b] for b in anios if b >= a))
out["T7"] = {"ultima_falla_en_alcance": ult.isoformat(), "lunes_siguiente": sig_lunes.isoformat(),
             "semanas_desde_inicio_hasta_fin": len(lunes(sig_lunes, fin)),
             "semanas_si_inicio_2023_05_01": len(lunes(dt.date(2023, 5, 1), fin)),
             "iv_prima_recalculado": ivp, "por_anio_en_alcance_sin_evidencia": {a: por_anio[a] for a in anios},
             "fallas_en_alcance": [(f["par"], f["E"], f["categoria"], f.get("omitido_por_la_extraccion")) for f in fallas]}
out["arreglos_leidos"] = sorted(leidos)
SAL.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print(json.dumps(out["T7"], ensure_ascii=False, default=str))
print("arreglos leídos:", sorted(leidos))
for r in out["T8"]:
    print(r)
