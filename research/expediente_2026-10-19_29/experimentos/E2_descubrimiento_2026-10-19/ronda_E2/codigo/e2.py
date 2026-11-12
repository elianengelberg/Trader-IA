"""Ronda E2 (E2-A, E2-B, E2-C) según prerregistro/PRERREGISTRO_E2.md. Una sola ejecución.

Uso:
  python -B e2.py prueba_cw <salida.json>     # verificación del estimador de Clark–West con datos SINTÉTICOS
  python -B e2.py ejecutar  <dir_resultados>  # la ronda con datos reales

Reutiliza, sin modificarlo, el código congelado de T: tendencia.datos.leer, tendencia.senal.tsmom,
tendencia.backtest.simular/Costes y tendencia.metricas (PYTHONPATH=research/tendencia_btc/src).
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import io
import json
import math
import random
import statistics as st
import sys
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from tendencia.backtest import Costes, simular
from tendencia.datos import leer
from tendencia.metricas import calcular, rendimientos
from tendencia.senal import tsmom

RAIZ = Path("/home/user/Trader-IA/research")
SPOT = {"BTC": RAIZ / "tendencia_btc/datos/BTCUSDT", "ETH": RAIZ / "tendencia_btc/datos/ETHUSDT"}
FUNDING = {"BTC": RAIZ / "hcarry_next/datos/binance_vision/futures/um/monthly/fundingRate/BTCUSDT",
           "ETH": RAIZ / "hcarry_next/datos/otros_simbolos/ETHUSDT/futures/um/monthly/fundingRate/ETHUSDT"}
PRIMA_BTC = RAIZ / "hcarry_next/datos/binance_vision/futures/um/monthly/premiumIndexKlines/BTCUSDT/1h"
WIKI = Path(__file__).resolve().parents[1] / "datos/wikipedia_bitcoin_pageviews.json"
DIA_MS = 86_400_000
SEMILLA = 20261019
ENTRENA_A = "2020-01-08"
PRONOSTICO_A = "2021-01-01"
FIN = "2026-06-01"          # exclusivo (último día de datos: 2026-05-31)
VENTANA_B = ("2020-07-06", "2026-06-01")
VARIABLES_A = ["VOL30", "VOLUMEN_Z30", "FUNDING7", "PRIMA7", "DD90"]
HORIZONTES_A = [7, 28]


def _ms_dia(d: str) -> int:
    return int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() * 1000)


# ------------------------------------------------------------------------------------------------ datos
def zips_verificados(directorio: Path) -> tuple[list[tuple[str, bytes]], list[dict]]:
    out, reg = [], []
    for z in sorted(directorio.glob("*.zip")):
        b = z.read_bytes()
        h = hashlib.sha256(b).hexdigest()
        oficial = z.with_name(z.name + ".CHECKSUM").read_text().split()[0]
        if h != oficial:
            raise SystemExit(f"{z} no coincide con su .CHECKSUM: se detiene")
        with zipfile.ZipFile(io.BytesIO(b)) as f:
            out.append((z.name, f.read(f.namelist()[0]).decode()))
        reg.append({"archivo": z.name, "sha256": h})
    return out, reg


def leer_funding(directorio: Path) -> tuple[list[tuple[int, float]], dict]:
    archivos, reg = zips_verificados(directorio)
    filas = {}
    for _, texto in archivos:
        for r in csv.reader(io.StringIO(texto)):
            if not r or not r[0].strip().isdigit():
                continue
            filas[int(r[0])] = float(r[2])
    serie = sorted(filas.items())
    return serie, {"archivos": reg, "liquidaciones": len(serie),
                   "primera": datetime.fromtimestamp(serie[0][0] / 1000, timezone.utc).isoformat(),
                   "ultima": datetime.fromtimestamp(serie[-1][0] / 1000, timezone.utc).isoformat()}


def leer_prima(directorio: Path) -> tuple[list[tuple[int, float]], dict]:
    archivos, reg = zips_verificados(directorio)
    filas = {}
    for _, texto in archivos:
        for r in csv.reader(io.StringIO(texto)):
            if not r or not r[0].strip().isdigit():
                continue
            t = int(r[0])
            t = t // 1000 if t > 10**14 else t
            filas[t] = float(r[4])  # cierre del índice de prima de esa hora
    serie = sorted(filas.items())
    esperadas = (serie[-1][0] - serie[0][0]) // 3_600_000 + 1
    return serie, {"archivos": reg, "horas": len(serie), "esperadas": esperadas, "faltantes": esperadas - len(serie)}


def leer_wiki(ruta: Path) -> tuple[dict[str, int], dict]:
    b = ruta.read_bytes()
    items = json.loads(b)["items"]
    vistas = {}
    for it in items:
        d = f"{it['timestamp'][:4]}-{it['timestamp'][4:6]}-{it['timestamp'][6:8]}"
        if it["article"] != "Bitcoin" or it["agent"] != "user" or it["access"] != "all-access":
            raise SystemExit("respuesta de Wikipedia con parámetros inesperados: se detiene")
        vistas[d] = int(it["views"])
    dias = sorted(vistas)
    d0, d1 = date.fromisoformat(dias[0]), date.fromisoformat(dias[-1])
    esperados = (d1 - d0).days + 1
    return vistas, {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "primero": dias[0], "ultimo": dias[-1],
                    "dias": len(dias), "esperados": esperados, "faltantes": esperados - len(dias),
                    "no_positivos": sum(1 for v in vistas.values() if v <= 0)}


def cargar_todo(corte: str | None = None):
    """Todos los datos; con ``corte`` (AAAA-MM-DD) se descarta todo lo posterior al cierre de ese día (prueba de
    invariancia frente al futuro)."""
    precios, calidad = {}, {}
    for a, d in SPOT.items():
        v, inf = leer(d)
        v = [x for x in v if x.dia < FIN]
        if corte:
            v = [x for x in v if x.dia <= corte]
        precios[a] = v
        calidad[f"spot_{a}"] = {"dias": len(v), "primero": v[0].dia, "ultimo": v[-1].dia,
                                "informe": {k: (len(x) if isinstance(x, list) else x) for k, x in inf.items()}}
    funding = {}
    for a, d in FUNDING.items():
        s, inf = leer_funding(d)
        if corte:
            s = [x for x in s if x[0] < _ms_dia(corte) + DIA_MS]
        funding[a] = s
        calidad[f"funding_{a}"] = {k: v for k, v in inf.items() if k != "archivos"} | {"archivos": len(inf["archivos"])}
    prima, inf = leer_prima(PRIMA_BTC)
    if corte:
        prima = [x for x in prima if x[0] + 3_600_000 <= _ms_dia(corte) + DIA_MS]
    calidad["prima_BTC"] = {k: v for k, v in inf.items() if k != "archivos"} | {"archivos": len(inf["archivos"])}
    vistas, inf = leer_wiki(WIKI)
    if corte:
        vistas = {d: x for d, x in vistas.items() if d <= corte}
    calidad["wikipedia"] = inf
    return precios, funding, prima, vistas, calidad


# --------------------------------------------------------------------------------------------- variables
def variables(velas, funding_serie, prima_serie=None) -> dict[str, list[float | None]]:
    n = len(velas)
    c = [v.c for v in velas]
    lv = [math.log(v.vol_quote) if v.vol_quote > 0 else None for v in velas]
    r = [None] + [math.log(c[i] / c[i - 1]) for i in range(1, n)]
    mom = tsmom(c)
    ts_f = [t for t, _ in funding_serie]
    out = {"MOM": mom, "VOL30": [None] * n, "VOLUMEN_Z30": [None] * n, "FUNDING7": [None] * n,
           "PRIMA7": [None] * n, "DD90": [None] * n}
    if prima_serie is not None:
        ts_p = [t for t, _ in prima_serie]
    for i, v in enumerate(velas):
        if i >= 30:
            out["VOL30"][i] = st.stdev(r[i - 29: i + 1]) * math.sqrt(365)
            prev = lv[i - 30: i]
            if all(x is not None for x in prev) and lv[i] is not None and st.stdev(prev) > 0:
                out["VOLUMEN_Z30"][i] = (lv[i] - st.fmean(prev)) / st.stdev(prev)
        if i >= 89:
            out["DD90"][i] = c[i] / max(c[i - 89: i + 1]) - 1
        d0 = _ms_dia(v.dia)
        a, b = bisect.bisect_left(ts_f, d0 - 6 * DIA_MS), bisect.bisect_left(ts_f, d0 + DIA_MS)
        if ts_f and ts_f[0] <= d0 - 6 * DIA_MS and b > a and b <= len(ts_f) and ts_f[b - 1] >= d0:
            out["FUNDING7"][i] = st.fmean(x for _, x in funding_serie[a:b])
        if prima_serie is not None:
            fin = d0 + DIA_MS                       # cierre del día: incluye la hora que cierra a las 00:00 de d+1
            pa, pb = bisect.bisect_left(ts_p, fin - 168 * 3_600_000), bisect.bisect_left(ts_p, fin)
            if pb - pa >= 160 and ts_p[0] <= fin - 168 * 3_600_000:  # tolera algún hueco aislado
                out["PRIMA7"][i] = st.fmean(x for _, x in prima_serie[pa:pb])
    return out


# ------------------------------------------------------------------------------------------- estadística
def nw_media(f: np.ndarray, rezagos: int) -> tuple[float, float]:
    f = np.asarray(f, float)
    n = f.size
    m = f.mean()
    u = f - m
    var = u @ u / n
    for l in range(1, rezagos + 1):
        var += 2 * (1 - l / (rezagos + 1)) * (u[l:] @ u[:-l]) / n
    return float(m), float(math.sqrt(max(var, 1e-300) / n))


def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class OLSExpansivo:
    """Acumula X'X y X'y; solo admite filas con objetivo ya realizado (lo comprueba el que llama)."""

    def __init__(self, p: int):
        self.xtx = np.zeros((p, p)); self.xty = np.zeros(p); self.n = 0

    def agregar(self, x, y):
        x = np.asarray(x, float); self.xtx += np.outer(x, x); self.xty += x * y; self.n += 1

    def predecir(self, x):
        b = np.linalg.lstsq(self.xtx, self.xty, rcond=None)[0]
        return float(np.asarray(x, float) @ b)


def clark_west(pares: dict, h: int) -> dict:
    """pares[(fecha, activo)] = (y, yb, ya). Promedia f entre activos por fecha y aplica Newey–West(h)."""
    por_fecha: dict[str, list[float]] = {}
    eb2 = ea2 = 0.0
    for (fe, _a), (y, yb, ya) in sorted(pares.items()):
        eb, ea = y - yb, y - ya
        por_fecha.setdefault(fe, []).append(eb * eb - (ea * ea - (yb - ya) ** 2))
        eb2 += eb * eb; ea2 += ea * ea
    f = np.array([st.fmean(v) for _, v in sorted(por_fecha.items())])
    m, se = nw_media(f, h)
    t = m / se if se > 0 else 0.0
    return {"n_pronosticos": len(pares), "n_fechas": int(f.size), "t_cw": t, "p_unilateral": 1 - phi(t),
            "delta_R2_oos": 1 - ea2 / eb2 if eb2 > 0 else None}


def pronosticos(series: dict[str, dict], fechas: dict[str, list[str]], col_x: str | None, base_cols: list[str],
                h: int, ini_entrena: str, ini_pron: str, activos: list[str], min_entrena: int = 0,
                comprobar: list | None = None, requiere: list[str] | None = None) -> dict:
    """Panel con interceptos por activo. series[a][col] = lista alineada a fechas[a]; 'Y' = objetivo a h días."""
    cols = base_cols + ([col_x] if col_x else [])
    req = cols + [r for r in (requiere or []) if r not in cols]
    p = len(activos) + len(cols)
    ols = OLSExpansivo(p)
    idx = {a: {d: i for i, d in enumerate(fechas[a])} for a in activos}
    todas = sorted({d for a in activos for d in fechas[a] if d >= ini_entrena})
    out = {}
    for d in todas:
        # 1) se agregan las filas cuyo objetivo se realizó EXACTAMENTE hoy: s = t − h
        for k, a in enumerate(activos):
            i = idx[a].get(d)
            if i is None or i - h < 0:
                continue
            s = i - h
            if fechas[a][s] < ini_entrena:
                continue
            fila = [series[a][c][s] for c in cols]
            y = series[a]["Y"][s]
            if y is None or any(series[a][c][s] is None for c in req):
                continue
            assert s + h <= i, "mirada al futuro en el entrenamiento"
            if comprobar is not None:
                comprobar.append((fechas[a][s], d, h))
            ols.agregar([1.0 if j == k else 0.0 for j in range(len(activos))] + fila, y)
        # 2) se pronostica en t con lo disponible
        if d < ini_pron or ols.n < max(min_entrena, p + 5):
            continue
        for k, a in enumerate(activos):
            i = idx[a].get(d)
            if i is None:
                continue
            fila = [series[a][c][i] for c in cols]
            if any(series[a][c][i] is None for c in req) or series[a]["Y"][i] is None:
                continue
            out[(d, a)] = (series[a]["Y"][i], ols.predecir([1.0 if j == k else 0.0 for j in range(len(activos))] + fila))
    return out


def objetivo_h(velas, h: int, fin: str = FIN) -> list[float | None]:
    c = [v.c for v in velas]
    return [math.log(c[i + h] / c[i]) if i + h < len(c) and velas[i + h].dia < fin else None for i in range(len(c))]


# ------------------------------------------------------------------------------------------- experimentos
def experimento_A(precios, funding, prima, comprobar=None) -> tuple[dict, dict]:
    series, fechas = {}, {}
    for a in ("BTC", "ETH"):
        series[a] = variables(precios[a], funding[a], prima if a == "BTC" else None)
        fechas[a] = [v.dia for v in precios[a]]
    res, crudos = {}, {}
    for h in HORIZONTES_A:
        for a in ("BTC", "ETH"):
            series[a]["Y"] = objetivo_h(precios[a], h)
        for x in VARIABLES_A:
            act = ["BTC"] if x == "PRIMA7" else ["BTC", "ETH"]
            aug = pronosticos(series, fechas, x, ["MOM"], h, ENTRENA_A, PRONOSTICO_A, act, comprobar=comprobar)
            base = pronosticos(series, fechas, None, ["MOM"], h, ENTRENA_A, PRONOSTICO_A, act, requiere=[x])
            comunes = sorted(set(aug) & set(base))
            pares = {k: (aug[k][0], base[k][1], aug[k][1]) for k in comunes}
            r = clark_west(pares, h)
            r["activos"] = act
            r["periodo_pronostico"] = [comunes[0][0], comunes[-1][0]] if comunes else None
            res[f"{x}|h{h}"] = r
            crudos[f"{x}|h{h}"] = {f"{k[0]}|{k[1]}": v for k, v in pares.items()}
    ps = {k: v["p_unilateral"] for k, v in res.items()}
    orden = sorted(ps, key=ps.get)
    sigue = True
    for j, k in enumerate(orden):
        umbral = 0.05 / (len(orden) - j)
        sigue = sigue and ps[k] <= umbral
        res[k]["holm_interno"] = {"umbral": umbral, "pasa": sigue}
    p_fam = min(1.0, len(ps) * min(ps.values()))
    return {"pruebas": res, "p_familia_bonferroni": p_fam, "n_pruebas": len(ps)}, crudos


def exposicion_B(velas, funding_serie) -> list[float | None]:
    f7 = variables(velas, funding_serie)["FUNDING7"]
    hist: list[float] = []
    out: list[float | None] = []
    for x in f7:
        if x is None:
            out.append(None)
            continue
        bisect.insort(hist, x)
        if len(hist) < 180:
            out.append(None)
            continue
        n = len(hist)
        p10 = np.percentile(hist, 10)
        p90 = np.percentile(hist, 90)
        out.append(1.0 if x <= p10 else 0.0 if x >= p90 else 0.5)
    return out


def bootstrap_circular(x: list[float], bloque: int, n: int, semilla: int) -> np.ndarray:
    a = np.asarray(x, float); m = a.size
    rng = np.random.default_rng(semilla)
    k = math.ceil(m / bloque)
    medias = np.empty(n)
    for r in range(n):
        ini = rng.integers(0, m, k)
        idx = (ini[:, None] + np.arange(bloque)[None, :]).ravel()[:m] % m
        medias[r] = a[idx].mean()
    return medias


def experimento_B(precios, funding) -> tuple[dict, dict]:
    desde, hasta = VENTANA_B
    out, excesos, excesos_x2 = {"por_activo": {}}, {}, {}
    for a in ("BTC", "ETH"):
        v = precios[a]
        obj = exposicion_B(v, funding[a])
        i0 = next(i for i, x in enumerate(v) if x.dia >= desde)
        if obj[i0 - 1] is None:
            raise SystemExit(f"E2-B {a}: no hay señal el día anterior al inicio de la ventana: se detiene")
        s = simular(v, obj, desde, hasta, costes=Costes())
        s2 = simular(v, obj, desde, hasta, costes=Costes(multiplicador=2.0))
        wbar = st.fmean(s.exposicion)
        e = simular(v, [wbar] * len(v), desde, hasta, costes=Costes(0, 0), banda=0.0)
        bh = simular(v, [1.0] * len(v), desde, hasta)
        x = [p - q for p, q in zip(rendimientos(s), rendimientos(e), strict=True)]
        x2 = [p - q for p, q in zip(rendimientos(s2), rendimientos(e), strict=True)]
        excesos[a], excesos_x2[a] = dict(zip(s.dias, x)), dict(zip(s.dias, x2))
        ventana = [o for o, d in zip(obj, [z.dia for z in v]) if desde <= d < hasta]
        estados = {k: sum(1 for o in ventana if o == k) for k in (0.0, 0.5, 1.0)}
        episodios = {k: sum(1 for j in range(len(ventana)) if ventana[j] == k and (j == 0 or ventana[j - 1] != k)) for k in (0.0, 1.0)}
        med = bootstrap_circular(x, 60, 10_000, SEMILLA)
        out["por_activo"][a] = {"exceso_anual": st.fmean(x) * 365, "P": float((med > 0).mean()),
                                "ic90": [float(np.percentile(med, 5) * 365), float(np.percentile(med, 95) * 365)],
                                "exceso_anual_costes_x2": st.fmean(x2) * 365, "exposicion_media": wbar,
                                "dias_por_estado": {str(k): n for k, n in estados.items()},
                                "episodios": {"cola_baja_largo": episodios[1.0], "cola_alta_efectivo": episodios[0.0]},
                                "regla": {k: calcular(s)[k] for k in ("cagr", "vol_anual", "sharpe", "caida_maxima", "operaciones", "costes_pp_anual", "rotacion_anual")},
                                "estatica": {k: calcular(e)[k] for k in ("cagr", "vol_anual", "sharpe", "caida_maxima")},
                                "buy_and_hold": {k: calcular(bh)[k] for k in ("cagr", "vol_anual", "sharpe", "caida_maxima")}}
    dias = sorted(set(excesos["BTC"]) & set(excesos["ETH"]))
    conj = [(excesos["BTC"][d] + excesos["ETH"][d]) / 2 for d in dias]
    conj2 = [(excesos_x2["BTC"][d] + excesos_x2["ETH"][d]) / 2 for d in dias]
    med = bootstrap_circular(conj, 60, 10_000, SEMILLA)
    out["conjunto"] = {"dias": len(dias), "exceso_anual": st.fmean(conj) * 365, "P": float((med > 0).mean()),
                       "ic90": [float(np.percentile(med, 5) * 365), float(np.percentile(med, 95) * 365)],
                       "exceso_anual_costes_x2": st.fmean(conj2) * 365}
    out["p_B"] = 1 - out["conjunto"]["P"]
    return out, {"exposiciones": {a: exposicion_B(precios[a], funding[a]) for a in ("BTC", "ETH")}}


def experimento_C(precios, vistas, comprobar=None) -> tuple[dict, dict]:
    v = precios["BTC"]
    c = [x.c for x in v]
    fechas = [x.dia for x in v]
    n = len(v)
    M = [math.log(c[i] / c[i - 28]) if i >= 28 else None for i in range(n)]
    A: list[float | None] = []
    for d in fechas:
        t = date.fromisoformat(d)
        rec = [vistas.get((t - timedelta(days=k)).isoformat()) for k in range(1, 8)]
        ant = [vistas.get((t - timedelta(days=k)).isoformat()) for k in range(29, 36)]
        A.append(math.log(st.fmean(rec) / st.fmean(ant)) if all(x is not None and x > 0 for x in rec + ant) else None)
    Y = objetivo_h(v, 7)
    ini = next(fechas[i] for i in range(n) if M[i] is not None and A[i] is not None)
    series = {"BTC": {"M": M, "A": A, "Y": Y}}
    aug = pronosticos(series, {"BTC": fechas}, "A", ["M"], 7, ini, ini, ["BTC"], min_entrena=180, comprobar=comprobar)
    base = pronosticos(series, {"BTC": fechas}, None, ["M"], 7, ini, ini, ["BTC"], min_entrena=180, requiere=["A"])
    comunes = sorted(set(aug) & set(base))
    pares = {k: (aug[k][0], base[k][1], aug[k][1]) for k in comunes}
    r = clark_west(pares, 7)
    posibles = [d for d in fechas if comunes and comunes[0][0] <= d and Y[fechas.index(d)] is not None]
    sin_A = sum(1 for d in posibles if A[fechas.index(d)] is None)
    r.update({"inicio_entrenamiento": ini, "periodo_pronostico": [comunes[0][0], comunes[-1][0]] if comunes else None,
              "dias_de_pronostico_posibles": len(posibles), "dias_sin_variable_por_huecos": sin_A,
              "fraccion_sin_variable": sin_A / len(posibles) if posibles else None, "p_C": r["p_unilateral"]})
    r["inconcluso_por_huecos"] = bool(r["fraccion_sin_variable"] is not None and r["fraccion_sin_variable"] > 0.05)
    return r, {f"{k[0]}|{k[1]}": val for k, val in pares.items()}


# -------------------------------------------------------------------------------------------- verificación
def prueba_cw(salida: str):
    """Tamaño y potencia del estimador con datos SINTÉTICOS (no históricos): y_t = suma de 7 shocks futuros."""
    rng = np.random.default_rng(1)
    def sim(beta):
        n = 2000
        z = rng.normal(0, 0.02, n + 7)
        x = rng.normal(0, 1, n)
        m = rng.normal(0, 1, n)
        y = np.array([z[i + 1: i + 8].sum() for i in range(n)]) + beta * 0.01 * x
        fechas = [(date(2015, 1, 1) + timedelta(days=i)).isoformat() for i in range(n)]
        s = {"S": {"MOM": list(m), "X": list(x), "Y": list(y[:-7]) + [None] * 7}}
        aug = pronosticos(s, {"S": fechas}, "X", ["MOM"], 7, fechas[0], fechas[400], ["S"])
        base = pronosticos(s, {"S": fechas}, None, ["MOM"], 7, fechas[0], fechas[400], ["S"])
        k = sorted(set(aug) & set(base))
        return clark_west({q: (aug[q][0], base[q][1], aug[q][1]) for q in k}, 7)["p_unilateral"]
    nulo = [sim(0.0) for _ in range(300)]
    alt = [sim(1.0) for _ in range(100)]
    out = {"datos": "SINTÉTICOS", "rechazo_al_5pct_bajo_nulo": sum(p <= 0.05 for p in nulo) / len(nulo),
           "potencia_al_5pct_alternativa": sum(p <= 0.05 for p in alt) / len(alt),
           "nota": "CW es algo conservador en muestras finitas (Clark y West, 2007); se espera rechazo ≲ 5 % bajo el nulo"}
    json.dump(out, open(salida, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(out, ensure_ascii=False))


def ejecutar(dir_res: str):
    d = Path(dir_res)
    if (d / "resultado_E2.json").exists():
        sys.exit("ya existe resultado_E2.json: una sola ejecución")
    d.mkdir(parents=True, exist_ok=True)
    precios, funding, prima, vistas, calidad = cargar_todo()
    # ---- validez 2: huecos ≤ 1 % por serie en su ventana
    val = {"calidad": calidad, "problemas": []}
    for a in ("BTC", "ETH"):
        inf = calidad[f"spot_{a}"]["informe"]
        if inf.get("ausentes", 0) and inf["ausentes"] / calidad[f"spot_{a}"]["dias"] > 0.01:
            val["problemas"].append(f"spot {a}: más de 1 % de días ausentes")
    p = calidad["prima_BTC"]
    if p["faltantes"] / p["esperadas"] > 0.01:
        val["problemas"].append("prima BTC: más de 1 % de horas faltantes")
    w = calidad["wikipedia"]
    if w["faltantes"] / w["esperados"] > 0.01 or w["no_positivos"]:
        val["problemas"].append("wikipedia: más de 1 % de días faltantes o valores no positivos")
    for a in ("BTC", "ETH"):
        f = funding[a]
        esperadas = (f[-1][0] - f[0][0]) / (8 * 3_600_000) + 1
        val["calidad"][f"funding_{a}"]["esperadas_8h"] = round(esperadas)
        if len(f) / esperadas < 0.99:
            val["problemas"].append(f"funding {a}: más de 1 % de liquidaciones faltantes")
    # ---- experimentos (con registro de pares entrenamiento/pronóstico para la validez 3)
    reg_a, reg_c = [], []
    A, crudos_A = experimento_A(precios, funding, prima, comprobar=reg_a)
    B, crudos_B = experimento_B(precios, funding)
    C, crudos_C = experimento_C(precios, vistas, comprobar=reg_c)
    val["entrenamiento_sin_futuro"] = all((date.fromisoformat(t) - date.fromisoformat(s_)).days >= h for s_, t, h in reg_a + reg_c)
    val["filas_de_entrenamiento_comprobadas"] = len(reg_a) + len(reg_c)
    # ---- validez 4: invariancia frente al futuro en 5 cortes
    rnd = random.Random(SEMILLA)
    dias_pron = sorted({k.split("|")[0] for k in crudos_A["FUNDING7|h7"]})
    cortes = sorted(rnd.sample(dias_pron[30:-30], 5))
    inv = []
    for corte in cortes:
        p2, f2, pr2, v2, _ = cargar_todo(corte)
        A2, cA2 = experimento_A(p2, f2, pr2)
        _, cB2 = experimento_B_parcial(p2, f2)
        C2, cC2 = experimento_C(p2, v2)
        okA = all(abs(cA2[k][f][1] - crudos_A[k][f][1]) < 1e-12 and abs(cA2[k][f][2] - crudos_A[k][f][2]) < 1e-12
                  for k in cA2 for f in cA2[k] if f.split("|")[0] <= corte)
        okB = all(cB2[a][i] == crudos_B["exposiciones"][a][i] for a in ("BTC", "ETH") for i in range(len(cB2[a])))
        okC = all(abs(cC2[f][1] - crudos_C[f][1]) < 1e-12 and abs(cC2[f][2] - crudos_C[f][2]) < 1e-12
                  for f in cC2 if f.split("|")[0] <= corte)
        okV = True
        for a in ("BTC", "ETH"):
            vf = variables(precios[a], funding[a], prima if a == "BTC" else None)
            vt = variables(p2[a], f2[a], pr2 if a == "BTC" else None)
            for col in vt:
                okV = okV and all((x is None and y is None) or (x is not None and y is not None and abs(x - y) < 1e-12)
                                  for x, y in zip(vt[col], vf[col][: len(vt[col])]))
        okVC = attention_igual(precios, vistas, p2, v2)
        inv.append({"corte": corte, "variables_A_B_hasta_el_corte": okV, "atencion_C_hasta_el_corte": okVC,
                    "pronosticos_A": okA, "exposiciones_B": okB, "pronosticos_C": okC})
    val["invariancia_frente_al_futuro"] = inv
    val["todo_ok"] = (not val["problemas"] and val["entrenamiento_sin_futuro"] and all(all(v for k, v in x.items() if k != "corte") for x in inv))
    (d / "validez.json").write_text(json.dumps(val, indent=1, ensure_ascii=False, default=str))
    print("VALIDEZ:", json.dumps({k: v for k, v in val.items() if k != "calidad"}, ensure_ascii=False))
    if not val["todo_ok"]:
        sys.exit("la validez falla: se detiene ANTES de interpretar")
    # ---- Holm entre las tres hipótesis confirmatorias
    pC = 1.0 if C["inconcluso_por_huecos"] else C["p_C"]
    ps = {"E2-A": A["p_familia_bonferroni"], "E2-B": B["p_B"], "E2-C": pC}
    orden = sorted(ps, key=ps.get)
    holm, sigue = {}, True
    for j, k in enumerate(orden):
        u = 0.05 / (3 - j)
        sigue = sigue and ps[k] <= u
        holm[k] = {"p": ps[k], "umbral": u, "rechaza": sigue}
    # ---- clasificación prerregistrada
    pr = A["pruebas"]
    if holm["E2-A"]["rechaza"]:
        cA = "FAVORABLE (información incremental)"
    elif all((v["delta_R2_oos"] or 0) <= 0 and v["p_unilateral"] >= 0.10 for v in pr.values()):
        cA = "EN CONTRA (sin información incremental detectable)"
    else:
        cA = "INSUFICIENTE"
    cj = B["conjunto"]
    if holm["E2-B"]["rechaza"] and cj["exceso_anual_costes_x2"] > 0 and all(B["por_activo"][a]["exceso_anual"] > 0 for a in ("BTC", "ETH")):
        cB = "FAVORABLE"
    elif cj["ic90"][1] < 0.02:
        cB = "EN CONTRA (sin ventaja relevante: límite superior del IC90 < +2 %/año)"
    else:
        cB = "INSUFICIENTE" + (" (estimación puntual negativa)" if cj["exceso_anual"] < 0 else "")
    if C["inconcluso_por_huecos"]:
        cC = "INCONCLUSO (huecos en los datos)"
    elif holm["E2-C"]["rechaza"] and (C["delta_R2_oos"] or 0) > 0:
        cC = "FAVORABLE (información incremental)"
    elif (C["delta_R2_oos"] or 0) <= 0 and C["p_C"] >= 0.10:
        cC = "EN CONTRA (sin información incremental detectable)"
    else:
        cC = "INSUFICIENTE"
    res = {"E2-A": A, "E2-B": B, "E2-C": C, "holm_entre_experimentos": holm,
           "clasificacion": {"E2-A": cA, "E2-B": cB, "E2-C": cC},
           "meta": {"ejecutado_utc": datetime.now(timezone.utc).isoformat(), "semilla": SEMILLA}}
    (d / "resultado_E2.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
    (d / "pronosticos_y_exposiciones.json").write_text(json.dumps({"A": crudos_A, "B": crudos_B, "C": crudos_C}, default=str))
    print(json.dumps({"clasificacion": res["clasificacion"], "holm": holm}, ensure_ascii=False, indent=1))


def atencion(velas, vistas):
    out = []
    for x in velas:
        t = date.fromisoformat(x.dia)
        rec = [vistas.get((t - timedelta(days=k)).isoformat()) for k in range(1, 8)]
        ant = [vistas.get((t - timedelta(days=k)).isoformat()) for k in range(29, 36)]
        out.append(math.log(st.fmean(rec) / st.fmean(ant)) if all(v is not None and v > 0 for v in rec + ant) else None)
    return out


def attention_igual(precios, vistas, p2, v2):
    full, trunc = atencion(precios["BTC"], vistas), atencion(p2["BTC"], v2)
    return all((x is None and y is None) or (x is not None and y is not None and abs(x - y) < 1e-12) for x, y in zip(trunc, full))


def experimento_B_parcial(precios, funding):
    return None, {a: exposicion_B(precios[a], funding[a]) for a in ("BTC", "ETH")}


if __name__ == "__main__":
    if sys.argv[1] == "prueba_cw":
        prueba_cw(sys.argv[2])
    elif sys.argv[1] == "ejecutar":
        ejecutar(sys.argv[2])
    else:
        sys.exit(__doc__)
