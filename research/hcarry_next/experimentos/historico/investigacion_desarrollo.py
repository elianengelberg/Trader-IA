"""Investigación SOLO en desarrollo (2020-01 → 2022-12), datos HISTÓRICOS oficiales.

E1 · Atribución de umbral − rev. 5: funding que rev. 5 cobró (o pagó) mientras UmbralFunding estaba fuera, costes
     extra y patas de precio.
E3 · Techo de cualquier regla de salida: con conocimiento PERFECTO del funding futuro (oráculo, no realizable), ¿cuánto
     habría ganado salir del carry en los tramos de funding desfavorable, pagando el coste real de ida y vuelta?
     Si el techo es pequeño, ninguna regla realizable puede aportar más.

Uso: PYTHONPATH=src .venv/bin/python -B experimentos/historico/investigacion_desarrollo.py"""

from __future__ import annotations

import json
from pathlib import Path

from hcarry.lab import experimento as X
from hcarry.lab import historico as H

AQUI = Path(__file__).resolve().parent
DATOS = {"fuente": "binance_vision", "directorio": str(AQUI.parents[1] / "datos" / "binance_vision"),
         "desde": "2020-01-01", "hasta": "2026-06-01"}
COSTE_IDA_VUELTA = 2 * (10 + 5 + 5 + 5) * 1e-4  # entrada + salida, spot (10 + 5 bps) y perpetuo (5 + 5 bps)


def e1(rev5, umb) -> dict:  # type: ignore[no-untyped-def]
    dentro = {fila[0]: fila[5] != 0 for fila in umb.serie}  # t_cierre → umbral con posición
    fuera_pos = fuera_neg = dentro_f = 0.0
    for x in rev5.funding:
        if dentro.get(x["t"], dentro.get(x["t"] + 3_600_000, True)):
            dentro_f += x["importe"]
        elif x["importe"] >= 0:
            fuera_pos += x["importe"]
        else:
            fuera_neg += x["importe"]
    dif = umb.final - rev5.final
    return {"diferencia_pnl": dif,
            "funding_rev5_mientras_umbral_fuera_positivo": fuera_pos,
            "funding_rev5_mientras_umbral_fuera_negativo_evitado": fuera_neg,
            "funding_neto_umbral_menos_rev5": umb.funding_total - rev5.funding_total,
            "costes_extra_umbral": umb.costes_total - rev5.costes_total,
            "resto_patas_y_tamano": dif - (umb.funding_total - rev5.funding_total) + (umb.costes_total - rev5.costes_total)}


def e3(rev5) -> dict:  # type: ignore[no-untyped-def]
    """Programación dinámica sobre los eventos de funding de rev. 5 (en fracción del nocional): elegir tramos fuera del
    mercado que maximicen el funding negativo evitado menos el positivo perdido, con un coste de ida y vuelta por tramo."""
    f = [x["tasa"] for x in rev5.funding]
    dentro, fuera = 0.0, -COSTE_IDA_VUELTA  # valor acumulado estando dentro / fuera (la salida paga la ida y vuelta)
    tramos_d, tramos_f = 0, 1
    for x in f:
        nd_desde_d, nd_desde_f = dentro + x, fuera + x  # volver a entrar no cuesta más: ya se pagó al salir
        nf_desde_f, nf_desde_d = fuera, dentro - COSTE_IDA_VUELTA
        dentro, td = (nd_desde_d, tramos_d) if nd_desde_d >= nd_desde_f else (nd_desde_f, tramos_f)
        fuera, tf = (nf_desde_f, tramos_f) if nf_desde_f >= nf_desde_d else (nf_desde_d, tramos_d + 1)
        tramos_d, tramos_f = td, tf
    siempre = sum(f)
    mejor = max(dentro, fuera)
    tramos = tramos_d if dentro >= fuera else tramos_f
    anos = len(f) / (3 * 365)
    nocional_sobre_equity = 0.5  # ρ = 1: nocional ≈ la mitad del equity
    return {"funding_siempre_frac_nocional": siempre, "oraculo_frac_nocional": mejor,
            "ganancia_oraculo_frac_nocional": mejor - siempre, "tramos_fuera_oraculo": tramos,
            "ganancia_oraculo_pp_equity_anual": (mejor - siempre) * nocional_sobre_equity / anos * 100,
            "coste_ida_vuelta_frac_nocional": COSTE_IDA_VUELTA, "anos": anos,
            "nota": "techo NO realizable: conoce el futuro; con coste ×2 el techo sería menor"}


def e3_costes(rev5, mult: float) -> float:
    global COSTE_IDA_VUELTA
    base = COSTE_IDA_VUELTA
    COSTE_IDA_VUELTA = base * mult
    try:
        return e3(rev5)["ganancia_oraculo_pp_equity_anual"]
    finally:
        COSTE_IDA_VUELTA = base


def main() -> None:
    pols = H.PRERREGISTRO["politicas"]
    rev5 = X.correr(H._cfg("inv_rev5", DATOS, "desarrollo", pols["rev5"]))[0]
    umb = X.correr(H._cfg("inv_umbral", DATOS, "desarrollo", pols["umbral"]))[0]
    out = {"categoria": "HISTÓRICO verificado, SOLO desarrollo", "codigo_sha256": X.huella_codigo(),
           "E1_atribucion": e1(rev5, umb), "E3_techo_oraculo": e3(rev5),
           "E3_techo_pp_anual_por_coste": {str(k): e3_costes(rev5, k) for k in (0.5, 1, 2)}}
    destino = AQUI / "desarrollo" / "investigacion.json"
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
