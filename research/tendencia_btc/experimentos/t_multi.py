"""T-MULTI (PRERREGISTRO_T_MULTI.md): la regla T congelada, sin cambios, en 12 ETF de renta variable, bonos y materias
primas, sesiones del [2013-01-02, 2026-10-01). Histórico con procedencia limitada; no es prospectivo y no toca el
experimento en papel ni la regla (src/ 73b22f3e…).

Uso (PYTHONPATH=src:../hcarry_next/src):  t_multi.py autoprueba | descargar | validar | evaluar
Cada paso exige el anterior; ``descargar`` no vuelve a bajar si ya existe el manifiesto y ``evaluar`` se niega a
correr si el resultado ya existe (una sola ejecución)."""

from __future__ import annotations

import bisect
import collections
import datetime as dt
import hashlib
import json
import math
import statistics as st
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from statistics import NormalDist

from tendencia import papel as P
from tendencia.backtest import Costes, Resultado, simular
from tendencia.datos import Vela, leer
from tendencia.estadistica import bootstrap_media
from tendencia.metricas import caida, rendimientos
from tendencia.senal import tsmom

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
PRERREGISTRO = RAIZ / "PRERREGISTRO_T_MULTI.md"
DATOS = RAIZ / "datos_multi"
RESULTADO = AQUI / "t_multi.json"
CODIGO = "73b22f3e3a8f21513d5533fb11a7553becae30b87c8736fb6880bccc36c11d2b"
CLASES = {"renta_variable": ["SPY", "IWM", "EFA", "EEM"], "bonos": ["SHY", "IEF", "TLT", "LQD"],
          "materias_primas": ["GLD", "SLV", "USO", "DBC"]}
TODOS = [t for ts in CLASES.values() for t in ts]
DATOS_DESDE, DATOS_HASTA = "2011-01-03", "2026-09-30"  # inclusive
EVAL_DESDE, EVAL_HASTA = "2013-01-02", "2026-10-01"  # [desde, hasta)
HORIZONTES = (30, 90, 180)  # días corridos: el ensamble de 1, 3 y 6 meses de T
COSTES = Costes(comision_bps=0.0, slippage_bps=5.0)
VOL_OBJETIVO, VOL_SESIONES, SESIONES = 0.10, 252, 252
BLOQUE, REMUESTREOS, SEMILLA, NW = 60, 5000, 20261017, 60
DELTA, UMBRAL_P = 0.005, 0.95
AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
Z = NormalDist()


# ---------------- regla: adaptador de horizontes en días corridos ----------------
def senal_calendario(dias: list[str], cierres: list[float], horizontes: tuple[int, ...] = HORIZONTES
                     ) -> list[float | None]:
    """Fracción de h ∈ horizontes con cierre_d > cierre de la última sesión ≤ fecha(d) − h; None sin historia. Con días
    consecutivos es exactamente ``tendencia.senal.tsmom`` (misma comparación)."""
    fechas = [dt.date.fromisoformat(d) for d in dias]
    out: list[float | None] = []
    for k, f in enumerate(fechas):
        votos = []
        for h in horizontes:
            j = bisect.bisect_right(fechas, f - dt.timedelta(days=h)) - 1
            if j < 0:
                break
            votos.append(cierres[k] / cierres[j] > 1)
        out.append(sum(votos) / len(horizontes) if len(votos) == len(horizontes) else None)
    return out


def exceso(v: list[Vela], objetivo: list[float | None], costes: Costes = COSTES, retraso: int = 0,
           desde: str = EVAL_DESDE, hasta: str = EVAL_HASTA) -> tuple[list[float], dict[str, Resultado]]:
    """La fórmula de ``tendencia.papel._exceso`` con el objetivo dado: T frente a la estática con su misma exposición
    media (rebalanceo diario sin costes); también buy and hold con los mismos costes."""
    s = simular(v, objetivo, desde, hasta, costes=costes, retraso=retraso)
    wbar = st.fmean(s.exposicion)
    e = simular(v, [wbar] * len(v), desde, hasta, costes=Costes(0, 0), banda=0.0)
    bh = simular(v, [1.0] * len(v), desde, hasta, costes=costes)
    return [a - b for a, b in zip(rendimientos(s), rendimientos(e), strict=True)], {"T": s, "estatica": e,
                                                                                    "buy_and_hold": bh}


def autoprueba() -> None:
    if P.huella_codigo() != CODIGO:
        sys.exit("código de src/ distinto del congelado")
    for s in ("BTCUSDT", "ETHUSDT"):
        v, _ = leer(RAIZ / "datos" / s)
        dias, c = [x.dia for x in v], [x.c for x in v]
        if senal_calendario(dias, c) != tsmom(c):
            sys.exit(f"{s}: el adaptador no reproduce tsmom")
        if exceso(v, tsmom(c), Costes(), 0, "2018-02-14", "2022-01-01")[0] != P._exceso(v, "2018-02-14", "2022-01-01",
                                                                                         Costes())[0]:
            sys.exit(f"{s}: la métrica no reproduce _exceso")
    print("autoprueba: el adaptador reproduce tsmom y la métrica reproduce _exceso exactamente (BTCUSDT, ETHUSDT)")


# ---------------- descarga ----------------
def _ts(dia: str) -> int:
    return int(dt.datetime.fromisoformat(dia).replace(tzinfo=dt.UTC).timestamp())


def urls(t: str) -> dict[str, list[str]]:
    q = (f"/v8/finance/chart/{t}?period1={_ts('2010-12-01')}&period2={_ts('2026-10-02')}&interval=1d"
         "&events=div%7Csplit%7CcapitalGains&includeAdjustedClose=true")
    return {"yahoo": [f"https://query1.finance.yahoo.com{q}", f"https://query2.finance.yahoo.com{q}"],
            "nasdaq_historico": [(f"https://api.nasdaq.com/api/quote/{t}/historical?assetclass=etf"
                                  f"&fromdate={DATOS_DESDE}&todate={DATOS_HASTA}&limit=9999")],
            "nasdaq_dividendos": [f"https://api.nasdaq.com/api/quote/{t}/dividends?assetclass=etf"]}


def _get(url: str) -> dict:
    """GET con 4 intentos (esperas 5, 20 y 60 s) ante red, 429 o 5xx."""
    error = None
    for espera in (0, 5, 20, 60):
        time.sleep(espera)
        req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json, text/plain, */*"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:  # respeta HTTPS_PROXY
                return {"estado": r.status, "fecha_servidor": r.headers.get("Date"), "cuerpo": r.read()}
        except urllib.error.HTTPError as e:
            error = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            error = repr(e)
    return {"estado": None, "error": error, "cuerpo": b""}


def descargar(datos: Path = DATOS, get=_get) -> dict:  # type: ignore[no-untyped-def]
    man_p = datos / "MANIFIESTO.json"
    if man_p.exists():
        sys.exit(f"{man_p} ya existe: los datos se descargan una sola vez")
    entradas = []
    for t in TODOS:
        for fuente, lista in urls(t).items():
            r = {"estado": None, "error": "sin intentos", "cuerpo": b""}
            for u in lista:
                r = get(u)
                if r["estado"] == 200 and r["cuerpo"]:
                    break
            destino = datos / fuente.split("_")[0] / f"{t}{'_' + fuente.split('_')[1] if '_' in fuente else ''}.json"
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(r["cuerpo"])
            entradas.append({"activo": t, "fuente": fuente, "url": u, "estado": r["estado"], "error": r.get("error"),
                             "fecha_servidor": r.get("fecha_servidor"),
                             "descargado_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                             "archivo": destino.relative_to(datos).as_posix(),
                             "sha256": hashlib.sha256(r["cuerpo"]).hexdigest(), "bytes": len(r["cuerpo"])})
            time.sleep(2 if get is _get else 0)
    man = {"prerregistro_sha256": _sha(PRERREGISTRO), "script_sha256": _sha(Path(__file__)), "entradas": entradas}
    man_p.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    fallos = [e for e in entradas if e["fuente"] == "yahoo" and e["estado"] != 200]
    print(f"descarga: {len(entradas)} respuestas; Yahoo sin datos: {[e['activo'] for e in fallos]}")
    return man


# ---------------- lectura ----------------
def _dia_utc(t: float) -> str:
    return dt.datetime.fromtimestamp(int(t), dt.UTC).date().isoformat()


def leer_yahoo(cuerpo: bytes) -> tuple[dict[str, tuple], dict[str, float], dict[str, float], int]:
    """(filas día → (o, h, l, c, adjclose, volumen)), distribuciones (dividendos + ganancias de capital), splits,
    fechas repetidas."""
    ch = json.loads(cuerpo)["chart"]
    if ch.get("error") or not ch.get("result"):
        raise ValueError(f"Yahoo: {ch.get('error')}")
    r = ch["result"][0]
    q = r["indicators"]["quote"][0]
    adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    filas: dict[str, tuple] = {}
    repetidas = 0
    for i, t in enumerate(r.get("timestamp") or []):
        dia = _dia_utc(t)
        repetidas += dia in filas
        filas[dia] = tuple(None if x is None or i >= len(x) else x[i]
                           for x in (q.get("open"), q.get("high"), q.get("low"), q.get("close"), adj, q.get("volume")))
    ev = r.get("events") or {}
    dist: dict[str, float] = collections.defaultdict(float)
    for clave in ("dividends", "capitalGains"):
        for e in (ev.get(clave) or {}).values():
            if float(e["amount"]) != 0:  # un evento de monto nulo no es una distribución
                dist[_dia_utc(e["date"])] += float(e["amount"])
    splits = {_dia_utc(e["date"]): float(e["numerator"]) / float(e["denominator"]) for e in (ev.get("splits") or {}).values()}
    return filas, dict(dist), splits, repetidas


def _num(s: object) -> float | None:
    try:
        return float(str(s).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _fecha_us(s: str) -> str:
    m, d, a = s.strip().split("/")
    return f"{int(a):04d}-{int(m):02d}-{int(d):02d}"


def leer_nasdaq(historico: bytes, dividendos: bytes) -> tuple[dict[str, float], dict[str, float]]:
    h = (((json.loads(historico).get("data") or {}).get("tradesTable") or {}).get("rows")) or []
    cierres = {_fecha_us(x["date"]): _num(x.get("close")) for x in h if x.get("date")}
    d = (((json.loads(dividendos).get("data") or {}).get("dividends") or {}).get("rows")) or []
    divs: dict[str, float] = collections.defaultdict(float)
    for x in d:
        monto = _num(x.get("amount")) or 0.0
        if x.get("exOrEffDate") not in (None, "", "N/A") and str(x.get("type") or "cash").lower().startswith("cash") and monto:
            divs[_fecha_us(x["exOrEffDate"])] += monto  # un monto nulo no es una distribución
    return {k: v for k, v in cierres.items() if v}, dict(divs)


# ---------------- validación ----------------
def _valida(f: tuple) -> bool:
    o, h, lo, c, a, _ = f
    if any(x is None or x <= 0 for x in (o, h, lo, c, a)):
        return False
    return lo <= min(o, c) * (1 + 1e-3) and h >= max(o, c) * (1 - 1e-3)


def _pareados(x: dict[str, float], y: dict[str, float], lo: str | None, hi: str | None) -> float | None:
    """Fracción de las distribuciones de ``x`` en [lo, hi] con pareja en ``y`` (fecha ex ±3 días, monto ±max(2 %, 0,002))."""
    xs = {d: m for d, m in x.items() if lo and hi and lo <= d <= hi and DATOS_DESDE <= d <= DATOS_HASTA}
    if not xs:
        return None
    hit = 0
    for d, m in xs.items():
        f0 = dt.date.fromisoformat(d)
        hit += any(abs((dt.date.fromisoformat(e) - f0).days) <= 3 and abs(n - m) <= max(0.02 * m, 0.002)
                   for e, n in y.items())
    return hit / len(xs)


def validar(datos: Path = DATOS) -> dict:
    man = json.loads((datos / "MANIFIESTO.json").read_text(encoding="utf-8"))
    entradas = {(e["activo"], e["fuente"]): e for e in man["entradas"]}
    yahoo, informe = {}, {}
    for t in TODOS:
        e = entradas[(t, "yahoo")]
        b = (datos / e["archivo"]).read_bytes()
        if hashlib.sha256(b).hexdigest() != e["sha256"]:
            sys.exit(f"{t}: archivo distinto del manifiesto")
        try:
            yahoo[t] = leer_yahoo(b)
        except (ValueError, KeyError, IndexError, TypeError) as err:
            informe[t] = {"pasa": False, "motivo": f"Yahoo sin datos legibles: {err!r} (estado {e['estado']})"}
    validas = {t: {d: f for d, f in yahoo[t][0].items() if DATOS_DESDE <= d <= DATOS_HASTA and _valida(f)} for t in yahoo}
    conteo = collections.Counter(d for t in validas for d in validas[t])
    referencia = sorted(d for d, n in conteo.items() if n >= 10)
    for t, (filas, dist, splits, repetidas) in yahoo.items():
        val = validas[t]
        g: dict = {"repetidas": repetidas, "invalidas": sum(DATOS_DESDE <= d <= DATOS_HASTA and not _valida(f)
                                                              for d, f in filas.items())}
        faltan = [d for d in referencia if d not in val]
        racha = mayor = 0
        for d in referencia:
            racha = racha + 1 if d not in val else 0
            mayor = max(mayor, racha)
        g["cobertura"] = {"primera": min(val) if val else None, "ultima": max(val) if val else None,
                          "faltantes": len(faltan), "racha_maxima": mayor, "fuera_de_referencia": len(set(val) - set(referencia))}
        g["c1_cobertura"] = bool(val) and min(val) <= "2011-01-04" and max(val) == DATOS_HASTA and len(faltan) <= 5 and mayor <= 3
        dias = [d for d in referencia if d in val]
        c = [val[d][3] for d in dias]
        a = [val[d][4] for d in dias]
        # factor reconstruido con las distribuciones (ex en sesión faltante → siguiente sesión válida)
        asignada: dict[int, float] = collections.defaultdict(float)
        for d, monto in dist.items():
            k = bisect.bisect_left(dias, d)
            if 0 < k < len(dias):
                asignada[k] += monto
        f_rec = [1.0] * len(dias)
        for k in range(len(dias) - 2, -1, -1):
            f_rec[k] = f_rec[k + 1] * (1 - asignada.get(k + 1, 0.0) / c[k])
        f_prov = [x / y for x, y in zip(a, c, strict=True)]
        err = max(abs(f_prov[k] / f_prov[-1] / f_rec[k] - 1) for k in range(len(dias))) if dias else 1.0
        rel = [monto / c[k - 1] for k, monto in asignada.items()]
        por_ano: dict[str, float] = collections.defaultdict(float)
        for k, monto in asignada.items():
            por_ano[dias[k][:4]] += monto / c[k - 1]
        g["ajuste"] = {"error_maximo_factor": err, "distribuciones": len(asignada), "splits": splits,
                       "max_distribucion": max(rel, default=0.0), "max_anual": max(por_ano.values(), default=0.0)}
        g["c3_ajuste"] = err <= 0.005 and all(0 < x <= 0.15 for x in rel) and max(por_ano.values(), default=0.0) <= 0.20
        r_adj = {dias[k]: a[k] / a[k - 1] - 1 for k in range(1, len(dias))}
        saltos = [d for d, r in r_adj.items() if abs(r) > 0.35]
        # contraste con Nasdaq
        nas = None
        try:
            eh, ed = entradas[(t, "nasdaq_historico")], entradas[(t, "nasdaq_dividendos")]
            if eh["estado"] == 200 and ed["estado"] == 200:
                nas = leer_nasdaq((datos / eh["archivo"]).read_bytes(), (datos / ed["archivo"]).read_bytes())
        except (ValueError, KeyError, TypeError, AttributeError):
            nas = None
        if nas and nas[0]:
            cn, dn = nas
            cn = {d: x for d, x in cn.items() if DATOS_DESDE <= d <= DATOS_HASTA}
            comunes = sorted(set(cn) & set(dias))
            cortes = sorted(splits)
            tramos: dict[int, list[float]] = collections.defaultdict(list)
            for d in comunes:
                tramos[bisect.bisect_right(cortes, d)].append(cn[d] / val[d][3])
            med = {k: st.median(v) for k, v in tramos.items()}
            ok = sum(abs(cn[d] / val[d][3] / med[bisect.bisect_right(cortes, d)] - 1) <= 0.005 for d in comunes)
            frac_precio = ok / len(comunes) if comunes else 0.0
            cobertura_nas = len(comunes) / len(cn) if cn else 0.0
            lo_n, hi_n = (min(dn), max(dn)) if dn else (None, None)
            p1, p2 = _pareados(dn, dist, lo_n, hi_n), _pareados(dist, dn, lo_n, hi_n)
            divs_ok = (p1 is None and p2 is None) or ((p1 or 0) >= 0.95 and (p2 or 0) >= 0.95)
            r_nas = {d: cn[d] / cn[comunes[i - 1]] - 1 for i, d in enumerate(comunes) if i > 0}
            g["contraste_nasdaq"] = {"disponible": True, "dias_comunes": len(comunes), "cobertura": cobertura_nas,
                                     "fraccion_precios_dentro_0_5pct": frac_precio, "dividendos_nasdaq_pareados": p1,
                                     "dividendos_yahoo_pareados": p2}
            g["c5_contraste"] = frac_precio >= 0.99 and cobertura_nas >= 0.90 and divs_ok
            g["c4_saltos"] = all(d in r_nas and abs(r_nas[d] - r_adj[d]) <= 0.01 for d in saltos)
        else:
            g["contraste_nasdaq"] = {"disponible": False}
            g["c5_contraste"] = None
            g["c4_saltos"] = not saltos
        g["saltos_mayores_35pct"] = saltos
        g["pasa"] = bool(g["c1_cobertura"] and g["c3_ajuste"] and g["c4_saltos"] and g["c5_contraste"] is not False)
        informe[t] = g
    if len(yahoo) < 10:  # sin 10 series legibles no hay calendario de referencia: bloqueo, no diagnóstico por activo
        for t in yahoo:
            informe[t] = {"pasa": False, "motivo": f"bloqueo: solo {len(yahoo)} series de Yahoo legibles (< 10)"}
    excluidos = [t for t in TODOS if not informe[t]["pasa"]]
    por_clase = {k: sum(informe[t]["pasa"] for t in ts) for k, ts in CLASES.items()}
    out = {"manifiesto_sha256": _sha(datos / "MANIFIESTO.json"), "sesiones_de_referencia": len(referencia),
           "referencia": [referencia[0], referencia[-1]] if referencia else None, "referencia_dias": referencia,
           "activos": informe,
           "excluidos": excluidos, "activos_por_clase": por_clase,
           "yahoo_legibles": len(yahoo),  # §3: sin los 12 de Yahoo, el experimento se detiene
           "ejecutable": len(yahoo) == len(TODOS) and len(excluidos) <= 2 and min(por_clase.values()) >= 3}
    (datos / "VALIDACION.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float) + "\n",
                                           encoding="utf-8")
    print(f"validación: {len(referencia)} sesiones de referencia; excluidos {excluidos}; ejecutable {out['ejecutable']}")
    return out


def velas_ajustadas(datos: Path = DATOS) -> dict[str, list[Vela]]:
    """Velas con rendimiento total (factor adjclose/close en toda la sesión), en las sesiones de referencia válidas."""
    val = json.loads((datos / "VALIDACION.json").read_text(encoding="utf-8"))
    man = json.loads((datos / "MANIFIESTO.json").read_text(encoding="utf-8"))
    archivo = {e["activo"]: e["archivo"] for e in man["entradas"] if e["fuente"] == "yahoo"}
    incluidos = [t for t in TODOS if val["activos"][t]["pasa"]]
    filas = {t: leer_yahoo((datos / archivo[t]).read_bytes())[0] for t in incluidos}
    referencia = val["referencia_dias"]
    out = {}
    for t in incluidos:
        v = []
        for d in referencia:
            f = filas[t].get(d)
            if f and _valida(f):
                o, h, lo, c, a, vol = f
                k = a / c
                v.append(Vela(d, o * k, h * k, lo * k, a, float(vol or 0)))
        out[t] = v
    return out


# ---------------- evaluación ----------------
def hac_se(x: list[float], lags: int = NW) -> float:
    n, m = len(x), st.fmean(x)
    d = [a - m for a in x]
    g = [sum(d[t] * d[t - k] for t in range(k, n)) / n for k in range(lags + 1)]
    return math.sqrt((g[0] + 2 * sum((1 - k / (lags + 1)) * g[k] for k in range(1, lags + 1))) / n)


def estadistica(x: list[float], bloque: int = BLOQUE) -> dict:
    b = bootstrap_media(x, bloque=bloque, n=REMUESTREOS, semilla=SEMILLA)
    k, m, se = SESIONES / 365, st.fmean(x), hac_se(x)
    return {"E": m * SESIONES, "ic90_bootstrap": [b["intervalo_anual"][0] * k, b["intervalo_anual"][1] * k],
            "p_bootstrap": b["p_mayor_que_cero"], "se_newey_west": se * SESIONES, "p_newey_west": Z.cdf(m / se),
            "superior_newey_west": (m + Z.inv_cdf(0.95) * se) * SESIONES, "sesiones": len(x)}


def normalizado(v: list[Vela], x: list[float]) -> dict[str, float]:
    """z = (0,10 / σ̂ ex ante de 252 sesiones) · x, por fecha de la ventana."""
    c = [y.c for y in v]
    r = [None] + [c[k] / c[k - 1] - 1 for k in range(1, len(c))]
    idx = [k for k, y in enumerate(v) if EVAL_DESDE <= y.dia < EVAL_HASTA]
    out = {}
    for m, k in enumerate(idx):
        sig = st.stdev(r[k - VOL_SESIONES:k]) * math.sqrt(SESIONES)
        out[v[k].dia] = VOL_OBJETIVO / sig * x[m]
    return out


def agrupar(z: dict[str, dict[str, float]], clases: dict[str, list[str]]) -> tuple[list[str], dict[str, list[float]], int]:
    """Por día: media de cada clase sobre sus activos con dato; un día sin alguna clase no entra."""
    dias = sorted(set().union(*(zz.keys() for zz in z.values())))
    medias: dict[str, list[float]] = {k: [] for k in clases}
    usados, fuera = [], 0
    for d in dias:
        fila = {k: [z[t][d] for t in ts if t in z and d in z[t]] for k, ts in clases.items()}
        if not all(fila.values()):
            fuera += 1
            continue
        usados.append(d)
        for k, vals in fila.items():
            medias[k].append(st.fmean(vals))
    return usados, medias, fuera


def pool(medias: dict[str, list[float]], sin: str | None = None) -> list[float]:
    ks = [k for k in medias if k != sin]
    return [st.fmean(medias[k][i] for k in ks) for i in range(len(medias[ks[0]]))]


def metricas(r: Resultado) -> dict:
    rd = rendimientos(r)
    anos = len(rd) / SESIONES
    m, s = st.fmean(rd), st.stdev(rd)
    return {"cagr": (r.equity[-1] / r.capital) ** (1 / anos) - 1, "vol_anual": s * math.sqrt(SESIONES),
            "sharpe": m / s * math.sqrt(SESIONES) if s else None, "caida_maxima": caida([r.capital, *r.equity])[0],
            "exposicion_media": st.fmean(r.exposicion), "operaciones": len(r.operaciones),
            "costes_pp_anual": r.costes / st.fmean(r.equity) / anos * 100}


def decidir(p: float, superior: float, e_x2: float, loco: dict[str, float]) -> str:
    if superior < DELTA:
        return "SIN VENTAJA RELEVANTE"
    if p >= UMBRAL_P and e_x2 > 0 and all(x > 0 for x in loco.values()):
        return "VENTAJA TRANSFERIBLE RESPALDADA"
    return "EVIDENCIA INSUFICIENTE"


def evaluar(datos: Path = DATOS, salida: Path = RESULTADO) -> dict:
    if salida.exists():
        sys.exit(f"{salida} ya existe: el prerregistro permite una sola ejecución")
    if P.huella_codigo() != CODIGO:
        sys.exit("código de src/ distinto del congelado")
    val = json.loads((datos / "VALIDACION.json").read_text(encoding="utf-8"))
    if not val["ejecutable"]:
        sys.exit(f"datos no aptos: excluidos {val['excluidos']}; no se ejecuta")
    velas = velas_ajustadas(datos)
    clases = {k: [t for t in ts if t in velas] for k, ts in CLASES.items()}
    esc = {"base": (COSTES, 0), "costes_x2": (Costes(0, 10.0), 0), "costes_x3": (Costes(0, 15.0), 0),
           "retraso_1_sesion": (COSTES, 1), "sin_costes": (Costes(0, 0), 0)}  # sin_costes: solo descriptivo
    z: dict[str, dict] = {n: {} for n in esc}
    activos: dict = {}
    for t, v in velas.items():
        obj = senal_calendario([y.dia for y in v], [y.c for y in v])
        for n, (cst, ret) in esc.items():
            x, res = exceso(v, obj, cst, ret)
            z[n][t] = normalizado(v, x)
            if n == "base":
                activos[t] = {"exceso_timing_anual": st.fmean(x) * SESIONES, **{k: metricas(r) for k, r in res.items()}}
    out: dict = {"categoria": "HISTÓRICO con procedencia limitada (Yahoo, contrastado con Nasdaq); no prospectivo",
                 "prerregistro_sha256": _sha(PRERREGISTRO), "script_sha256": _sha(Path(__file__)), "codigo_sha256": CODIGO,
                 "manifiesto_sha256": _sha(datos / "MANIFIESTO.json"), "validacion_sha256": _sha(datos / "VALIDACION.json"),
                 "git": _git(), "excluidos": val["excluidos"], "clases": clases, "ventana": [EVAL_DESDE, EVAL_HASTA]}
    pools = {}
    for n in esc:
        dias, medias, fuera = agrupar(z[n], clases)
        pools[n] = {"dias": dias, "medias": medias, "fuera": fuera, "X": pool(medias)}
    base = pools["base"]
    prim = estadistica(base["X"])
    p_dec = min(prim["p_bootstrap"], prim["p_newey_west"])
    sup = max(prim["ic90_bootstrap"][1], prim["superior_newey_west"])
    e_x2 = st.fmean(pools["costes_x2"]["X"]) * SESIONES
    loco = {k: st.fmean(pool(base["medias"], sin=k)) * SESIONES for k in clases}
    out["decision_prerregistrada"] = decidir(p_dec, sup, e_x2, loco)
    out["principal"] = {**prim, "P_decision": p_dec, "superior_decision": sup, "E_costes_x2": e_x2,
                        "E_sin_cada_clase": loco, "sesiones_sin_alguna_clase": base["fuera"],
                        "primera_y_ultima": [base["dias"][0], base["dias"][-1]]}
    sec: dict = {"bloques": {L: estadistica(base["X"], L) for L in (20, 120)},
                 "estres": {n: estadistica(pools[n]["X"]) for n in ("costes_x2", "costes_x3", "retraso_1_sesion",
                                                                     "sin_costes")},
                 "por_clase": {k: estadistica(m) for k, m in base["medias"].items()}}
    sec["por_activo"] = {}
    for t in velas:
        zz = [z["base"][t][d] for d in sorted(z["base"][t])]
        sec["por_activo"][t] = {**activos[t], "E_normalizado": estadistica(zz)}
    comunes = sorted(set.intersection(*(set(z["base"][t]) for t in velas)))
    serie = {t: [z["base"][t][d] for d in comunes] for t in velas}
    w = {t: 1 / (len(clases) * len(ts)) for ts in clases.values() for t in ts}
    corr = {(a, b): st.correlation(serie[a], serie[b]) for a in velas for b in velas}
    clase_de = {t: k for k, ts in clases.items() for t in ts}
    dentro = [corr[a, b] for a in velas for b in velas if a < b and clase_de[a] == clase_de[b]]
    entre = [corr[a, b] for a in velas for b in velas if a < b and clase_de[a] != clase_de[b]]
    sec["correlacion"] = {"media_dentro_de_clase": st.fmean(dentro), "media_entre_clases": st.fmean(entre),
                          "activos_efectivos": 1 / sum(w[a] * w[b] * corr[a, b] for a in velas for b in velas),
                          "dias_comunes": len(comunes)}
    out["secundarios"] = sec
    salida.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float) + "\n", encoding="utf-8")
    print("DECISIÓN PRERREGISTRADA:", out["decision_prerregistrada"])
    print(f"  E {prim['E']:+.2%}/año a 10 % de vol. | IC90 bootstrap [{prim['ic90_bootstrap'][0]:+.2%}, "
          f"{prim['ic90_bootstrap'][1]:+.2%}] | P bootstrap {prim['p_bootstrap']:.3f} | P Newey–West "
          f"{prim['p_newey_west']:.3f} | límite superior {sup:+.2%} | costes ×2 {e_x2:+.2%} | sin cada clase "
          f"{ {k: f'{x:+.2%}' for k, x in loco.items()} }")
    return out


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git() -> dict:
    def g(*a: str) -> str:
        r = subprocess.run(["git", *a], check=False, cwd=RAIZ, capture_output=True, text=True)
        return r.stdout.strip()
    rel = [str(PRERREGISTRO.relative_to(RAIZ)), str(Path(__file__).relative_to(RAIZ))]
    return {"head": g("rev-parse", "HEAD"), "fecha_commit_head": g("log", "-1", "--format=%cI"),
            "prerregistro_y_script_sin_cambios_desde_head": g("status", "--porcelain", "--", *rel) == ""}


if __name__ == "__main__":
    pasos = {"autoprueba": autoprueba, "descargar": descargar, "validar": validar, "evaluar": evaluar}
    if len(sys.argv) != 2 or sys.argv[1] not in pasos:
        sys.exit(f"uso: t_multi.py {' | '.join(pasos)}")
    pasos[sys.argv[1]]()
