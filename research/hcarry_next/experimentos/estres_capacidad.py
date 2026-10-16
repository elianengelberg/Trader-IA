"""Estrés y capacidad en mundos SINTÉTICOS (toda la ventana 2019-10 → 2026-05). No es evidencia económica: mide cuánto
dependen las estrategias de cada supuesto del modelo.

Uso: python -B experimentos/estres_capacidad.py"""

from __future__ import annotations

import copy
import json
import statistics
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "src"))

from hcarry.lab import experimento as X
from hcarry.lab.protocolo import BASE_APALANCADA, REFERENCIA

VENTANA = {"desde": "2019-10-01", "hasta": "2026-06-01"}
SEMILLAS = (101, 102, 103, 104, 105, 106)
POLITICAS = {
    "referencia": REFERENCIA,
    "siempre_rho05": BASE_APALANCADA,
    "umbral_v21_e0.1_s0.03": {"nombre": "umbral_funding",
                              "params": {"ventana": 21, "entrada": 0.10, "salida": 0.03, "permanencia_h": 72}},
    "prima_v24_e0.05_s0.0": {"nombre": "umbral_prima",
                             "params": {"ventana_h": 24, "entrada": 0.05, "salida": 0.0, "permanencia_h": 24}},
}
ESCENARIOS = {
    "base": {},
    "costes_x2": {"costes": {"multiplicador": 2.0}},
    "costes_x3": {"costes": {"multiplicador": 3.0}},
    "retraso_1h": {"motor": {"retraso_barras": 1}},
    "retraso_3h": {"motor": {"retraso_barras": 3}},
    "pata_adversa": {"motor": {"pata_perp_adversa": True}},
    "funding_x05": {"estres": {"funding_factor": 0.5}},
    "omitir_10pc_funding": {"estres": {"omitir_funding": 0.10, "semilla": 1}},
    "liquidacion_fee_05pc": {"motor": {"comision_liquidacion": 0.005}},
}
SALTOS = {"prob_salto_h": 0.004, "salto_sd": 0.07}
CAPITALES = (1e4, 1e6, 1e7, 1e8)


def cfg(nombre: str, datos: dict, pol: dict, extra: dict) -> dict:
    c = {"nombre": nombre, "datos": datos, "division": VENTANA, "politica": copy.deepcopy(pol), "costes": {},
         "filtros": {}, "motor": {}}
    for k, v in extra.items():
        c[k] = {**c.get(k, {}), **v}
    return c


def main() -> None:
    salida = AQUI / (sys.argv[1] if len(sys.argv) > 1 else "estres")
    registro = salida / "registro.jsonl"
    filas = []
    for s in SEMILLAS:
        for mundo, datos in (("normal", {"fuente": "sintetico", "semilla": s}),
                             ("saltos", {"fuente": "sintetico", "semilla": s, **SALTOS}),
                             ("bajista_suave", {"fuente": "sintetico", "semilla": s, "variante": "bajista_suave"})):
            escenarios = ESCENARIOS if mundo != "saltos" else {"base": {}}
            for esc, extra in escenarios.items():
                for nombre, pol in POLITICAS.items():
                    _, m, _ = X.correr(cfg(f"{nombre}__{esc}__{mundo}", datos, pol, extra), registro)
                    filas.append({"semilla": s, "mundo": mundo, "escenario": esc, "politica": nombre,
                                  "cagr": m["cagr_neto"], "dd": m["caida_maxima"], "liq": m["liquidaciones"],
                                  "dmin": m["distancia_min_liquidacion"], "costes": m["costes"],
                                  "funding": m["funding_neto"]})
        datos = {"fuente": "sintetico", "semilla": s}
        for capital in CAPITALES:
            for nombre in ("referencia", "siempre_rho05"):
                extra = {"motor": {"capital": capital}, "costes": {"impacto_bps_raiz": 10.0}}
                _, m, _ = X.correr(cfg(f"{nombre}__capital{capital:g}", datos, POLITICAS[nombre], extra), registro)
                filas.append({"semilla": s, "mundo": "normal", "escenario": f"capital_{capital:g}_impacto10",
                              "politica": nombre, "cagr": m["cagr_neto"], "dd": m["caida_maxima"],
                              "liq": m["liquidaciones"], "dmin": m["distancia_min_liquidacion"],
                              "costes": m["costes"] / capital, "funding": m["funding_neto"] / capital})
        print(f"semilla {s} hecha", flush=True)
    (salida / "filas.json").write_text(json.dumps(filas, indent=1), encoding="utf-8")
    # resumen: mediana por escenario y política
    resumen = {}
    for f in filas:
        resumen.setdefault((f["mundo"], f["escenario"], f["politica"]), []).append(f)
    lineas = ["| mundo | escenario | política | CAGR mediano | CAGR mín | caída máx. mediana | liquidaciones (total) |",
              "|---|---|---|---|---|---|---|"]
    for (mundo, esc, pol), fs in resumen.items():
        lineas.append(f"| {mundo} | {esc} | {pol} | {statistics.median(x['cagr'] for x in fs):.2%} | "
                      f"{min(x['cagr'] for x in fs):.2%} | {statistics.median(x['dd'] for x in fs):.2%} | "
                      f"{sum(x['liq'] for x in fs)} |")
    (salida / "resumen.md").write_text("SINTÉTICO — no es evidencia económica.\n\n" + "\n".join(lineas) + "\n",
                                                encoding="utf-8")
    print("\n".join(lineas))


if __name__ == "__main__":
    main()
