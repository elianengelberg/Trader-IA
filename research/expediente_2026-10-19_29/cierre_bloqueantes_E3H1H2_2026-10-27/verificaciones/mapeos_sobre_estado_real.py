"""Aplica la tabla completa con las funciones del v3 a la ACTIVIDAD real (solo `simbolo` y `estado`; una guarda aborta si
se pide O, H, L, C, QV u otro arreglo) y compara, para cada formación de A, los criterios (a) 30 días activos seguidos y
(b) edad ≥ 180 días entre: sin mapeos, con la tabla de 22 y con la tabla completa. El criterio (d) (volumen) NO se
evalúa: exigiría leer QV real. Uso: python -I mapeos_sobre_estado_real.py <ejecutar_E3_v3.py> <dir_E3> <ventana_A.json> <dir_reparacion> <salida.json>"""
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

V3P, E3, VENT, REP, SAL = (Path(a) for a in sys.argv[1:6])
spec = importlib.util.spec_from_file_location("v3", V3P)
V3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V3)
leidos = set()


class SoloEstado:
    def __init__(self, z):
        self.z = z

    def __getitem__(self, k):
        if k not in ("estado", "simbolo"):
            raise AssertionError(f"se pidió «{k}»: prohibido (solo estado y simbolo)")
        leidos.add(k)
        return self.z[k]


_npz_original = V3._npz
V3._npz = lambda b: SoloEstado(_npz_original(b))
raices = {"E3": E3, "reparacion": REP, "cierre": V3.CIERRE, "ventana": VENT}
datos = V3.leer_y_verificar((V3P.parent / "ENTRADAS_CONGELADAS_V3.json").read_bytes(), raices)  # bytes + sha256
mods = V3.cargar_modulos({n[:-3]: datos[n] for n in V3.CONGELADOS})
U = mods["universo"]
syms, act = V3.actividad_desde_bytes(datos)
cero = np.zeros(act.shape)
tabla = json.loads(datos["mapeos_adenda1_completa"])["mapeos"]
tabla22 = json.loads((REP / "renombres/mapeos_adenda1.json").read_text())["mapeos"]
res = {"arreglos_leidos": None}
variantes = {}
for nombre, maps in (("sin_mapeos", []), ("tabla_22", tabla22), ("tabla_completa", tabla)):
    s2, _, _, _, a2, reg, origen = V3.aplicar_mapeos(syms, cero, cero, cero, act, maps, U.INICIO)
    V3.comprobar_marcas(syms, s2, origen, U)
    P = U.Panel(s2, np.zeros(a2.shape), np.zeros(a2.shape), np.zeros(a2.shape), a2)
    variantes[nombre] = (s2, P, len(reg))
inicio = dt.date.fromisoformat(V3.INICIO_H_A)
F = U.lunes(inicio, V3.ULTIMA_FORMACION)


def ab(P, s, t):
    """(a) 30 días activos seguidos antes de t y (b) edad ≥ 180 días: solo actividad."""
    k = P.sym.index(s)
    return bool(P.act[k, t - 30:t].all()) and P.ep_ini[k, t - 1] >= 0 and t - P.ep_ini[k, t - 1] >= 180


cambios = {}
for a, b in (("tabla_22", "tabla_completa"), ("sin_mapeos", "tabla_completa")):
    sa, Pa, _ = variantes[a]
    sb, Pb, _ = variantes[b]
    dif = {}
    for s in sorted(set(sa) & set(sb)):
        fs = [(U.INICIO + dt.timedelta(days=int(t))).isoformat() for t in F if ab(Pa, s, t) != ab(Pb, s, t)]
        if fs:
            dif[s] = {"formaciones_distintas": len(fs), "primera": fs[0], "ultima": fs[-1],
                      f"cumple_a_y_b_con_{b}": ab(Pb, s, F[[(U.INICIO + dt.timedelta(days=int(t))).isoformat() for t in F].index(fs[0])])}
    cambios[f"{a}→{b}"] = dif
res.update({"mapeos_en_tabla": len(tabla), "aplicados": {k: v[2] for k, v in variantes.items()},
            "filas": {k: len(v[0]) for k, v in variantes.items()}, "formaciones_A": len(F),
            "cambios_en_a_y_b_dentro_de_A": cambios, "arreglos_leidos": sorted(leidos),
            "nota": "Criterio (d) de volumen no evaluado: exigiría leer QV real."})
SAL.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
print(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
