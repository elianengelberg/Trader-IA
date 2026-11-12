"""E3 · Ventana A con la segunda pasada (Adenda R con R1 literal; v3 §4.11; Adenda 3 A3.7–A3.8). SIN RETORNOS.

Es `p0_auditoria_interna.py` (E3R, 0452347d…) con tres cambios, y solo esos:
  1. la conciliación de entrada es un argumento (primera o segunda pasada), en vez de la ruta fija de la primera;
  2. se pueden sumar fallas de §2.3 que la extracción omitió (archivo JSON con par, E y categoría, clasificadas con la
     función congelada `clasificar`); se usan en (ii) y (ii′);
  3. A3.7: las salidas por un renombre mapeado (motivo «renombre_mapeado» de la conciliación) no cuentan como salidas en (iv′).
Además informa, sin usarlos para decidir, el (ii) de la v3 pura (todas las fallas, sin alcance) y la tabla de semanas.
Lee: `estado` de las series de calidad (nunca O, H, L, C ni QV), listas fijas, estructural, salidas y eventos.
Uso: python -I p0_pasada2.py <dir_ejecucion_E3> <dir_conciliacion> <resoluciones_C.json> <fallas_extra.json|-> <salida.json>
"""
import datetime as dt
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

E3, CON, RES, EXTRA, SALIDA = (Path(a) for a in sys.argv[1:6])
INICIO = dt.date(2017, 7, 1)
ULTIMO_LUNES = dt.date(2026, 5, 18)
CAL = E3 / "resultados" / "calidad" / "series"
ESTR = E3 / "resultados" / "estructural"
INSUMOS = [ESTR / "listas_fijas_por_lunes.json", ESTR / "estructural.json", CON / "salidas.json", CON / "eventos.json", RES]
if str(EXTRA) != "-":
    INSUMOS.append(EXTRA)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def lunes_siguiente(x: dt.date) -> dt.date:
    return x + dt.timedelta(days=(7 - x.weekday()) % 7 or 7)


salidas = json.loads((CON / "salidas.json").read_text())
eventos = json.loads((CON / "eventos.json").read_text())
listas = json.loads((ESTR / "listas_fijas_por_lunes.json").read_text())
semanas = json.loads((ESTR / "estructural.json").read_text())["semanas"]
resoluciones = json.loads(RES.read_text())
extra = json.loads(EXTRA.read_text()) if str(EXTRA) != "-" else []
series = sorted({CAL / f"{x['simbolo']}.npz" for x in salidas})
antes = {str(p): sha(p) for p in [*INSUMOS, *series]}

lunes = sorted((d(x["lunes"]), set(x["lista_fija"]), set(x["apalancados"])) for x in listas)


def fuera_de_alcance(simbolo: str, fecha: dt.date) -> bool:
    """R1 literal: en `lista_fija` o `apalancados` del último lunes ≤ fecha (o del primero, si es anterior)."""
    elegido = lunes[0]
    for entrada in lunes:
        if entrada[0] <= fecha:
            elegido = entrada
        else:
            break
    return simbolo in elegido[1] or simbolo in elegido[2]


anunciados = {e["par"] for e in eventos if e.get("categoria") in ("A", "B")}
filas = []
for x in salidas:
    s, L = x["simbolo"], d(x["ultimo_activo"])
    estado = np.load(CAL / f"{s}.npz")["estado"]  # solo el estado; los precios no se cargan
    i = (L - INICIO).days
    cola = estado[i + 1:i + 31]
    ev = {"ANUNCIO": s in anunciados, "SUSPENSION": bool(i + 1 < len(estado) and estado[i + 1] == 3), "COLA_CERO": bool((cola == 2).any())}
    filas.append({"simbolo": s, "L": L.isoformat(), "anio": L.year, "motivo_E3": x.get("motivo"),
                  "renombre_mapeado": x.get("motivo") == "renombre_mapeado",
                  "en_alcance": not fuera_de_alcance(s, L), **ev, "con_evidencia": any(ev.values())})


def tabla_iv(excluir_mapeados: bool):
    por_anio = defaultdict(lambda: defaultdict(int))
    for f in filas:
        if excluir_mapeados and f["renombre_mapeado"]:
            continue
        a = por_anio[f["anio"]]
        a["salidas"] += 1
        if f["en_alcance"]:
            a["en_alcance"] += 1
            for k in ("ANUNCIO", "SUSPENSION", "COLA_CERO"):
                a[k] += f[k]
            a["sin_evidencia"] += not f["con_evidencia"]
    tabla = {y: {**por_anio[y], "pct_sin_evidencia": round(100 * por_anio[y]["sin_evidencia"] / por_anio[y]["en_alcance"], 1)
                 if por_anio[y]["en_alcance"] else 0.0} for y in sorted(por_anio)}
    anios = list(range(2018, 2027))
    cumple = {y: (tabla.get(y, {}).get("en_alcance", 0) == 0 or tabla[y]["sin_evidencia"] <= 0.10 * tabla[y]["en_alcance"]) for y in anios}
    iv = next((y for y in anios if all(cumple[z] for z in anios if z >= y)), None)
    return tabla, iv


tabla, iv = tabla_iv(excluir_mapeados=True)
tabla_sin_A37, iv_sin_A37 = tabla_iv(excluir_mapeados=False)

fallas = []
for e in [*eventos, *({**x, "categoria": x["categoria"], "omitido_por_la_extraccion": True} for x in extra)]:
    cat = e.get("categoria")
    if cat not in ("T", "D", "C_no_explicada"):
        continue
    if cat == "C_no_explicada" and resoluciones.get(e["par"], {}).get("resolucion") == "agregado":
        continue
    E = d(e["E"])
    fallas.append({"par": e["par"], "E": e["E"], "categoria": cat, "en_alcance": not fuera_de_alcance(e["par"], E),
                   "omitido_por_la_extraccion": bool(e.get("omitido_por_la_extraccion"))})
fallas.sort(key=lambda f: (f["E"], f["par"]))
en_alcance = [f for f in fallas if f["en_alcance"]]
ii = max((d(f["E"]) for f in en_alcance), default=None)
ii_lunes = None if ii is None else lunes_siguiente(ii)
ii_v3 = max((d(f["E"]) for f in fallas), default=None)  # v3 §2.3 pura: todas las fallas, sin alcance

i_comp = d(json.loads((ESTR / "estructural.json").read_text())["inicio_componente_i_13_semanas_evaluables"])
iv_lunes = None if iv is None else dt.date(iv, 1, 1) + dt.timedelta(days=(7 - dt.date(iv, 1, 1).weekday()) % 7)
inicio = max(c for c in (i_comp, ii_lunes, iv_lunes) if c is not None) if iv is not None else None
ventana = [w for w in semanas if inicio is not None and inicio <= d(w["lunes"]) <= ULTIMO_LUNES]
evaluables = sum(w["evaluable"] for w in ventana)
no_eval_pct = round(100 * (len(ventana) - evaluables) / len(ventana), 1) if ventana else None
valido = inicio is not None and evaluables >= 156 and no_eval_pct is not None and no_eval_pct <= 20.0

# Margen: el lunes más tardío que todavía deja ≥ 156 semanas evaluables, y la fecha efectiva de falla que lo alcanzaría
lunes_ok = [d(w["lunes"]) for w in semanas if d(w["lunes"]) <= ULTIMO_LUNES and
            sum(v["evaluable"] for v in semanas if d(w["lunes"]) <= d(v["lunes"]) <= ULTIMO_LUNES) >= 156]
ultimo_inicio_valido = max(lunes_ok) if lunes_ok else None

despues = {str(p): sha(p) for p in [*INSUMOS, *series]}
salida = {
    "base": "p0_auditoria_interna.py (0452347d…) con los cambios 1–3 del encabezado",
    "conciliacion": str(CON), "por_anio_iv_prima": tabla, "por_anio_iv_prima_sin_excluir_renombres_mapeados": tabla_sin_A37,
    "componentes": {"i": i_comp.isoformat(), "ii_prima": ii_lunes and ii_lunes.isoformat(), "ultima_falla_en_alcance": ii and ii.isoformat(),
                    "iv_prima_anio": iv, "iv_prima_anio_sin_excluir_renombres_mapeados": iv_sin_A37,
                    "ii_v3_pura_lunes": ii_v3 and lunes_siguiente(ii_v3).isoformat()},
    "fallas_2_3": fallas, "inicio_H": inicio and inicio.isoformat(), "fin_H_ultimo_lunes": ULTIMO_LUNES.isoformat(),
    "semanas_H": len(ventana), "evaluables_H": evaluables, "no_evaluables_pct": no_eval_pct,
    "min_elegibles_en_H": min((w["elegibles"] for w in ventana), default=None),
    "ultimo_inicio_con_156_evaluables": ultimo_inicio_valido and ultimo_inicio_valido.isoformat(),
    "margen_semanas": (evaluables - 156) if ventana else None,
    "veredicto": "VALIDO" if valido else "INVALIDO",
    "semanas": [{k: w[k] for k in ("lunes", "elegibles", "U100", "U30", "evaluable")} for w in ventana],
    "salidas": filas, "insumos_sin_cambios": antes == despues, "huellas_insumos": antes,
}
SALIDA.write_text(json.dumps(salida, indent=1, ensure_ascii=False))
print(json.dumps({k: salida[k] for k in ("componentes", "inicio_H", "semanas_H", "evaluables_H", "no_evaluables_pct", "min_elegibles_en_H",
                                         "ultimo_inicio_con_156_evaluables", "margen_semanas", "veredicto", "insumos_sin_cambios")},
                 indent=1, ensure_ascii=False))
