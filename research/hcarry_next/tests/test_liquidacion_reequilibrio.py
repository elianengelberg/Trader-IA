"""Liquidación del corto (dentro de la barra y por salto de apertura), regla de enfriamiento, reequilibrio por banda,
neutralidad de las patas, costes y filtros."""

from __future__ import annotations

import pytest
from ayudas import INI, P0, barra, constante, panel

from hcarry.conventions import HORA_MS
from hcarry.data.schema import Panel
from hcarry.estrategias import Siempre
from hcarry.metricas import calcular
from hcarry.model.conciliacion import conciliar
from hcarry.model.costes import Costes, Filtros
from hcarry.model.motor import ParamsMotor, simular

Q = 0.083
W0 = 10_000 - Q * P0 - Q * 150
P_LIQ = (W0 + Q * P0) / (Q * 1.01)


def _con_pico(i_pico: int, n: int = 60, *, en_apertura: bool = False, nivel: float = 130_000.0) -> Panel:
    barras = []
    for i in range(n):
        t = INI + i * HORA_MS
        if i == i_pico and en_apertura:
            barras.append(barra(t, nivel, S_c=P0))
        elif i == i_pico:
            barras.append(barra(t, P0, M_h=nivel, F_h=nivel))
        else:
            barras.append(barra(t, P0))
    return Panel(barras, [], "sintetico:prueba")


def test_liquidacion_dentro_de_la_barra_a_mano() -> None:
    p = _con_pico(5)
    r = simular(p, Siempre())
    assert len(r.liquidaciones) == 1
    liq = r.liquidaciones[0]
    assert liq["t"] == INI + 5 * HORA_MS and liq["precio"] == pytest.approx(P_LIQ) and not liq["en_apertura"]
    # el equity de futuros que queda es el margen de mantenimiento: mmr · q · P_liq
    W_tras = W0 + Q * (P0 - P_LIQ)
    assert W_tras == pytest.approx(0.01 * Q * P_LIQ, rel=1e-12)
    # siguiente apertura: se vende el spot descubierto; tras el enfriamiento (24 h) se vuelve a entrar
    tipos = [(o["tipo"], (o["t"] - INI) // HORA_MS) for o in r.operaciones]
    assert tipos[1] == ("venta_spot_descubierto", 6)
    assert tipos[2][0] == "apertura" and tipos[2][1] >= 5 + 24
    E_tras_venta = W_tras + Q * P0 - Q * P0 * 15e-4
    assert r.serie[6][1] == pytest.approx(E_tras_venta, abs=1e-6)
    conciliar(r, p)
    m = calcular(r)
    assert m["liquidaciones"] == 1 and m["rev5"]["resultado"] == "DESCARTADA" and "D2" in m["rev5"]["criterios_activos"]


def test_liquidacion_por_salto_de_apertura_y_fondo_de_seguros() -> None:
    p = _con_pico(5, en_apertura=True, nivel=125_000.0)
    r = simular(p, Siempre())
    liq = r.liquidaciones[0]
    assert liq["en_apertura"] and liq["precio"] == 125_000.0
    # W + q·(Fb − 125 000) < 0: el fondo de seguros absorbe el déficit (asiento 'nota' con su ajuste)
    deficit = W0 + Q * (P0 - 125_000.0)
    assert deficit < 0
    notas = [a for a in r.asientos if a["tipo"] == "nota"]
    assert len(notas) == 1 and notas[0]["ajuste"] == pytest.approx(-deficit)
    d = conciliar(r, p)
    assert d.ajustes == pytest.approx(-deficit)


def test_reequilibrio_al_salir_de_la_banda_y_neutralidad() -> None:
    precios = [P0 * 1.01 ** k for k in range(50)]
    p = panel(precios)
    r = simular(p, Siempre())
    red = [o for o in r.operaciones if o["tipo"] == "reduccion"]
    assert red, "debía reequilibrar"
    k = (red[0]["t"] - INI) // HORA_MS
    # ρ = (W + q(Fb − F)) / (qF) < 0,5 por primera vez cuando F > (W/q + Fb)/1,5
    umbral = (W0 / Q + P0) / 1.5
    assert precios[k] > umbral and all(precios[j] <= umbral for j in range(k))
    E = r.serie[k - 1][1] if k > 0 else 10_000
    assert red[0]["lotes_despues"] == pytest.approx(E / (2 * precios[k]) / 0.001, abs=2)
    for s in r.serie:
        assert s[4] == s[5]  # lotes spot = lotes perp en todo cierre
    conciliar(r, p)


def test_costes_y_filtros_unitarios() -> None:
    c = Costes()
    assert c.coste("spot", 10_000) == pytest.approx(15.0) and c.coste("perp", 10_000) == pytest.approx(10.0)
    assert Costes(impacto_bps_raiz=10).coste("perp", 10_000, 1_000_000) == pytest.approx(10_000 * (10 + 1) * 1e-4)
    assert c.escalados(2).coste("spot", 10_000) == pytest.approx(30.0)
    f = Filtros(max_lotes=50)
    assert f.lotes(0.0839999) == 83 and f.lotes(0.084) == 84 and f.lotes(-1) == 0
    assert f.ordenes(120) == 3 and f.ordenes(0) == 0
    assert f.motivo_rechazo(1, 60_000, 60_000, False).startswith("nocional perp")
    assert f.motivo_rechazo(1, 60_000, 60_000, True) is None


def test_division_por_maximos_se_informa() -> None:
    r = simular(constante(24), Siempre(), filtros=Filtros(max_lotes=50))
    assert r.operaciones[0]["ordenes"] == 2 and r.operaciones[0]["lotes"] == 83


def test_estres_retraso_y_pata_adversa() -> None:
    precios = [P0 * 1.01 ** k for k in range(50)]
    base = simular(panel(precios), Siempre())
    tarde = simular(panel(precios), Siempre(), params=ParamsMotor(retraso_barras=1))
    assert tarde.operaciones[0]["t"] == base.operaciones[0]["t"] + HORA_MS
    t_red = next(o["t"] for o in base.operaciones if o["tipo"] == "reduccion")
    assert next(o["t"] for o in tarde.operaciones if o["tipo"] == "reduccion") == t_red + HORA_MS
    p = Panel([barra(INI + i * HORA_MS, P0, F_h=P0 * 1.002, F_l=P0 * 0.998) for i in range(24)], [], "sintetico:prueba")
    adv = simular(p, Siempre(), params=ParamsMotor(pata_perp_adversa=True))
    assert adv.operaciones[0]["F"] == P0 * 0.998 and adv.operaciones[-1]["F"] == P0 * 1.002
    assert adv.final < simular(p, Siempre()).final
    conciliar(adv, p)
    conciliar(tarde, panel(precios))


def test_la_liquidacion_cancela_las_ordenes_pendientes() -> None:
    """Retraso de 2 h. En la hora 4 el precio sube un 40 % (ρ < 0,5): se DECIDE reequilibrar, para ejecutar en la 6.
    En la 5 el mark alcanza la liquidación. La orden pendiente ya no es válida: no puede ejecutarse en la 6 ni
    reabrir posición durante el enfriamiento de 24 h."""
    barras = []
    for i in range(60):
        t = INI + i * HORA_MS
        precio = P0 if i < 4 else 1.4 * P0
        barras.append(barra(t, precio, M_h=250_000.0, F_h=250_000.0) if i == 5 else barra(t, precio))
    p = Panel(barras, [], "sintetico:prueba")
    r = simular(p, Siempre(), params=ParamsMotor(retraso_barras=2))
    t_liq = r.liquidaciones[0]["t"]
    assert t_liq == INI + 5 * HORA_MS
    assert not any(o["t"] == INI + 6 * HORA_MS and o["tipo"] != "venta_spot_descubierto" for o in r.operaciones)
    assert all(o["t"] >= t_liq + 24 * HORA_MS for o in r.operaciones if o["tipo"] == "apertura" and o["t"] > t_liq)
    conciliar(r, p)
