"""Contabilidad calculada a mano y regresión contra resultados DOCUMENTADOS de rev. 5.

Las cifras de rev. 5 proceden del ejemplo sintético de su plantilla de informe (Universo(tasa=0.001): 72 h a 60 000,
funding cada 8 h) y de las pruebas recuperadas (tests/test_hc_decisiones.py: c1, d1, d1b). El código original se
perdió; aquí se comprueba que la reconstrucción reproduce esos números."""

from __future__ import annotations

import pytest
from ayudas import P0, constante, panel

from hcarry.estrategias import Siempre
from hcarry.metricas import calcular
from hcarry.model.conciliacion import conciliar
from hcarry.model.costes import Filtros
from hcarry.model.motor import ParamsMotor, simular

Q = 0.083  # 10 000 / (2 · 60 000) descontando costes, redondeado a 0,001 BTC
COSTE_LADO = Q * P0 * 25e-4  # spot 10+5 bps y perp 5+5 bps sobre el nocional


def test_apertura_reproduce_rev5_a_mano() -> None:
    r = simular(constante(72), Siempre())
    apertura = r.operaciones[0]
    assert apertura["tipo"] == "apertura" and apertura["lotes"] == 83 and apertura["t"] == r.inicio
    _, E, U, W, ls, lp, Fb, _ = r.serie[0]
    assert U == 0 and ls == lp == 83 and Fb == P0
    assert W == pytest.approx(10_000 - Q * P0 - Q * 150, abs=1e-9)          # rev. 5, prueba c1
    assert E == pytest.approx(10_000 - COSTE_LADO, abs=1e-9)
    m_liq = (W + Q * P0) / (Q * 1.01)                                       # precio de liquidación del modelo
    assert r.distancia_min_liquidacion == (pytest.approx(m_liq / P0 - 1, abs=1e-12), r.inicio)
    assert round(m_liq / P0 - 1, 6) == pytest.approx(0.985675, abs=1e-6)     # cifra documentada en rev. 5


def test_regresion_ejemplo_de_la_plantilla_rev5() -> None:
    """Plantilla rev. 5: equity final 10014.94, costes 24.90, funding 39.84 (8 liquidaciones cobradas de 9),
    CAGR 0.2022473335, días 2.9583, caída máxima 0.001245."""
    r = simular(constante(72, tasa=0.001), Siempre())
    m = calcular(r)
    conciliar(r, constante(72, tasa=0.001))
    assert len(r.funding) == 8                         # la de la hora de entrada no se cobra; la de salida sí
    assert m["costes"] == pytest.approx(24.90, abs=1e-9)
    assert m["funding_neto"] == pytest.approx(39.84, abs=1e-9)
    assert r.final == pytest.approx(10_014.94, abs=1e-9)
    assert m["dias"] == pytest.approx(71 / 24) and round(m["dias"], 4) == 2.9583
    assert round(m["cagr_neto"], 10) == pytest.approx(0.2022473335, abs=1e-10)
    assert m["caida_maxima"] == pytest.approx(0.001245, abs=1e-12)
    assert m["pnl_precio_patas"] == pytest.approx(0.0, abs=1e-9)
    assert m["rev5"]["resultado"] == "NO DESCARTADA" and m["rev5"]["banda"].startswith("> 7 %")


def test_funding_negativo_se_paga() -> None:
    r = simular(constante(72, tasa=-0.0002), Siempre())
    assert r.funding_total == pytest.approx(-8 * Q * P0 * 0.0002, abs=1e-9)
    assert r.final == pytest.approx(10_000 - 2 * COSTE_LADO - 8 * Q * P0 * 0.0002, abs=1e-9)


def test_d1_dias_fijos_aunque_la_entrada_se_retrase() -> None:
    """Prueba d1b de rev. 5: la orden mínima de 0,09 BTC no cabe a 60 000 y sí a 50 000 (hora 10); D = (n − 1)/24."""
    n = 30
    precios = [P0 if t < 10 else 50_000.0 for t in range(n)]
    r = simular(panel(precios), Siempre(), filtros=Filtros(min_lotes=90))
    assert r.operaciones[0]["t"] == r.inicio + 10 * 3_600_000 and r.operaciones[0]["lotes"] >= 90
    assert len(r.rechazos) == 10
    assert calcular(r)["dias"] == pytest.approx((n - 1) / 24)


def test_sin_entrada_es_sin_veredicto() -> None:
    r = simular(constante(48), Siempre(), filtros=Filtros(nocional_min_perp=1e9))
    m = calcular(r)
    assert r.operaciones == [] and len(r.rechazos) == 47
    assert m["rev5"]["resultado"] == "SIN VEREDICTO" and r.final == pytest.approx(10_000)


def test_regla_r0_detiene_si_la_ampliacion_es_inviable() -> None:
    """Con apalancamiento máximo 1 casi no hay transferible de futuros: al caer el precio, ampliar es inviable.
    R0 ('detener') termina la simulación; 'omitir' la deja seguir."""
    precios = [P0 * (0.99 ** k) for k in range(60)]
    detenida = simular(panel(precios), Siempre(), params=ParamsMotor(apalancamiento_max=1.0, al_inviable="detener"))
    sigue = simular(panel(precios), Siempre(), params=ParamsMotor(apalancamiento_max=1.0))
    assert detenida.estado == "detenida_E1" and "inviable" in detenida.notas[-1]
    assert sigue.estado == "completada" and any("limitada" in x["motivo"] for x in sigue.rechazos)
    conciliar(detenida, panel(precios))
    conciliar(sigue, panel(precios))
