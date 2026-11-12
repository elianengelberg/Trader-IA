"""E3 · F3 estructural (después de calidad.py). Sin rendimientos de estrategia: no importa motor.py ni calcula retornos futuros.

Uso: python -I analisis_estructural.py <dir_calidad> <salida.json>
"""
import collections
import datetime as dt
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from universo import INICIO, Panel, lunes, universo  # noqa: E402


def cargar(dir_calidad: Path):
    archivos = sorted((dir_calidad / "series").glob("*.npz"))
    syms, O, C, QV, act = [], [], [], [], []
    for f in archivos:
        z = np.load(f)
        syms.append(str(z["simbolo"]))
        O.append(z["O"]); C.append(z["C"]); QV.append(z["QV"]); act.append(z["estado"] == 1)
    return Panel(syms, np.array(O), np.array(C), np.array(QV), np.array(act))


def main(dir_calidad: Path, salida: Path):
    P = cargar(dir_calidad)
    aud = {a["simbolo"]: a for a in json.loads((dir_calidad / "auditoria_por_simbolo.json").read_text())}
    # 1) Universo reconstruido por lunes (solo tamaños y evaluabilidad)
    F = lunes(dt.date(2018, 1, 1), dt.date(2026, 5, 25))
    filas, listas = [], []
    for t in F:
        U = universo(P, t)
        n = 0 if U is None else len(U["elegibles"])
        w = slice(t - 30, t)
        ca = P.act[:, w].all(axis=1)
        cb = ca & (P.ep_ini[:, t - 1] >= 0) & (t - P.ep_ini[:, t - 1] >= 180)
        V = np.nanmedian(np.where(P.act[:, w], P.QV[:, w], np.nan), axis=1) if t >= 30 else np.full(P.S, np.nan)
        cd = cb & (V >= 1_000_000)
        # Listas fijas de F3 (v3 §10.3): candidatos líquidos excluidos por lista fija, apalancamiento, baja volatilidad o duplicado
        cand = cd & ~P.fijo & ~P.apalancado
        eleg = set(U["elegibles"]) if U else set()
        excl_vd = sorted(P.sym[k] for k in np.flatnonzero(cand) if k not in eleg)
        listas.append({"lunes": (INICIO + dt.timedelta(days=t)).isoformat(),
                       "lista_fija": sorted(P.sym[k] for k in np.flatnonzero(cd & P.fijo)),
                       "apalancados": sorted(P.sym[k] for k in np.flatnonzero(cd & P.apalancado & ~P.fijo)),
                       "baja_volatilidad_o_duplicado": excl_vd, "elegibles": sorted(P.sym[k] for k in eleg)})
        filas.append({"lunes": (INICIO + dt.timedelta(days=t)).isoformat(), "activos_30d": int(ca.sum()), "con_edad_180": int(cb.sum()),
                      "falta_liquidez": int((cb & ~(V >= 1_000_000)).sum()), "liquidos": int(cd.sum()),
                      "excluidos_lista_o_apalancados": int((cd & (P.fijo | P.apalancado)).sum()), "elegibles": n,
                      "U100": min(n, 100), "U30": min(n, 30), "evaluable": n >= 30})
    ev = [f["evaluable"] for f in filas]
    ini_i = next((filas[i]["lunes"] for i in range(len(ev) - 12) if all(ev[i:i + 13])), None)
    por_anio = collections.defaultdict(lambda: {"semanas": 0, "evaluables": 0, "elegibles_mediana": []})
    for f in filas:
        y = f["lunes"][:4]
        por_anio[y]["semanas"] += 1
        por_anio[y]["evaluables"] += int(f["evaluable"])
        por_anio[y]["elegibles_mediana"].append(f["elegibles"])
    por_anio = {y: {"semanas": v["semanas"], "evaluables": v["evaluables"], "elegibles_mediana": float(np.median(v["elegibles_mediana"]))} for y, v in sorted(por_anio.items())}
    if ini_i:
        desde = [f for f in filas if f["lunes"] >= ini_i and f["lunes"] <= "2026-05-18"]
        sem_i = {"desde_componente_i": ini_i, "semanas": len(desde), "evaluables": sum(f["evaluable"] for f in desde),
                 "no_evaluables_pct": 100 * (1 - sum(f["evaluable"] for f in desde) / len(desde))}
    else:
        sem_i = None
    # 2) Evidencia de supervivencia solo con datos (sin anuncios: A3 bloqueado)
    salidas = collections.Counter()
    colas = {"con_velas_cero_operaciones": 0, "sin_velas": 0}
    cortes, saltos = [], []
    for s, a in aud.items():
        eps = a.get("episodios", [])
        for i, (ini, fin) in enumerate(eps):
            if fin <= "2026-05-01":
                salidas[fin[:4]] += 1
        cola = a.get("cola_tras_ultimo_activo")
        if cola and eps and eps[-1][1] <= "2026-05-01":
            colas["con_velas_cero_operaciones" if cola["filas_cero_operaciones"] > 0 else "sin_velas"] += 1
        # cortes con reanudación (Adenda 1): cualquier duración; salto de precio a través del corte
        k = P.sym.index(s)
        for c0, c1, h in a.get("cortes_con_reanudacion", []):
            i0 = (dt.date.fromisoformat(c0) - INICIO).days
            i1 = (dt.date.fromisoformat(c1) - INICIO).days
            ratio = float(P.O[k, i1] / P.C[k, i0])
            cortes.append({"simbolo": s, "ultimo_activo": c0, "reanuda": c1, "dias": h, "ratio_precio": ratio})
        for j in range(1, len(eps)):
            i0 = (dt.date.fromisoformat(eps[j - 1][1]) - INICIO).days
            i1 = (dt.date.fromisoformat(eps[j][0]) - INICIO).days
            ratio = float(P.O[k, i1] / P.C[k, i0])
            saltos.append({"simbolo": s, "fin_episodio": eps[j - 1][1], "nuevo_episodio": eps[j][0], "ratio_precio": ratio})
    sospechosos = [c for c in cortes if not (0.1 <= c["ratio_precio"] <= 10)]
    out = {"universo_por_anio": por_anio, "inicio_componente_i_13_semanas_evaluables": ini_i, "ventana_desde_componente_i": sem_i,
           "componentes_ii_iii_iv": "ver conciliacion.json (conciliacion.py, Adenda 3)",
           "salidas_observadas_por_anio": dict(sorted(salidas.items())), "colas_tras_ultimo_activo": colas,
           "cortes_con_reanudacion": {"total": len(cortes), "dias_mediana": float(np.median([c["dias"] for c in cortes])) if cortes else None,
                                      "con_salto_de_precio_x10": len(sospechosos), "lista_saltos": sospechosos},
           "relistados_tras_30_dias": {"total": len(saltos), "lista": saltos},
           "semanas": filas}
    salida.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    salida.with_name("listas_fijas_por_lunes.json").write_text(json.dumps(listas, ensure_ascii=False, indent=0))
    print(json.dumps({k: v for k, v in out.items() if k not in ("semanas",)}, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
