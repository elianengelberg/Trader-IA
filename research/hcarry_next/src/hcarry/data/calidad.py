"""Informe de calidad de un directorio de datos y filtros de aceptación FIJADOS ANTES de ver datos reales.

Si cualquier filtro falla, la evaluación histórica no se ejecuta (el resultado es «evidencia insuficiente» por datos).

  C1 procedencia   manifiesto presente y procedencia declarada; en datos históricos, cada archivo con su .CHECKSUM
                   oficial al lado y coincidente (además de la verificación contra el manifiesto al cargar)
  C2 cobertura     desde el primer mes común de las series requeridas (spot, perp, mark, funding) hasta el final de
                   la ventana, ningún mes requerido ausente (A1)
  C3 horas         horas rellenadas ≤ 0,5 % y ninguna racha rellenada > 24 h
  C4 funding       sin incidencias A2, A2b, A4, A7, A8 (política estricta de rev. 5)
  C5 coherencia    sin A6 ni P2; mediana de |F/S − 1| ≤ 0,2 % y p99 de |M/F − 1| ≤ 1 %
  C6 periodo       nada en el período reservado (garantizado por código)"""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

from hcarry.conventions import HORA_MS, iso, ms
from hcarry.data.binance_vision import _checksum_de, cobertura, construir_panel, inicio_comun, leer_manifiesto, meses
from hcarry.estrategias import apr_funding
from hcarry.metricas import percentil_rango_cercano

UMBRALES = {"horas_rellenadas_frac_max": 0.005, "racha_rellenada_max_h": 24, "base_mediana_abs_max": 0.002,
            "mark_perp_p99_abs_max": 0.01,
            "funding_bloqueantes": ["A2", "A2b", "A4", "A7", "A8"], "coherencia_bloqueantes": ["A6", "P2"]}
HASTA_DEFECTO = "2026-06-01"


def evaluar(directorio: Path, desde: str | None = None, hasta: str = HASTA_DEFECTO) -> dict:
    man = leer_manifiesto(directorio)
    cob = cobertura(directorio)
    ini = desde or inicio_comun(directorio)
    filtros: dict[str, dict] = {}

    # C1 procedencia y checksums oficiales
    sin_check, malos = [], []
    for a in man["archivos"]:
        cp = directorio / (a["ruta"] + ".CHECKSUM")
        if not cp.exists():
            sin_check.append(a["ruta"])
            continue
        zp = directorio / a["ruta"]
        if _checksum_de(cp.read_bytes(), zp.name) != hashlib.sha256(zp.read_bytes()).hexdigest():
            malos.append(a["ruta"])
    c1 = not malos and (not sin_check or man["procedencia"] != "historico_oficial")
    filtros["C1_procedencia"] = {"ok": c1, "procedencia": man["procedencia"], "via": man.get("via"),
                                 "archivos": len(man["archivos"]), "sin_checksum": len(sin_check),
                                 "checksum_no_coincide": malos[:10]}

    # C2 cobertura de meses requeridos
    meses_ventana = [f"{a}-{m:02d}" for a, m in meses(ini[:7], hasta[:7])]
    faltan = {t: [x for x in meses_ventana if x not in set(cob[t])] for t in ("spot", "perp", "mark", "funding")}
    c2 = not any(faltan.values())
    filtros["C2_cobertura"] = {"ok": c2, "inicio_comun": ini, "hasta": hasta, "meses": len(meses_ventana),
                               "primer_mes": {t: (v[0] if v else None) for t, v in cob.items()},
                               "faltan": {t: v[:12] for t, v in faltan.items() if v},
                               "meses_con_prima": len([x for x in cob["premium"] if x in set(meses_ventana)])}
    if not c2:
        return _cerrar(directorio, man, filtros, None)

    panel, inf = construir_panel(directorio, ini, hasta)
    clases = [i.clase for i in inf.incidencias]

    # C3 horas rellenadas
    rellenas = [b.relleno for b in panel.barras]
    racha = mejor = 0
    for r in rellenas:
        racha = racha + 1 if r else 0
        mejor = max(mejor, racha)
    frac = sum(rellenas) / len(rellenas)
    c3 = frac <= UMBRALES["horas_rellenadas_frac_max"] and mejor <= UMBRALES["racha_rellenada_max_h"]
    filtros["C3_horas"] = {"ok": c3, "horas": len(rellenas), "rellenadas": sum(rellenas), "fraccion": frac,
                           "racha_max_h": mejor}

    # C4 funding
    fi = inf.info.get("funding", {})
    malas_f = [str(i) for i in inf.incidencias if i.clase in UMBRALES["funding_bloqueantes"]]
    tasas = [e.tasa for e in panel.funding]
    filtros["C4_funding"] = {"ok": not malas_f, "incidencias": malas_f[:10], "eventos": len(tasas),
                             "intervalos_h": fi.get("intervalos_h"), "cambios": fi.get("cambios", [])[:10],
                             "tasa_modal": fi.get("tasa_modal"),
                             "fraccion_negativas": (sum(x < 0 for x in tasas) / len(tasas)) if tasas else None,
                             "apr_medio_nocional": apr_funding(panel.funding) if len(tasas) > 1 else None}

    # C5 coherencia entre series
    reales = [b for b in panel.barras if not b.relleno]
    base = [abs(b.F_c / b.S_c - 1) for b in reales]
    mark = [abs(b.M_c / b.F_c - 1) for b in reales]
    med_base = statistics.median(base)
    p99_mark = percentil_rango_cercano(mark, 0.99)
    malas_c = [str(i) for i in inf.incidencias if i.clase in UMBRALES["coherencia_bloqueantes"]]
    c5 = (not malas_c and med_base <= UMBRALES["base_mediana_abs_max"]
          and p99_mark <= UMBRALES["mark_perp_p99_abs_max"])
    filtros["C5_coherencia"] = {"ok": c5, "incidencias": malas_c[:10], "base_abs_mediana": med_base,
                                "base_abs_p99": percentil_rango_cercano(base, 0.99), "base_abs_max": max(base),
                                "mark_perp_abs_p99": p99_mark, "mark_perp_abs_max": max(mark)}

    # C6 período reservado (el cargador lo impide; se deja constancia)
    filtros["C6_periodo"] = {"ok": panel.fin <= ms("2026-06-01"), "inicio": iso(panel.inicio), "fin": iso(panel.fin)}
    otras = sorted({c for c in clases if c not in ("H1",)} - set(UMBRALES["funding_bloqueantes"])
                   - set(UMBRALES["coherencia_bloqueantes"]))
    if otras:
        filtros["otras_incidencias"] = {"ok": False, "clases": otras}
    return _cerrar(directorio, man, filtros, panel)


def _cerrar(directorio: Path, man: dict, filtros: dict, panel) -> dict:  # type: ignore[no-untyped-def]
    return {"directorio": str(directorio), "procedencia": man["procedencia"],
            "manifiesto_sha256": hashlib.sha256((directorio / "MANIFIESTO.json").read_bytes()).hexdigest(),
            "umbrales": UMBRALES, "filtros": filtros, "apto": all(f["ok"] for f in filtros.values()),
            "horas": len(panel.barras) if panel else None,
            "ventana": [iso(panel.inicio), iso(panel.fin)] if panel else None}


def markdown(inf: dict) -> str:
    aviso = ("**SINTÉTICO** — datos fabricados para ensayar el pipeline; no son datos de mercado."
             if inf["procedencia"] == "sintetico" else "Datos HISTÓRICOS oficiales (data.binance.vision).")
    lineas = ["# Informe de calidad de datos", "", aviso, "",
              f"- Directorio: `{inf['directorio']}`", f"- Manifiesto: `{inf['manifiesto_sha256']}`",
              f"- Ventana: {inf['ventana']}  ·  horas: {inf['horas']}",
              f"- **Apto para la evaluación: {'SÍ' if inf['apto'] else 'NO'}**", "",
              "| Filtro | Resultado | Detalle |", "|---|---|---|"]
    for nombre, f in inf["filtros"].items():
        detalle = {k: v for k, v in f.items() if k != "ok"}
        lineas.append(f"| {nombre} | {'OK' if f['ok'] else 'FALLA'} | `{json.dumps(detalle, ensure_ascii=False, default=str)[:400]}` |")
    lineas += ["", f"Umbrales (fijados antes de ver datos): `{json.dumps(inf['umbrales'], ensure_ascii=False)}`"]
    return "\n".join(lineas) + "\n"


__all__ = ["HORA_MS", "UMBRALES", "evaluar", "markdown"]
