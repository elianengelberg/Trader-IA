"""Laboratorio: guarda del test (prerregistro y uso único), registro reproducible, mundos nulos, bootstrap y
aritmética de la estructura de capital."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from hcarry.analisis import amortizacion, estructura
from hcarry.lab import experimento as X
from hcarry.lab.estadistica import bootstrap_media

DATOS = {"fuente": "sintetico", "semilla": 7, "desde": "2023-06-01", "hasta": "2024-06-01"}


def _cfg(division, nombre="ref"):  # type: ignore[no-untyped-def]
    return {"nombre": nombre, "datos": DATOS, "division": division,
            "politica": {"nombre": "siempre", "params": {"rho": 1.0, "banda": [0.5, 1.5]}},
            "costes": {}, "filtros": {}, "motor": {}}


def test_registro_reproducible(tmp_path: Path) -> None:
    reg = tmp_path / "registro.jsonl"
    _, m1, e1 = X.correr(_cfg({"desde": "2023-07-01", "hasta": "2023-10-01"}), reg)
    _, m2, e2 = X.correr(_cfg({"desde": "2023-07-01", "hasta": "2023-10-01"}, "otro_nombre"), reg)
    assert m1["final"] == m2["final"] and e1["id"] == e2["id"]  # el nombre no cambia la identidad
    lineas = reg.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2
    e = json.loads(lineas[0])
    assert e["codigo_sha256"] == X.huella_codigo() and e["datos"]["sintetico"] and "SINTÉTICO" in e["aviso"]


def test_test_exige_prerregistro_y_solo_una_vez(tmp_path: Path) -> None:
    reg, pre = tmp_path / "registro.jsonl", tmp_path / "pre.json"
    with pytest.raises(X.AccesoTestDenegado, match="prerregistro"):
        X.correr(_cfg("test"), reg, None)
    pre.write_text(json.dumps({"configuraciones": [_cfg("validacion")]}), encoding="utf-8")
    with pytest.raises(X.AccesoTestDenegado, match="no prerregistrada"):
        X.correr(_cfg("test"), reg, pre)
    pre.write_text(json.dumps({"configuraciones": [_cfg("test")]}), encoding="utf-8")
    X.correr(_cfg("test"), reg, pre)
    with pytest.raises(X.AccesoTestDenegado, match="ya se evaluó"):
        X.correr(_cfg("test", "con otro nombre"), reg, pre)


def test_mundo_nulo_conserva_las_tasas_y_rompe_el_orden() -> None:
    base, _ = X.cargar_datos(DATOS)
    nulo, _ = X.cargar_datos({**DATOS, "nulo_semilla": 3})
    assert Counter(e.tasa for e in base.funding) == Counter(e.tasa for e in nulo.funding)
    assert [e.t for e in base.funding] == [e.t for e in nulo.funding]
    assert [e.tasa for e in base.funding] != [e.tasa for e in nulo.funding] and "nulo" in nulo.origen


def test_bootstrap_casos_limite() -> None:
    assert bootstrap_media([0.0] * 100)["p_mayor_que_cero"] == 0.0
    assert bootstrap_media([0.001] * 100)["p_mayor_que_cero"] == 1.0
    assert not bootstrap_media([0.001] * 30)["aplicable"]
    import random
    rng = random.Random(1)
    x = [rng.gauss(0, 0.01) for _ in range(400)]
    media = sum(x) / len(x)
    r = bootstrap_media([v - media for v in x], bloque=10)  # media exactamente 0
    assert 0.2 < r["p_mayor_que_cero"] < 0.8 and r["intervalo_anual"][0] < 0 < r["intervalo_anual"][1]


def test_aritmetica_de_la_estructura() -> None:
    e = estructura(1.0, 0.5)
    assert e["nocional_sobre_equity"] == 0.5 and e["apr_necesario_para_objetivo"] == pytest.approx(0.12)
    assert e["salto_que_liquida_desde_lo"] == pytest.approx(0.49 / 1.01)
    assert estructura(0.5, 0.3)["apr_necesario_para_objetivo"] == pytest.approx(0.09)
    assert amortizacion(0.11)["coste_ida_vuelta_nocional"] == pytest.approx(0.005)
    assert amortizacion(0.11)["dias_para_amortizar"] == pytest.approx(0.005 / 0.11 * 365)


@pytest.mark.parametrize("rho, banda", [(1.0, (0.5, 1.5)), (0.5, (0.3, 0.75))])
def test_el_motor_cumple_la_aritmetica_de_la_estructura(rho: float, banda: tuple) -> None:
    """Un año a precio constante con funding de 1 bp cada 8 h: rendimiento ≈ APR/(1 + ρ) − ida y vuelta."""
    from ayudas import constante

    from hcarry.estrategias import Siempre
    from hcarry.model.motor import simular
    n = 365 * 24 + 1
    r = simular(constante(n, tasa=0.0001), Siempre(rho=rho, banda=banda))
    apr = 0.0001 * 3 * 365
    q = r.operaciones[0]["cantidad"]
    nocional = q * 60_000.0
    assert r.final == pytest.approx(10_000 + nocional * 0.0001 * 1095 - 2 * nocional * 0.0025, abs=1e-6)  # exacto
    esperado = apr / (1 + rho) - 0.005 / (1 + rho)  # ida y vuelta: 50 bps del nocional
    assert r.final / r.capital - 1 == pytest.approx(esperado, abs=1e-3)  # salvo el redondeo a lotes de 0,001 BTC


def test_protocolo_estructura_fija() -> None:
    """El protocolo es finito y estable: 39 candidatos, cada uno con su línea base, y un hash reproducible."""
    from hcarry.lab import protocolo as P
    c = P.candidatos()
    assert len(c) == 63 and len({n for _, n, _, _ in c}) == 63
    assert {b for *_, b in c} == set(P.BASES)
    assert all(b == "siempre_rho05" for f, _, _, b in c if f in ("rho_vol", "umbral_apalancado", "prima_apalancada"))
    assert P.hash_protocolo() == P.hash_protocolo() and len(P.hash_protocolo()) == 64


def test_estres_de_funding() -> None:
    base, _ = X.cargar_datos(DATOS)
    mitad = X.aplicar_estres(base, {"funding_factor": 0.5})
    assert [e.tasa for e in mitad.funding] == [e.tasa * 0.5 for e in base.funding]
    menos = X.aplicar_estres(base, {"omitir_funding": 0.1, "semilla": 1})
    assert 0.8 * len(base.funding) < len(menos.funding) < len(base.funding)
    assert X.aplicar_estres(base, {"omitir_funding": 0.1, "semilla": 1}).funding == menos.funding  # reproducible
    assert "estrés" in menos.notas[-1]
