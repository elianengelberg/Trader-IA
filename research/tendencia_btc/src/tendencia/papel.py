"""Evaluación EN PAPEL (prospectiva) con reglas CONGELADAS. Sin órdenes ni dinero real.

La validez prospectiva no depende de registrar nada cada día: las reglas, los parámetros, los criterios y la huella del
código quedan fijados en un commit (fecha de GitHub) ANTES de que existan los datos evaluados. Cualquiera puede
recalcular después, de forma determinista, con los archivos oficiales diarios (data.binance.vision, con .CHECKSUM).

Dos ramas prerregistradas, según lo que decida el usuario sobre el período reservado de H-CARRY (2026-06-01 → 13-10):
  A · se autoriza usar sus PRECIOS solo como historia de la señal (nunca para evaluar): se evalúa desde 2026-10-18;
  B · no se autoriza: la señal solo usa días ≥ 2026-10-14 y la evaluación empieza cuando hay 180 días de historia.
Hasta que el usuario decida, el evaluador funciona en la rama B (no toca el período reservado)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import statistics as st
from pathlib import Path

from hcarry.data.binance_vision import _abrir_http, _bajar_verificado, _escribir_manifiesto, leer_funding

from tendencia.backtest import Costes, simular
from tendencia.datos import RESERVADO_FIN, RESERVADO_INICIO, leer
from tendencia.estadistica import bootstrap_media
from tendencia.metricas import calcular, rendimientos
from tendencia.senal import tsmom

SRC = Path(__file__).resolve().parent

PRERREGISTRO_PAPEL: dict = {
    "version": 1, "fecha_congelado": "2026-10-17",
    "naturaleza": "evaluación prospectiva en papel; sin órdenes, claves ni dinero real",
    "estrategias": {
        "T_BTC": {"simbolo": "BTCUSDT", "senal": "tsmom", "ventanas": [30, 90, 180]},
        "T_ETH": {"simbolo": "ETHUSDT", "senal": "tsmom", "ventanas": [30, 90, 180]},
    },
    "reglas": {"decision": "con el cierre diario UTC del día d", "ejecucion": "apertura oficial del día d + 1",
               "opera": "solo cuando cambia el objetivo (0, 1/3, 2/3, 1)", "costes_bps": {"comision": 10, "slippage": 5},
               "efectivo": "USDT al 0 %", "capital": 10_000, "apalancamiento": "ninguno; sin cortos"},
    "benchmarks": ["buy and hold con coste de entrada", ("estática con la misma exposición media (rebalanceo diario, sin "
                   "costes)"), "efectivo al 0 %"],
    "datos": "data.binance.vision spot/daily/klines/{SIMBOLO}/1d con .CHECKSUM; funding: futures/um/monthly/fundingRate",
    "ramas": {"A": {"historia_de_senal_desde": "2026-04-20", "usa_reservado_como_historia": True,
                    "primera_ejecucion": "2026-10-18"},
              "B": {"historia_de_senal_desde": RESERVADO_FIN, "usa_reservado_como_historia": False,
                    "primera_ejecucion": "primer día con 180 cierres ≥ 2026-10-14 (2027-04-13)"}},
    "metrica_principal": "exceso de timing = media diaria (estrategia − estática con su misma exposición), media BTC+ETH",
    "inferencia": {"bootstrap_bloque_dias": 20, "remuestreos": 2000, "semilla": 20261017},
    "criterios": {
        "antes_de_12_meses": "solo informativo: ninguna decisión",
        "HIPOTESIS_NO_RESPALDADA_detener": "en un corte con ≥ 12 meses: P(exceso BTC+ETH > 0) < 0,10",
        "VENTAJA_RESPALDADA": "en un corte con ≥ 24 meses: P(exceso BTC+ETH > 0) ≥ 0,95, P(exceso BTC > 0) ≥ 0,90 y "
                              "exceso BTC+ETH > 0 con costes ×2",
        "EVIDENCIA_INSUFICIENTE": "en cualquier otro caso: continuar",
        "potencia": "con el efecto de desarrollo hacen falta ≈ 7 años para P ≥ 0,95 (papel/potencia.json); con la mitad, "
                    "≈ 28. Un resultado de 1–2 años solo puede descartar un fracaso grueso"},
    "monitor_carry": {"que": "funding medio de BTCUSDT (USDⓈ-M) de los 90 días previos, anualizado",
                      "disparador": "> 12 % anual: reabrir H-CARRY con un prerregistro prospectivo nuevo",
                      "fuente": "fundingRate mensual oficial (meses completos)"},
    "prohibido": ["cambiar reglas, parámetros o criterios después de ver datos prospectivos",
                  "usar los cortes intermedios para ajustar nada", "evaluar dentro del período reservado"],
}


def hash_prerregistro() -> str:
    return hashlib.sha256(json.dumps(PRERREGISTRO_PAPEL, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def huella_codigo() -> str:
    h = hashlib.sha256()
    for p in sorted(SRC.glob("*.py")):
        h.update(p.name.encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def ruta_diaria_1d(simbolo: str, fecha: str) -> str:
    return f"spot/daily/klines/{simbolo}/1d/{simbolo}-1d-{fecha}.zip"


def descargar(destino: Path, simbolo: str, desde: str, hasta: str, permitir_reservado: bool = False,
              abrir=_abrir_http) -> dict:  # type: ignore[no-untyped-def]
    """Velas diarias oficiales [desde, hasta). Ningún día del período reservado sin autorización explícita."""
    d, fin = dt.date.fromisoformat(desde), dt.date.fromisoformat(hasta)
    if d.isoformat() < RESERVADO_FIN and fin.isoformat() > RESERVADO_INICIO and not permitir_reservado:
        raise PermissionError("el rango toca el período reservado (2026-06-01 → 2026-10-13): requiere autorización")
    archivos, ausentes = [], []
    while d < fin:
        rel = ruta_diaria_1d(simbolo, d.isoformat())
        r = _bajar_verificado(destino, rel, abrir, 4)
        if r is None:
            ausentes.append(rel)
        else:
            archivos.append({"tipo": "spot_1d", "ruta": rel, "sha256": r["sha256"], "bytes": r["bytes"],
                             "checksum_oficial": r["checksum_oficial"]})
        d += dt.timedelta(days=1)
    man = {"procedencia": "historico_oficial", "uso": "evaluación en papel (prospectiva)", "simbolo": simbolo,
           "desde": desde, "hasta": hasta, "fecha_utc": dt.datetime.now(dt.UTC).isoformat(), "archivos": archivos,
           "ausentes": ausentes}
    _escribir_manifiesto(destino, man)
    return man


def primera_ejecucion(rama: str) -> str:
    if rama == "A":
        return PRERREGISTRO_PAPEL["ramas"]["A"]["primera_ejecucion"]
    return (dt.date.fromisoformat(RESERVADO_FIN) + dt.timedelta(days=max((30, 90, 180)) + 1)).isoformat()


def decidir(meses: float, p_conjunto: float, p_btc: float, exceso_x2: float) -> str:
    if meses < 12:
        return "INFORMATIVO (menos de 12 meses: ninguna decisión)"
    if p_conjunto < 0.10:
        return "HIPÓTESIS NO RESPALDADA: detener"
    if meses >= 24 and p_conjunto >= 0.95 and p_btc >= 0.90 and exceso_x2 > 0:
        return "VENTAJA RESPALDADA"
    return "EVIDENCIA INSUFICIENTE: continuar"


def _exceso(velas, desde: str, hasta: str, costes: Costes) -> tuple[list[float], dict]:  # type: ignore[no-untyped-def]
    s = simular(velas, tsmom([v.c for v in velas]), desde, hasta, costes=costes)
    wbar = st.fmean(s.exposicion)
    e = simular(velas, [wbar] * len(velas), desde, hasta, costes=Costes(0, 0), banda=0.0)
    bh = simular(velas, [1.0] * len(velas), desde, hasta)
    return [a - b for a, b in zip(rendimientos(s), rendimientos(e), strict=True)], {
        "T": calcular(s), "estatica": calcular(e), "buy_and_hold": calcular(bh), "exposicion_media": wbar}


def evaluar(dirs: dict[str, Path], corte: str, rama: str = "B") -> dict:
    """Resultados en papel desde la primera ejecución hasta ``corte`` (exclusivo), con la decisión prerregistrada."""
    inicio = primera_ejecucion(rama)
    out: dict = {"prerregistro_sha256": hash_prerregistro(), "codigo_sha256": huella_codigo(), "rama": rama,
                 "inicio": inicio, "corte": corte}
    if corte <= inicio:
        out["estado"] = "sin datos de evaluación todavía"
        return out
    excesos, excesos_x2 = {}, {}
    for k, d in dirs.items():
        velas, inf = leer(d, permitir_reservado=(rama == "A"), permitir_prospectivo=True)
        if inf["dias_ausentes"] or not inf["apto"]:
            out["estado"] = f"datos no aptos para {k}: {inf['dias_ausentes'][:5]}"
            return out
        excesos[k], out[k] = _exceso(velas, inicio, corte, Costes())
        excesos_x2[k], _ = _exceso(velas, inicio, corte, Costes(multiplicador=2))
    conj = [(a + b) / 2 for a, b in zip(excesos["T_BTC"], excesos["T_ETH"], strict=True)]
    conj_x2 = [(a + b) / 2 for a, b in zip(excesos_x2["T_BTC"], excesos_x2["T_ETH"], strict=True)]
    inf_cfg = PRERREGISTRO_PAPEL["inferencia"]
    kw = {"bloque": inf_cfg["bootstrap_bloque_dias"], "n": inf_cfg["remuestreos"], "semilla": inf_cfg["semilla"]}
    b_conj, b_btc = bootstrap_media(conj, **kw), bootstrap_media(excesos["T_BTC"], **kw)
    meses = len(conj) / 30.44
    out.update({"dias": len(conj), "meses": meses, "exceso_anual_conjunto": st.fmean(conj) * 365,
                "bootstrap_conjunto": b_conj, "bootstrap_btc": b_btc, "exceso_anual_conjunto_costes_x2": st.fmean(conj_x2) * 365})
    p = (lambda b: b.get("p_mayor_que_cero", 0.5))
    out["decision"] = decidir(meses, p(b_conj), p(b_btc), st.fmean(conj_x2))
    return out


def monitor_carry(dir_funding: Path, corte: str, rama: str = "B") -> dict:
    """Funding medio anualizado de BTCUSDT en los 90 días previos a ``corte`` (meses completos oficiales)."""
    desde = (dt.date.fromisoformat(corte) - dt.timedelta(days=90)).isoformat()
    if rama == "B" and desde < RESERVADO_FIN:
        return {"estado": f"ventana de 90 días incompleta sin el período reservado (desde {desde})"}
    man = json.loads((dir_funding / "MANIFIESTO.json").read_text(encoding="utf-8"))
    eventos = []
    for a in man["archivos"]:
        datos = (dir_funding / a["ruta"]).read_bytes()
        if hashlib.sha256(datos).hexdigest() != a["sha256"]:
            raise ValueError(f"{a['ruta']}: hash distinto del manifiesto")
        eventos += [(t, f) for t, f, _ in leer_funding(datos)
                    if desde <= dt.datetime.fromtimestamp(t / 1000, dt.UTC).date().isoformat() < corte]
    if not eventos:
        return {"estado": "sin eventos de funding en la ventana"}
    dias = 90
    apr = sum(f for _, f in eventos) * 365 / dias
    cobertura = len(eventos) / (dias * 3)
    return {"apr_90d": apr, "eventos": len(eventos), "cobertura": cobertura,
            "disparador_12pct": apr > 0.12 and cobertura > 0.95}
