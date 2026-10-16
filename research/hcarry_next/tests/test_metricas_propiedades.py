"""Métricas (percentiles, caída máxima con el final, clasificación rev. 5, años) y propiedades sobre configuraciones
aleatorias: conciliación independiente, neutralidad de las patas y saldos no negativos."""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hcarry.data.sintetico import ParamsSintetico, generar
from hcarry.estrategias import EscalaPorVolatilidad, RhoPorVolatilidad, Siempre, UmbralFunding
from hcarry.metricas import caida_maxima, calcular, clasificar_rev5, percentil_rango_cercano
from hcarry.model.conciliacion import conciliar
from hcarry.model.costes import Costes, Filtros
from hcarry.model.motor import ParamsMotor, simular


def test_percentil_rango_cercano_y_caida_maxima() -> None:
    assert percentil_rango_cercano(list(range(1, 21)), 0.95) == 19
    assert percentil_rango_cercano([7.0], 0.95) == 7.0 and percentil_rango_cercano([], 0.95) is None
    assert caida_maxima([100, 120, 90, 130]) == pytest.approx(0.25)
    assert caida_maxima([100, 110, 105, 95]) == pytest.approx(15 / 110)  # el punto final cuenta (D4 rev. 5)


@pytest.mark.parametrize("estado, cagr, liq, p95, dd, entradas, esperado", [
    ("detenida_E1", 0.2, 0, 1.0, 0.11, 1, "DESCARTADA"),
    ("detenida_E1", 0.2, 0, 1.0, 0.05, 1, "SIN VEREDICTO"),
    ("completada", 0.2, 0, None, 0.0, 0, "SIN VEREDICTO"),
    ("completada", 0.2, 1, 1.0, 0.0, 1, "DESCARTADA"),
    ("completada", 0.06, 0, 1.0, 0.0, 1, "DESCARTADA"),
    ("completada", 0.2, 0, 50.0, 0.0, 1, "NO DESCARTADA"),
    ("completada", 0.2, 0, 50.01, 0.0, 1, "DESCARTADA"),
    ("completada", 0.2, 0, 1.0, 0.10, 1, "NO DESCARTADA"),
    ("completada", 0.065, 0, 1.0, 0.0, 1, "NO DESCARTADA"),
])
def test_clasificacion_rev5(estado, cagr, liq, p95, dd, entradas, esperado) -> None:  # type: ignore[no-untyped-def]
    m = {"estado": estado, "cagr_neto": cagr, "liquidaciones": liq, "base_adversa_p95_bps": p95, "caida_maxima": dd,
         "entradas": entradas}
    assert clasificar_rev5(m)["resultado"] == esperado


def test_por_ano_compone_el_total() -> None:
    p = generar(ParamsSintetico(semilla=2, desde="2020-03-15", hasta="2022-08-01"))
    m = calcular(simular(p, Siempre()))
    total = math.prod(1 + x for x in m["por_ano"].values())
    assert list(m["por_ano"]) == ["2020", "2021", "2022"]
    assert total == pytest.approx(m["final"] / m["capital"], rel=1e-12)


PANELES = {s: generar(ParamsSintetico(semilla=s, desde="2021-01-01", hasta="2021-03-01")) for s in (1, 2, 3)}


@st.composite
def configuraciones(draw):  # type: ignore[no-untyped-def]
    rho = draw(st.floats(0.35, 1.3))
    lo = draw(st.floats(0.3, 0.9)) * rho
    hi = rho * draw(st.floats(1.1, 2.0))
    tipo = draw(st.sampled_from(["siempre", "umbral", "rho_vol", "escala_vol"]))
    if tipo == "siempre":
        pol = Siempre(rho=rho, banda=(lo, hi))
    elif tipo == "umbral":
        e = draw(st.floats(-0.05, 0.3))
        pol = UmbralFunding(ventana=draw(st.integers(2, 30)), entrada=e, salida=e - draw(st.floats(0, 0.2)),
                            permanencia_h=draw(st.integers(0, 100)), rho=rho, banda=(lo, hi))
    elif tipo == "rho_vol":
        pol = RhoPorVolatilidad(rho_base=rho, rho_min=0.3, rho_max=1.5, vol_ref=draw(st.floats(0.2, 1.0)))
    else:
        pol = EscalaPorVolatilidad(base=Siempre(rho=rho, banda=(lo, hi)), vol_obj=draw(st.floats(0.1, 1.0)))
    costes = Costes(multiplicador=draw(st.floats(0.0, 4.0)), impacto_bps_raiz=draw(st.sampled_from([0.0, 50.0])))
    filtros = Filtros(nocional_min_perp=draw(st.sampled_from([5.0, 100.0])), max_lotes=draw(st.sampled_from([None, 30])))
    params = ParamsMotor(capital=draw(st.sampled_from([1_000.0, 10_000.0, 250_000.0, 1e7, 1e8])),
                         apalancamiento_max=draw(st.floats(1.0, 5.0)), retraso_barras=draw(st.integers(0, 2)),
                         pata_perp_adversa=draw(st.booleans()), al_inviable="omitir",
                         comision_liquidacion=draw(st.sampled_from([0.0, 0.005])))
    return draw(st.sampled_from([1, 2, 3])), pol, costes, filtros, params


@settings(max_examples=60, derandomize=True, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(configuraciones())
def test_propiedades_contables(cfg) -> None:  # type: ignore[no-untyped-def]
    semilla, pol, costes, filtros, params = cfg
    p = PANELES[semilla]
    r = simular(p, pol, costes, filtros, params)
    d = conciliar(r, p)
    assert r.final >= 0 and d.costes >= 0
    liq_t = {x["t"] for x in r.liquidaciones}
    for s in r.serie:
        t, _, U, W, ls, lp = s[:6]
        assert U >= -1e-6 and W >= -1e-6
        assert ls == lp or (t - 3_600_000) in liq_t  # descubierto solo en la hora de la liquidación
    m = calcular(r)
    assert 0 <= m["caida_maxima"] <= 1 and 0 <= m["tiempo_en_mercado"] <= 1
