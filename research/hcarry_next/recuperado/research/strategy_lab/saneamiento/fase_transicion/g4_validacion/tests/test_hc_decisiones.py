"""Pruebas SINTÉTICAS de las decisiones provisionales de cierre de H-CARRY rev. 5:
A. omisiones de funding: cuáles se detectan (y bloquean) y por qué la dirección del sesgo de las indetectables NO está
   garantizada (contraejemplos en los dos sentidos);
B/C. condiciones explícitas del veredicto y medidas de riesgo no decisorias (liquidación del modelo, base);
D1. 850,9583 días fijos, también si la entrada se retrasa;
exchangeInfo: la comprobación previa hace solo 2 peticiones de metadatos y exige autorización explícita."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
from fractions import Fraction as Q
from pathlib import Path

import pytest

H = Path(__file__).resolve().parents[1] / "h_carry"
T = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
sys.path.insert(0, str(T))

import ejecutor_hcarry  # noqa: F401  — carga el conjunto de módulos
import hc_comun as HC
import hc_metricas as MET
import hc_plan as PL
import hc_sintetico as SIN
import invariantes as INV
import modelo_carry as MC
import prechequeo_exchangeinfo as PRE

HORA = 3_600_000
INI = int(dt.datetime(2024, 3, 1, tzinfo=dt.timezone.utc).timestamp()) * 1000
V = (INI, INI + 72 * HORA)
P0 = Q(60_000)


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    SIN.bloquear_red(monkeypatch)


def incidencias(r: dict) -> set[str]:
    return {i["clase"] for i in r.get("incidencias", [])}


# ====================================================================== A. omisiones de funding
def _hora(h: int) -> int:
    return (h // HORA) % 24


@pytest.mark.parametrize("omitida, clase, texto", [
    (lambda h: h == V[0] + 24 * HORA, "A2", "hueco"),                       # una omitida en un calendario de 8 h
    (lambda h: h == V[0] + 64 * HORA, "A2", "final"),                       # la última
    (lambda h: h == V[0], "A2", "principio"),                               # la primera
], ids=["en_medio", "al_final", "al_principio"])
def test_a1_omisiones_detectables_en_8h_bloquean(tmp_path: Path, omitida, clase, texto) -> None:  # type: ignore[no-untyped-def]
    _, r = SIN.experimento(tmp_path / "exp", SIN.Universo(omitir_funding=omitida), V)
    assert r["resultado"] == "SIN VEREDICTO" and clase in incidencias(r) and "criterios" not in r
    assert any(texto in i["detalle"] for i in r["incidencias"])


def test_a1b_omision_detectable_en_4h_bloquea(tmp_path: Path) -> None:
    _, r = SIN.experimento(tmp_path / "exp", SIN.Universo(intervalo_h=4, omitir_funding=lambda h: h == V[0] + 36 * HORA), V)
    assert r["resultado"] == "SIN VEREDICTO" and incidencias(r) == {"A2b"}


@pytest.mark.parametrize("signo_par, sentido", [(1, "sobrestima"), (-1, "subestima")])
def test_a2_omision_indetectable_puede_sesgar_en_cualquier_direccion(tmp_path: Path, signo_par: int, sentido: str) -> None:
    """Calendario REAL de 4 h con tasas de signo alterno; el registro publicado omite las de las 04, 12 y 20 h, y lo
    que queda es un calendario de 8 h perfectamente regular: ninguna incidencia. Según el signo de lo omitido, el
    resultado observado SOBRESTIMA o SUBESTIMA el real: la dirección del sesgo no está garantizada."""
    tasa = lambda h: ("0.0005" if signo_par > 0 else "-0.0005") if _hora(h) % 8 == 0 else (  # noqa: E731
        "-0.0005" if signo_par > 0 else "0.0005")
    _, real = SIN.experimento(tmp_path / "real", SIN.Universo(intervalo_h=4, tasa=tasa), V)
    _, visto = SIN.experimento(tmp_path / "visto", SIN.Universo(intervalo_h=4, tasa=tasa, omitir_funding=lambda h: _hora(h) % 8 == 4), V)
    assert real["incidencias"] == visto["incidencias"] == []          # nada lo delata
    assert visto["integridad"]["funding"]["intervalos_h"] == {"8": 8} and real["integridad"]["funding"]["intervalos_h"] == {"4": 17}
    q = Q(83, 1000)
    omitidas = 9  # 04, 12 y 20 h de los tres días, todas con posición abierta
    assert visto["final"] - real["final"] == signo_par * omitidas * q * P0 * Q(5, 10_000)  # calculado a mano
    assert (visto["final"] > real["final"]) == (sentido == "sobrestima")


def test_a3_el_veredicto_lleva_sus_condiciones_y_sin_veredicto_no(tmp_path: Path) -> None:
    _, r = SIN.experimento(tmp_path / "ok", SIN.Universo(tasa="0.001"), V)
    ids = [c["id"] for c in r["condiciones_del_veredicto"]]
    assert ids == ["S10-funding", "S8-filtros", "S11-S13-margen", "S12-ejecucion", "S1-api"]
    assert "CUALQUIER dirección" in r["condiciones_del_veredicto"][0]["texto"]
    _, malo = SIN.experimento(tmp_path / "malo", SIN.Universo(omitir_funding=lambda h: h == V[0] + 24 * HORA), V)
    assert "condiciones_del_veredicto" not in malo


# ====================================================================== B/C. filtros y riesgo no decisorio
def test_b1_la_dependencia_de_los_filtros_queda_en_las_condiciones(tmp_path: Path) -> None:
    filtros = [f if f["filterType"] != "MARKET_LOT_SIZE" else {**f, "maxQty": "0.05"} for f in SIN.EXPERP["symbols"][0]["filters"]]
    _, r = SIN.experimento(tmp_path / "exp", SIN.Universo(tasa="0.001", experp={"symbols": [{**SIN.EXPERP["symbols"][0], "filters": filtros}]}), V)
    s8 = next(c for c in r["condiciones_del_veredicto"] if c["id"] == "S8-filtros")["texto"]
    assert "2 operaciones divididas (S7)" in s8 and "ningún escenario reconstruye los filtros históricos" in s8


def test_c1_distancia_a_la_liquidacion_del_modelo_a_mano(tmp_path: Path) -> None:
    _, r = SIN.experimento(tmp_path / "exp", SIN.Universo(tasa="0.001"), V)
    q = Q(83, 1000)
    W = 10_000 - q * P0 - q * 150                     # saldo de futuros tras la entrada (sin funding todavía)
    m_liq = (W + q * P0) / (q * Q(101, 100))           # el modelo liquida si el mark máximo llega aquí
    riesgo = r["informativo"]["riesgo_no_decisorio"]
    assert Q(riesgo["distancia_minima_a_liquidacion_del_modelo"]) == round(m_liq / P0 - 1, 6)  # en la hora de entrada
    assert riesgo["hora_ms"] == V[0] and Q(riesgo["base_maxima_en_cierre_bps"]) == 0
    assert m_liq / P0 - 1 > Q(98, 100)  # ≈ +98 %: el modelo casi nunca liquida (D2 no es evidencia de riesgo real)


# ====================================================================== D1. 850,9583 días fijos
def test_d1_dias_fijos_coinciden_con_el_borrador() -> None:
    p = json.loads((H / "protocolo_hcarry_v1_1_borrador.json").read_text(encoding="utf-8"))
    texto = p["metricas_decisorias"]["D1"]
    assert "850,9583" in texto and "FIJO" in texto and "aunque la entrada se retrase" in texto
    horas = (PL.CORTE_MS - PL.INICIO_MS) // HORA
    assert Q(horas - 1, 24) == Q(20_423, 24) and round(float(Q(20_423, 24)), 4) == 850.9583
    assert PL.CONFIG["criterios"]["D1"]["dias"] == "(horas de la ventana − 1)/24"
    original = json.loads((H / "protocolo_hcarry.json").read_text(encoding="utf-8"))
    assert "días" not in original["criterios"]["D1"]  # el 1.0 no fija el recuento de días: no hay conflicto


def test_d1b_entrada_retrasada_no_cambia_los_dias() -> None:
    """La menor orden válida (0,09 BTC) no cabe en el objetivo a 60 000 y sí a 50 000: la entrada se retrasa a la
    hora 10; D sigue siendo (n − 1)/24."""
    n = 30
    precio = [P0 if t < 10 else Q(50_000) for t in range(n + 1)]
    barras = [{"t": t, "S_o": precio[t], "F_o": precio[t], "M_o": precio[t], "S_c": precio[t + 1], "F_c": precio[t + 1],
               "M_c": precio[t + 1], "M_h": max(precio[t], precio[t + 1])} for t in range(n)]
    costes = MC.Costes(Q(10, 10_000), Q(5, 10_000), Q(5, 10_000), Q(5, 10_000))
    r = MC.simular(barras, {}, costes, capital=Q(10_000), mmr=Q(1, 100), lo=Q(1, 2), hi=Q(3, 2),
                   filtros=MC.FiltrosOrden(periodo=Q(1, 1000), minimo=Q(9, 100)), clase=INV.CarteraAuditada,
                   apalancamiento=Q(2), si_inviable="sin_veredicto")
    assert r["estado"] == "completada" and r["operaciones"][0]["t"] == 10 and len(r["rechazos"]) == 10
    assert MET.calcular(r, n, Q(10_000))["D1"]["dias"] == Q(n - 1, 24)


# ====================================================================== exchangeInfo: comprobación previa
def test_x1_solo_dos_peticiones_de_metadatos_y_resumen(tmp_path: Path) -> None:
    tr = SIN.TransporteFalso(SIN.Universo())
    res = PRE.comprobar(tr, tmp_path / "pre", autorizacion="REF-SINTÉTICA")
    assert [r for r, _ in tr.llamadas] == ["/api/v3/exchangeInfo", "/fapi/v1/exchangeInfo"]
    assert [p for _, p in tr.llamadas] == [{"symbol": "BTCUSDT"}, {}]
    assert res["apto"] and res["incidencias"] == [] and res["parametros"]["periodo"] == Q(1, 1000)
    assert res["tipos"]["spot"]["filtros"]["PRICE_FILTER"]["clase"] == "no aplicable (S6)"
    for sha in res["sha256"].values():
        assert hashlib.sha256((tmp_path / "pre" / "datos" / f"{sha}.json").read_bytes()).hexdigest() == sha
    assert json.loads((tmp_path / "pre" / "resumen.json").read_bytes())["apto"] is True


def test_x2_filtro_desconocido_o_reticula_vacia_no_es_apto(tmp_path: Path) -> None:
    ajeno = {"symbols": [{**SIN.EXPERP["symbols"][0], "filters": SIN.EXPERP["symbols"][0]["filters"] + [
        {"filterType": "POSITION_RISK_CONTROL", "positionControlSide": "NONE"}]}]}
    res = PRE.comprobar(SIN.TransporteFalso(SIN.Universo(experp=ajeno)), autorizacion="REF")
    assert not res["apto"] and {i["clase"] for i in res["incidencias"]} == {"M1"}
    assert res["tipos"]["perp"]["filtros"]["POSITION_RISK_CONTROL"]["clase"] == "DESCONOCIDO"
    q1 = json.loads(json.dumps(SIN.EXSPOT))
    q1["symbols"][0]["filters"][1]["minQty"] = "0.0015"
    res = PRE.comprobar(SIN.TransporteFalso(SIN.Universo(exspot=q1)), autorizacion="REF")
    assert not res["apto"] and {i["clase"] for i in res["incidencias"]} == {"Q1"}


def test_x3_sin_autorizacion_no_hay_ninguna_peticion(tmp_path: Path) -> None:
    tr = SIN.TransporteFalso(SIN.Universo())
    with pytest.raises(PermissionError):
        PRE.comprobar(tr, autorizacion=" ")
    assert tr.llamadas == []
    r = subprocess.run([sys.executable, "-I", "-B", str(H / "prechequeo_exchangeinfo.py"), "--salida", str(tmp_path / "x")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "sin autorización" in r.stderr and not (tmp_path / "x").exists()
    assert all(p["tipo"] == "exchangeinfo" for p in PRE.PETICIONES) and len(PRE.PETICIONES) == 2
    assert "prechequeo_exchangeinfo" not in HC.MODULOS  # no es parte del experimento ni de su identidad
