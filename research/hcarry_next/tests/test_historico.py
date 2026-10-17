"""Evaluador histórico prerregistrado: criterios de conclusión, separación de categorías y parada por calidad."""

from __future__ import annotations

import copy
from pathlib import Path

from hcarry.data.fabricar import fabricar_sintetico
from hcarry.data.sintetico import ParamsSintetico, generar
from hcarry.lab import historico as H


def _s(d_pnl: float, p: float, estres: float = 1.0, val: float = 1.0, dd_umbral: float = 0.02,
       liq: int = 0, cagr_rev5: float = 0.06, cagr_rev5_x2: float = 0.05) -> dict:
    sens = {e: {"umbral_menos_rev5_pnl": estres, "rev5": {"cagr_neto": cagr_rev5_x2}, "umbral": {}}
            for e in ("costes_x2", "pata_adversa", "retraso_3h")}
    return {"test": {"umbral": {"pnl_neto": 100 + d_pnl, "caida_maxima": dd_umbral, "liquidaciones": liq},
                     "rev5": {"pnl_neto": 100.0, "caida_maxima": 0.03, "cagr_neto": cagr_rev5},
                     "bootstrap_umbral_menos_rev5": {"p_mayor_que_cero": p}, "sensibilidad": sens},
            "validacion": {"umbral_menos_rev5": {"pnl": val}}}


def test_criterios_prerregistrados() -> None:
    assert H.concluir("historico", _s(50, 0.97))["P1_umbral_vs_rev5"] == "VENTAJA RESPALDADA"
    assert H.concluir("historico", _s(-5, 0.97))["P1_umbral_vs_rev5"] == "HIPÓTESIS NO RESPALDADA"
    assert H.concluir("historico", _s(50, 0.40))["P1_umbral_vs_rev5"] == "HIPÓTESIS NO RESPALDADA"
    assert H.concluir("historico", _s(50, 0.80))["P1_umbral_vs_rev5"] == "EVIDENCIA INSUFICIENTE"
    assert H.concluir("historico", _s(50, 0.97, estres=-1))["P1_umbral_vs_rev5"] == "EVIDENCIA INSUFICIENTE"
    assert H.concluir("historico", _s(50, 0.97, val=-1))["P1_umbral_vs_rev5"] == "EVIDENCIA INSUFICIENTE"
    assert H.concluir("historico", _s(50, 0.97, dd_umbral=0.09))["P1_umbral_vs_rev5"] == "EVIDENCIA INSUFICIENTE"
    # P2: el carry de rev. 5
    assert H.concluir("historico", _s(0, 0.5, cagr_rev5=0.07, cagr_rev5_x2=0.01))["P2_carry_rev5"] == "VENTAJA RESPALDADA"
    assert H.concluir("historico", _s(0, 0.5, cagr_rev5=-0.01))["P2_carry_rev5"] == "HIPÓTESIS NO RESPALDADA"
    assert H.concluir("historico", _s(0, 0.5, cagr_rev5=0.04))["P2_carry_rev5"] == "EVIDENCIA INSUFICIENTE"
    # datos sintéticos: nunca pueden respaldar nada
    c = H.concluir("sintetico", _s(50, 0.99, cagr_rev5=0.2))
    assert c["P1_umbral_vs_rev5"] == c["P2_carry_rev5"] == "EVIDENCIA INSUFICIENTE" and "SINTÉTICOS" in c["motivo"]


def test_prerregistro_estable_y_sin_parametros_libres() -> None:
    antes = copy.deepcopy(H.PRERREGISTRO)
    assert H.hash_prerregistro() == H.hash_prerregistro() and H.PRERREGISTRO == antes
    assert H.PRERREGISTRO["politicas"]["umbral"]["params"] == {"ventana": 21, "entrada": 0.10, "salida": 0.03,
                                                               "permanencia_h": 72, "rho": 1.0, "banda": [0.5, 1.5]}
    assert set(H.PRERREGISTRO["sensibilidad"]) >= {"costes_x2", "pata_adversa", "retraso_3h"}


def test_datos_no_aptos_detienen_la_evaluacion_y_se_archivan_como_sinteticos(tmp_path: Path) -> None:
    p = generar(ParamsSintetico(semilla=4, desde="2024-11-01", hasta="2025-02-01"))
    d = tmp_path / "fab"
    fabricar_sintetico(type(p)(p.barras, [e for i, e in enumerate(p.funding) if i != 50], p.origen), d)  # hueco A2
    s = H.evaluar(d, tmp_path / "resultados")
    assert s["categoria"] == "sintetico" and "/sintetico/" in s["destino"] and not s["calidad_apta"]
    assert s["conclusion"]["P1_umbral_vs_rev5"] == "EVIDENCIA INSUFICIENTE" and "no se simuló" in s["conclusion"]["motivo"]
    assert not (Path(s["destino"]) / "registro.jsonl").exists()
    texto = (Path(s["destino"]) / "INFORME.md").read_text(encoding="utf-8")
    assert "SINTÉTICO" in texto and "No es evidencia económica" in texto and "prospectiva: **ninguna**" in texto


def test_el_test_historico_tiene_un_cerrojo_global_independiente_de_los_datos(tmp_path: Path, monkeypatch) -> None:
    import pytest
    raiz = tmp_path / "resultados"
    H.comprobar_test_disponible(raiz)  # libre
    H.reservar_test(raiz, {"manifiesto_sha256": "a" * 64})
    with pytest.raises(H.TestYaConsumido):
        H.comprobar_test_disponible(raiz)
    with pytest.raises(FileExistsError):  # la reserva es exclusiva
        H.reservar_test(raiz, {"manifiesto_sha256": "b" * 64})
    # una descarga nueva (otro manifiesto, otra carpeta) tampoco puede repetir el test: se rechaza antes de todo
    monkeypatch.setattr(H, "leer_manifiesto", lambda d: {"procedencia": "historico_oficial"})
    with pytest.raises(H.TestYaConsumido):
        H.evaluar(tmp_path / "otra_descarga", raiz)

