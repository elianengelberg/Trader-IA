"""T fuera de muestra (PRERREGISTRO_FUERA_DE_MUESTRA_T.md): la regla congelada, sin cambios, en [2022-01-01, 2026-06-01).
Una sola ejecución: se niega a correr si el resultado ya existe. Histórico verificado, fuera de muestra para T; NO es
prospectivo y no toca el experimento en papel."""

from __future__ import annotations

import hashlib
import json
import statistics as st
import sys
from pathlib import Path

from tendencia import papel as P
from tendencia.backtest import Costes, simular
from tendencia.datos import leer
from tendencia.estadistica import bootstrap_media, desplazamientos
from tendencia.metricas import rendimientos
from tendencia.senal import tsmom

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
PRERREGISTRO = RAIZ / "PRERREGISTRO_FUERA_DE_MUESTRA_T.md"
SALIDA = AQUI / "fuera_de_muestra_T.json"
CODIGO = "73b22f3e3a8f21513d5533fb11a7553becae30b87c8736fb6880bccc36c11d2b"
DESDE, HASTA, DIAS = "2022-01-01", "2026-06-01", 1612
SUBVENTANAS = {"2022-2023": ("2022-01-01", "2024-01-01"), "2024-01_a_2026-05": ("2024-01-01", "2026-06-01")}
DESARROLLO = "2018-02-14"
KW = {"bloque": 20, "n": 2000, "semilla": 20261017}
SIMBOLOS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def exceso(v, desde: str, hasta: str, **kw) -> list[float]:  # type: ignore[no-untyped-def]
    """La fórmula de ``tendencia.papel._exceso`` con ``simular(**kw)`` (para el retraso de ejecución)."""
    s = simular(v, tsmom([x.c for x in v]), desde, hasta, **kw)
    wbar = st.fmean(s.exposicion)
    e = simular(v, [wbar] * len(v), desde, hasta, costes=Costes(0, 0), banda=0.0)
    return [a - b for a, b in zip(rendimientos(s), rendimientos(e), strict=True)]


def decision(p_conj: float, p_btc: float, exceso_x2: float) -> str:
    if p_conj >= 0.95 and p_btc >= 0.90 and exceso_x2 > 0:
        return "RESPALDADA FUERA DE MUESTRA"
    if p_conj < 0.10:
        return "NO RESPALDADA"
    return "EVIDENCIA INSUFICIENTE"


def resumen(velas: dict, desde: str, hasta: str, costes: Costes = Costes()) -> dict:  # noqa: B008
    """Exceso por activo y conjunto (la métrica del papel) con bootstrap, más las métricas de T y sus benchmarks."""
    out: dict = {"ventana": [desde, hasta]}
    exc = {}
    for k, v in velas.items():
        exc[k], info = P._exceso(v, desde, hasta, costes)
        b = bootstrap_media(exc[k], **KW)
        out[k] = {"exceso_anual": b["media_anual"], "ic90_anual": b["intervalo_anual"], "p": b["p_mayor_que_cero"],
                  "exposicion_media": info["exposicion_media"],
                  **{n: {m: info[n][m] for m in ("cagr", "vol_anual", "sharpe", "caida_maxima", "exposicion_media",
                                                  "operaciones", "costes_pp_anual", "por_ano")}
                     for n in ("T", "estatica", "buy_and_hold")}}
    conj = [(a + b) / 2 for a, b in zip(exc["BTC"], exc["ETH"], strict=True)]
    b = bootstrap_media(conj, **KW)
    out["conjunto"] = {"exceso_anual": b["media_anual"], "ic90_anual": b["intervalo_anual"], "p": b["p_mayor_que_cero"]}
    return out


def main() -> None:
    if SALIDA.exists():
        sys.exit(f"{SALIDA} ya existe: el prerregistro permite una sola ejecución")
    if P.huella_codigo() != CODIGO:
        sys.exit("código de src/ distinto del congelado")
    velas, manifiestos = {}, {}
    for k, s in SIMBOLOS.items():
        v, inf = leer(RAIZ / "datos" / s)  # sin permitir_reservado: el período de H-CARRY no se lee
        dias = [x.dia for x in v if DESDE <= x.dia < HASTA]
        if inf["dias_ausentes"] or not inf["apto"] or len(dias) != DIAS or (dias[0], dias[-1]) != (DESDE, "2026-05-31"):
            sys.exit(f"{s}: datos no aptos para la ventana")
        velas[k], manifiestos[s] = v, inf["manifiesto_sha256"]
    for v in velas.values():  # la réplica de la fórmula congelada coincide exactamente
        assert exceso(v, DESDE, HASTA) == P._exceso(v, DESDE, HASTA, Costes())[0]

    principal = resumen(velas, DESDE, HASTA)
    x2 = resumen(velas, DESDE, HASTA, Costes(multiplicador=2))
    dec = decision(principal["conjunto"]["p"], principal["BTC"]["p"], x2["conjunto"]["exceso_anual"])

    sec: dict = {"subventanas": {n: resumen(velas, a, b) for n, (a, b) in SUBVENTANAS.items()},
                 "costes_x2": {k: x2[k]["exceso_anual"] for k in ("BTC", "ETH", "conjunto")},
                 "costes_x3": {k: r["exceso_anual"] for k, r in resumen(velas, DESDE, HASTA, Costes(multiplicador=3)).items()
                               if k != "ventana"}}
    ret = {k: exceso(v, DESDE, HASTA, retraso=1) for k, v in velas.items()}
    sec["retraso_1_dia"] = {k: st.fmean(x) * 365 for k, x in ret.items()}
    sec["retraso_1_dia"]["conjunto"] = st.fmean([(a + b) / 2 for a, b in zip(ret["BTC"], ret["ETH"], strict=True)]) * 365

    v = velas["BTC"]  # nulo por desplazamiento circular del objetivo de T, como en desarrollo
    obj = tsmom([x.c for x in v])
    idx = [i for i, x in enumerate(v) if DESDE <= x.dia < HASTA]
    seg = [obj[i - 1] for i in idx]
    t = simular(v, obj, DESDE, HASTA)
    est = simular(v, [st.fmean(t.exposicion)] * len(v), DESDE, HASTA, costes=Costes(0, 0), banda=0.0)
    obs = st.fmean(rendimientos(t)) - st.fmean(rendimientos(est))
    nulos = []
    for k in desplazamientos(len(seg), n=1000):
        o: list[float | None] = [None] * len(v)
        for i, w in zip(idx, seg[k:] + seg[:k], strict=True):
            o[i - 1] = w
        nulos.append(st.fmean(rendimientos(simular(v, o, DESDE, HASTA))) - st.fmean(rendimientos(est)))
    sec["nulo_circular_BTC"] = {"exceso_anual_observado": obs * 365, "percentil": sum(x < obs for x in nulos) / len(nulos)}

    dev = json.loads((RAIZ / "papel" / "potencia.json").read_text(encoding="utf-8"))
    sec["replicacion"] = {}
    for k, d in (("BTC", "BTCUSDT"), ("ETH", "ETHUSDT"), ("conjunto", "BTC+ETH (media)")):
        e_dev, r = dev[d]["exceso_anual_desarrollo"], principal[k]
        sec["replicacion"][k] = {"desarrollo": e_dev, "fuera_de_muestra": r["exceso_anual"],
                                 "cociente": r["exceso_anual"] / e_dev,
                                 "desarrollo_dentro_del_ic90": r["ic90_anual"][0] <= e_dev <= r["ic90_anual"][1]}
    sec["desarrollo_mas_fuera_de_muestra"] = resumen(velas, DESARROLLO, HASTA)
    sec["efectivo"] = {"cagr": 0.0, "nota": "USDT al 0 %"}

    out = {"categoria": "HISTÓRICO VERIFICADO, fuera de muestra para T (no prospectivo)",
           "prerregistro_sha256": _sha(PRERREGISTRO), "script_sha256": _sha(Path(__file__)), "codigo_sha256": CODIGO,
           "manifiestos_sha256": manifiestos, "ventana": [DESDE, HASTA], "dias": DIAS,
           "decision_prerregistrada": dec, "principal": principal, "secundarios": sec}
    texto = json.dumps(out, indent=1, ensure_ascii=False, default=float)
    SALIDA.write_text(texto + "\n", encoding="utf-8")
    c, b, e = principal["conjunto"], principal["BTC"], principal["ETH"]
    print("DECISIÓN PRERREGISTRADA:", dec)
    for n, r in (("conjunto", c), ("BTC", b), ("ETH", e)):
        print(f"  {n:9s} exceso {r['exceso_anual']:+.1%}/año  IC90 [{r['ic90_anual'][0]:+.1%}, {r['ic90_anual'][1]:+.1%}]"
              f"  P {r['p']:.3f}")
    print("  costes x2:", {k: f"{x:+.1%}" for k, x in sec["costes_x2"].items()})


if __name__ == "__main__":
    main()
