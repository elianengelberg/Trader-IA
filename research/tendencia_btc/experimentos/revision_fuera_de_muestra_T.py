"""Revisión crítica (POSTERIOR, descriptiva) del resultado fuera de muestra de T. No cambia la decisión prerregistrada ni
reescribe el experimento: lee ``fuera_de_muestra_T.json``, lo recalcula con el código congelado, lo reproduce con una
implementación independiente leída directamente de los zip oficiales y analiza la incertidumbre (dependencia temporal,
correlación BTC–ETH, observaciones efectivas, potencia). Usa la misma ventana ya consumida; no es una prueba nueva."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import itertools
import json
import math
import random
import statistics as st
import zipfile
from pathlib import Path
from statistics import NormalDist

from tendencia import papel as P
from tendencia.backtest import Costes
from tendencia.datos import leer
from tendencia.estadistica import bootstrap_media
from tendencia.senal import tsmom

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
DESDE, HASTA, DEV = "2022-01-01", "2026-06-01", "2018-02-14"
KW = {"bloque": 20, "n": 2000, "semilla": 20261017}
N = NormalDist()
SIM = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}


# ---------- implementación independiente (no usa tendencia.backtest, senal ni datos) ----------
def velas_zip(simbolo: str) -> list[tuple[str, float, float]]:
    """(día, apertura, cierre) leídos de los zip oficiales, comprobando el SHA-256 de cada uno contra el manifiesto."""
    man = json.loads((RAIZ / "datos" / simbolo / "MANIFIESTO.json").read_text(encoding="utf-8"))
    out = {}
    for a in man["archivos"]:
        b = (RAIZ / "datos" / simbolo / a["ruta"]).read_bytes()
        assert hashlib.sha256(b).hexdigest() == a["sha256"], a["ruta"]
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            for fila in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8")):
                if not fila[0].isdigit():
                    continue
                t = int(fila[0])
                t = t // 1000 if t > 10 ** 15 else t  # µs en el spot desde 2025
                dia = dt.datetime.fromtimestamp(t / 1000, dt.UTC).date().isoformat()
                out[dia] = (dia, float(fila[1]), float(fila[4]))
    return [out[d] for d in sorted(out)]


def senal(c: list[float]) -> list[float | None]:
    return [None if d < 180 else sum(c[d] > c[d - w] for w in (30, 90, 180)) / 3 for d in range(len(c))]


def cartera(v, objetivo, desde, hasta, tasa, diario=False):  # type: ignore[no-untyped-def]
    """Equity al cierre: decide con el cierre de d−1, opera en la apertura de d; ``diario``: rebalanceo cada día."""
    caja, q, ult, eq, expo = 10_000.0, 0.0, None, [], []
    for i, (dia, o, c) in enumerate(v):
        if not desde <= dia < hasta:
            continue
        obj = objetivo[i - 1] if objetivo[i - 1] is not None else 0.0
        e = caja + q * o
        if diario or obj != ult:
            valor = obj * e - q * o
            caja -= valor + abs(valor) * tasa
            q += valor / o
            ult = obj
        eq.append(caja + q * c)
        expo.append(q * c / eq[-1])
    r = [b / a - 1 for a, b in zip([10_000.0, *eq], eq, strict=False)]
    return r, expo, eq


def exceso_independiente(v, desde, hasta, tasa=0.0015):  # type: ignore[no-untyped-def]
    rt, expo, _ = cartera(v, senal([x[2] for x in v]), desde, hasta, tasa)
    wbar = st.fmean(expo)
    re, _, _ = cartera(v, [wbar] * len(v), desde, hasta, 0.0, diario=True)
    return [a - b for a, b in zip(rt, re, strict=True)]


# ---------- estadística ----------
def hac_se(x: list[float], lags: int) -> float:
    """Error estándar de la media con Newey–West (núcleo de Bartlett)."""
    n, m = len(x), st.fmean(x)
    d = [a - m for a in x]
    g = [sum(d[t] * d[t - k] for t in range(k, n)) / n for k in range(lags + 1)]
    return math.sqrt((g[0] + 2 * sum((1 - k / (lags + 1)) * g[k] for k in range(1, lags + 1))) / n)


def acf(x: list[float], k: int) -> float:
    m = st.fmean(x)
    d = [a - m for a in x]
    return sum(d[t] * d[t - k] for t in range(k, len(d))) / sum(a * a for a in d)


def se_bootstrap(b: dict) -> float:
    return (b["intervalo_anual"][1] - b["intervalo_anual"][0]) / (2 * N.inv_cdf(0.95))


def prob_papel(btc, eth, btc2, eth2, efecto, dias, n_sim=2000, semilla=1):  # type: ignore[no-untyped-def]
    """Monte Carlo de la decisión del papel con trayectorias remuestreadas por bloques de 20 días de las series fuera de
    muestra, recentradas para que el exceso conjunto verdadero sea ``efecto`` (anual). P se aproxima con error por
    medias de bloques (el papel usa bootstrap; aproximación declarada)."""
    rng = random.Random(semilla)
    ajuste = []
    for s in (btc, eth, btc2, eth2):
        ajuste.append(efecto / 365 - st.fmean(s))
    series = [[a + d for a in s] for s, d in zip((btc, eth, btc2, eth2), ajuste, strict=True)]
    m = len(btc)
    resp = det = 0
    for _ in range(n_sim):
        idx = []
        while len(idx) < dias:
            ini = rng.randrange(m)
            idx += [(ini + j) % m for j in range(20)]
        idx = idx[:dias]
        b, e, b2, e2 = ([s[i] for i in idx] for s in series)
        conj = [(x + y) / 2 for x, y in zip(b, e, strict=True)]
        conj2 = [(x + y) / 2 for x, y in zip(b2, e2, strict=True)]

        def p(z: list[float]) -> float:
            lotes = [st.fmean(z[k:k + 20]) for k in range(0, len(z) - 19, 20)]
            return N.cdf(st.fmean(z) / (st.stdev(lotes) / math.sqrt(len(lotes))))
        pc = p(conj)
        resp += pc >= 0.95 and p(b) >= 0.90 and st.fmean(conj2) > 0
        det += pc < 0.10
    return {"respaldada": resp / n_sim, "detener_p_menor_0_10": det / n_sim}


def main() -> None:
    fm = json.loads((AQUI / "fuera_de_muestra_T.json").read_text(encoding="utf-8"))
    out: dict = {"categoria": "REVISIÓN POSTERIOR y descriptiva de un resultado histórico ya consumido; no cambia su "
                              "decisión prerregistrada", "fuera_de_muestra_json_sha256":
                 hashlib.sha256((AQUI / "fuera_de_muestra_T.json").read_bytes()).hexdigest()}
    velas = {k: leer(RAIZ / "datos" / s)[0] for k, s in SIM.items()}

    # 1. reproducción con el código congelado y con la implementación independiente
    exc, x2, info = {}, {}, {}
    for k, v in velas.items():
        exc[k], info[k] = P._exceso(v, DESDE, HASTA, Costes())
        x2[k] = P._exceso(v, DESDE, HASTA, Costes(multiplicador=2))[0]
    conj = [(a + b) / 2 for a, b in zip(exc["BTC"], exc["ETH"], strict=True)]
    b = bootstrap_media(conj, **KW)
    p = fm["principal"]["conjunto"]
    out["reproduccion"] = {"exceso_anual": b["media_anual"], "ic90": b["intervalo_anual"], "p": b["p_mayor_que_cero"],
                           "identico_al_json": [b["media_anual"], b["intervalo_anual"], b["p_mayor_que_cero"]] ==
                           [p["exceso_anual"], p["ic90_anual"], p["p"]]}
    indep = {}
    for k, s in SIM.items():
        vi = velas_zip(s)
        assert [x[0] for x in vi] == [x.dia for x in velas[k]]
        e = exceso_independiente(vi, DESDE, HASTA)
        indep[k] = {"dias": len(e), "exceso_anual": st.fmean(e) * 365,
                    "max_dif_diaria_con_congelado": max(abs(a - c) for a, c in zip(e, exc[k], strict=True))}
    out["implementacion_independiente"] = indep

    # 2. dependencia temporal, correlación y observaciones efectivas
    n = len(conj)
    se_iid = st.stdev(conj) / math.sqrt(n) * 365
    bloques = {L: bootstrap_media(conj, bloque=L, n=2000, semilla=20261017) for L in (1, 5, 10, 20, 40, 60, 120, 250)}
    out["dependencia"] = {
        "acf_exceso_conjunto": {k: acf(conj, k) for k in (1, 2, 5, 10, 20, 60)},
        "acf_cuadrados": {k: acf([z * z for z in conj], k) for k in (1, 5, 20, 60)},
        "se_anual_iid": se_iid,
        "se_anual_newey_west": {L: hac_se(conj, L) * 365 for L in (7, 20, 60, 120)},
        "bootstrap_por_bloque": {L: {"se_anual": se_bootstrap(r), "ic90": r["intervalo_anual"], "p": r["p_mayor_que_cero"]}
                                 for L, r in bloques.items()},
        "observaciones_efectivas_bloque20": n * (se_iid / se_bootstrap(bloques[20])) ** 2,
        "observaciones_efectivas_bloque120": n * (se_iid / se_bootstrap(bloques[120])) ** 2}
    rho = st.correlation(exc["BTC"], exc["ETH"])
    rho20 = st.correlation(*[[sum(s[i:i + 20]) for i in range(0, n - 19, 20)] for s in (exc["BTC"], exc["ETH"])])
    var_media = st.variance(conj)
    out["correlacion_btc_eth"] = {"diaria": rho, "sumas_de_20_dias": rho20,
                                  "activos_efectivos": (st.variance(exc["BTC"]) + st.variance(exc["ETH"])) / 2 / var_media}
    for k, v in velas.items():  # episodios: tramos con la misma exposición objetivo dentro de la ventana
        o = tsmom([x.c for x in v])
        w = [o[i - 1] for i, x in enumerate(v) if DESDE <= x.dia < HASTA]
        cambios = sum(a != c for a, c in itertools.pairwise(w))
        dentro = [z > 0.5 for z in w]
        out.setdefault("episodios", {})[k] = {"cambios_de_objetivo": cambios, "dias_medios_por_tramo": len(w) / (cambios + 1),
                                               "entradas_salidas_mitad": sum(a != c for a, c in itertools.pairwise(dentro))}

    # 3. desarrollo frente a fuera de muestra
    dev = {}
    for k, v in velas.items():
        dev[k] = P._exceso(v, DEV, DESDE, Costes())[0]
    dev["conjunto"] = [(a + c) / 2 for a, c in zip(dev["BTC"], dev["ETH"], strict=True)]
    oos = {"BTC": exc["BTC"], "ETH": exc["ETH"], "conjunto": conj}
    out["desarrollo_vs_fuera"] = {}
    for k in ("BTC", "ETH", "conjunto"):
        bd, bo = bootstrap_media(dev[k], **KW), bootstrap_media(oos[k], **KW)
        dif, se = bd["media_anual"] - bo["media_anual"], math.hypot(se_bootstrap(bd), se_bootstrap(bo))
        out["desarrollo_vs_fuera"][k] = {"desarrollo": bd["media_anual"], "fuera": bo["media_anual"], "diferencia": dif,
                                         "se_diferencia": se, "z": dif / se, "p_dos_colas": 2 * (1 - N.cdf(abs(dif / se)))}

    # 4. estrés con su incertidumbre
    conj2 = [(a + c) / 2 for a, c in zip(x2["BTC"], x2["ETH"], strict=True)]
    from fuera_de_muestra_T import exceso as exceso_retraso  # misma fórmula congelada con retraso
    ret = [(a + c) / 2 for a, c in zip(*(exceso_retraso(v, DESDE, HASTA, retraso=1) for v in velas.values()), strict=True)]
    out["estres"] = {n_: {"exceso_anual": r["media_anual"], "ic90": r["intervalo_anual"], "p": r["p_mayor_que_cero"]}
                     for n_, r in (("costes_x2", bootstrap_media(conj2, **KW)), ("retraso_1_dia", bootstrap_media(ret, **KW)))}

    # 5. buy and hold: exposición media frente a timing (CAGR, media aritmética y 2022)
    out["buy_and_hold"] = {}
    for k in SIM:
        i = info[k]
        t, e, h = i["T"], i["estatica"], i["buy_and_hold"]
        v = velas[k]
        o = tsmom([x.c for x in v])
        w22 = [o[j - 1] for j, x in enumerate(v) if "2022-01-01" <= x.dia < "2023-01-01"]
        out["buy_and_hold"][k] = {
            "cagr": {"T": t["cagr"], "estatica": e["cagr"], "buy_and_hold": h["cagr"]},
            "cagr_por_exposicion_media (estatica - B&H)": e["cagr"] - h["cagr"],
            "cagr_por_timing (T - estatica)": t["cagr"] - e["cagr"],
            "anio_2022": {"T": t["por_ano"]["2022"], "estatica": e["por_ano"]["2022"], "buy_and_hold": h["por_ano"]["2022"],
                          "exposicion_objetivo_media_T_2022": st.fmean(w22), "exposicion_media_estatica": i["exposicion_media"]},
            "caida_maxima": {"T": t["caida_maxima"], "estatica": e["caida_maxima"], "buy_and_hold": h["caida_maxima"]},
            "sharpe": {"T": t["sharpe"], "estatica": e["sharpe"], "buy_and_hold": h["sharpe"]}}

    # 6. potencia: 52 años y ≤ 9 % con distintos supuestos
    pot = json.loads((RAIZ / "papel" / "potencia.json").read_text(encoding="utf-8"))["BTC+ETH (media)"]
    sig = {"desarrollo (potencia.json)": pot["error_1_ano"],
           "fuera de muestra, bloque 20": se_bootstrap(bloques[20]) * math.sqrt(n / 365),
           "fuera de muestra, bloque 120": se_bootstrap(bloques[120]) * math.sqrt(n / 365)}
    efectos = {"punto fuera de muestra": b["media_anual"], "mitad": b["media_anual"] / 2,
               "desarrollo": pot["exceso_anual_desarrollo"], "IC90 superior fuera": b["intervalo_anual"][1]}
    out["potencia_normal"] = {s: {"sigma_1_ano": sg, **{e: {
        "anos_para_P95_en_promedio": (N.inv_cdf(0.95) * sg / mu) ** 2,
        "anos_para_P95_con_80pct_de_potencia": ((N.inv_cdf(0.95) + N.inv_cdf(0.80)) * sg / mu) ** 2,
        "prob_P95_a_24_meses": 1 - N.cdf(N.inv_cdf(0.95) - mu / (sg / math.sqrt(2))),
        "prob_detener_a_12_meses": N.cdf(N.inv_cdf(0.10) - mu / sg)} for e, mu in efectos.items()}} for s, sg in sig.items()}
    out["potencia_montecarlo_regla_completa_24_meses"] = {
        e: prob_papel(exc["BTC"], exc["ETH"], x2["BTC"], x2["ETH"], mu, 731) for e, mu in
        (("cero", 0.0), ("punto fuera de muestra", b["media_anual"]), ("desarrollo", pot["exceso_anual_desarrollo"]))}
    out["potencia_montecarlo_12_meses"] = {
        e: prob_papel(exc["BTC"], exc["ETH"], x2["BTC"], x2["ETH"], mu, 366)["detener_p_menor_0_10"] for e, mu in
        (("cero", 0.0), ("punto fuera de muestra", b["media_anual"]))}

    # 7. potencia del diseño multimercado propuesto (SUPUESTOS explícitos; no usa datos nuevos)
    norm = {k: {"exceso_a_10pct_vol": fm["principal"][k]["exceso_anual"] / fm["principal"][k]["buy_and_hold"]["vol_anual"]
                * 0.10, "sigma_1_ano_a_10pct_vol": se_bootstrap(bootstrap_media(exc[k], **KW)) * math.sqrt(n / 365)
                / fm["principal"][k]["buy_and_hold"]["vol_anual"] * 0.10} for k in SIM}
    sigma = st.fmean(x["sigma_1_ano_a_10pct_vol"] for x in norm.values())
    efecto_cripto = st.fmean(x["exceso_a_10pct_vol"] for x in norm.values())
    anos, z95 = 13.75, N.inv_cdf(0.95)  # 2013-01-01 → 2026-09-30
    escenarios = {}
    for rw, ra in ((0.3, 0.05), (0.5, 0.10), (0.7, 0.20)):  # correlación del exceso dentro y entre clases (3 × 4 activos)
        neff = 144 / (12 + 36 * rw + 96 * ra)
        se = sigma / math.sqrt(neff * anos)
        escenarios[f"rho_dentro={rw}, rho_entre={ra}"] = {
            "activos_efectivos": neff, "se_anual": se,
            **{f"P(respaldada) si efecto={mu:.2%}": 1 - N.cdf(z95 - mu / se) for mu in (0.005, 0.010, efecto_cripto)},
            "P(sin ventaja) si efecto=0": N.cdf((0.005 - z95 * se) / se)}
    out["diseno_multimercado_potencia"] = {"cripto_normalizado_fuera_de_muestra": norm, "sigma_supuesta_1_ano": sigma,
                                           "efecto_cripto_normalizado": efecto_cripto, "anos": anos,
                                           "escenarios": escenarios}

    (AQUI / "revision_fuera_de_muestra_T.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float)
                                                           + "\n", encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
