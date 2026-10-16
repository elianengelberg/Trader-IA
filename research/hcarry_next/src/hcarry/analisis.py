"""Aritmética de la estructura del carry, válida con cualquier dato (se deriva de las convenciones del modelo).

Con ratio de futuros ρ, el equity desplegado es q·S + ρ·q·F ≈ q·P·(1 + ρ), así que:
  - fracción del equity que es nocional del corto:   1 / (1 + ρ)
  - rendimiento del funding sobre el equity:          APR_nocional / (1 + ρ)
  - APR sobre nocional necesario para un objetivo:    (objetivo + coste anual) · (1 + ρ)
  - salto de precio que liquida desde el borde inferior de la banda (ρ = lo), dentro de una hora sin reequilibrar:
        x = (lo − mmr) / (1 + mmr)
  - ida y vuelta: 2 · (bps spot + bps perp) sobre el nocional; días para amortizarla a un APR dado:
        días = coste_ida_vuelta / APR · 365"""

from __future__ import annotations

from hcarry.model.costes import Costes


def estructura(rho: float, lo: float, mmr: float = 0.01, objetivo_equity: float = 0.06,
               coste_anual_equity: float = 0.0) -> dict:
    frac = 1 / (1 + rho)
    return {"rho": rho, "banda_inferior": lo, "nocional_sobre_equity": frac,
            "apr_necesario_para_objetivo": (objetivo_equity + coste_anual_equity) * (1 + rho),
            "salto_que_liquida_desde_lo": (lo - mmr) / (1 + mmr)}


def amortizacion(apr_nocional: float, costes: Costes | None = None) -> dict:
    costes = costes or Costes()
    ida_vuelta = 2 * (costes.bps("spot") + costes.bps("perp")) * 1e-4 * costes.multiplicador
    return {"apr_nocional": apr_nocional, "coste_ida_vuelta_nocional": ida_vuelta,
            "dias_para_amortizar": ida_vuelta / apr_nocional * 365 if apr_nocional > 0 else None}


def tabla_markdown() -> str:
    filas = [("| ρ (margen/nocional) | banda | nocional / equity | APR sobre nocional para 6 % sobre equity | "
             "salto horario que liquida desde el borde inferior |"), "|---|---|---|---|---|"]
    for rho, lo, hi in ((1.0, 0.5, 1.5), (0.75, 0.45, 1.1), (0.5, 0.3, 0.75), (0.33, 0.2, 0.5)):
        e = estructura(rho, lo)
        filas.append(f"| {rho:g} | ({lo:g}; {hi:g}) | {e['nocional_sobre_equity']:.1%} | "
                     f"{e['apr_necesario_para_objetivo']:.1%} | +{e['salto_que_liquida_desde_lo']:.1%} |")
    filas += ["", "| APR sobre nocional | días para amortizar la ida y vuelta (50 bps de nocional) |", "|---|---|"]
    for apr in (0.03, 0.05, 0.11, 0.20, 0.30):
        a = amortizacion(apr)
        filas.append(f"| {apr:.0%} | {a['dias_para_amortizar']:.1f} |")
    return "\n".join(filas)
