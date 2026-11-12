"""E4 v1 · H-XS-REV-1 prospectivo: núcleo de cálculo (sin red, sin escritura). Especificación: PRERREGISTRO_E4_v1.md.

Convenciones (fijadas en el prerregistro):
  - día d = día UTC; velas spot de Binance, pares X/USDT; cierre(d) = cierre de la vela 1d (precio a las 24:00 UTC de d);
  - entrada(d) = cierre de la primera vela 1h de d (precio a las 01:00 UTC de d);
  - día activo: hay vela 1d, operaciones > 0 y cierre > 0;
  - r_s(d) = cierre_d / cierre_{d-1} − 1 si d−1 y d son activos; si no, NaN;
  - universo U(t): pares no excluidos (lista fija, apalancados, y paridad: los 30 cierres en [0,97; 1,03]), activos los 30 días
    [t−30, t−1], los N_MAX con mayor mediana de volumen en USDT de esos 30 días (solo datos ≤ t−1);
  - señal en t: s = −r(t−1), conocida a las 00:00 UTC de t;
  - resultado (RETRASO = "1h"): entrada(t+1) / entrada(t) − 1 — se compra a las 01:00 de t y se vende a las 01:00 de t+1
    (una barra horaria de retraso, P19); con RETRASO = "1d": r(t+1) (un día de retraso, como la v0);
  - IC_t = Spearman (rangos promedio en empates) entre s y el resultado, con los pares que tienen ambos valores.
Todo acceso a datos pasa por `Datos.hasta(t)`, que devuelve una vista truncada: es imposible leer un día > límite.
"""
import math
import re

import numpy as np

import secuencial as SQ

N_MAX, N_MIN, VENTANA, N_LIQUIDOS = 100, 30, 30, 50
RETRASO = "1h"
MIRADAS = (365, 730)  # días de formación en cada mirada; la última es la final
FRAC_MAX_NO_EVALUABLE = 0.20
SESOI = 0.01  # IC mínimo de interés para la INFORMACIÓN (convención; no es un umbral económico)
BANDA_PARIDAD = (0.97, 1.03)
EXCLUIDOS_FIJOS = {"USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDS", "USDSB", "UST", "USTC", "SUSD", "PAXG",
                   "XAUT", "AEUR", "EURI", "USD1", "BIDR", "IDRT", "BVND", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "UAH",
                   "NGN", "ZAR", "JPY", "PLN", "RON", "ARS", "MXN", "COP", "CZK",
                   "WBTC", "WBETH", "BETH"}  # v1: envoltorios de un activo que ya está en el universo
APALANCADO = re.compile(r"^(.+)(UP|DOWN|BULL|BEAR)$")
COMISION_BPS, MEDIO_SPREAD_BPS = 7.5, 5.0
NW_REZAGOS = 5
FRAC_DIAS_EXTREMOS = 0.05


class FugaDeFuturo(Exception):
    pass


class Datos:
    """cierre[s], volq[s], ops[s], entrada[s]: arreglos por índice de día (0 = primer día del panel). `limite` = último día legible."""

    def __init__(self, cierre, volq, ops, entrada=None, limite=None):
        self.cierre, self.volq, self.ops = cierre, volq, ops
        self.entrada = entrada if entrada is not None else {s: np.zeros(len(v)) for s, v in cierre.items()}
        self.n = len(next(iter(cierre.values())))
        self.limite = self.n - 1 if limite is None else limite

    def hasta(self, t):
        if t > self.limite:
            raise FugaDeFuturo(f"se pidió hasta {t} con límite {self.limite}")
        return Datos(self.cierre, self.volq, self.ops, self.entrada, limite=t)

    def _chk(self, d):
        if d > self.limite:
            raise FugaDeFuturo(f"lectura del día {d} con límite {self.limite}")

    def activo(self, s, d):
        self._chk(d)
        return d >= 0 and self.ops[s][d] > 0 and self.cierre[s][d] > 0

    def ret(self, s, d):
        self._chk(d)
        if d < 1 or not (self.activo(s, d) and self.activo(s, d - 1)):
            return math.nan
        return self.cierre[s][d] / self.cierre[s][d - 1] - 1.0

    def precio_entrada(self, s, d):
        self._chk(d)
        p = self.entrada[s][d] if d >= 0 else 0.0
        return p if p > 0 else math.nan

    def resultado(self, s, t):
        """Retorno de la posición formada en t. Necesita la vista hasta t+1."""
        if RETRASO == "1h":
            a, b = self.precio_entrada(s, t), self.precio_entrada(s, t + 1)
            return b / a - 1.0 if not (math.isnan(a) or math.isnan(b)) else math.nan
        return self.ret(s, t + 1)


def excluido(simbolo, todos):
    base = simbolo[:-4]
    m = APALANCADO.match(base)
    return base in EXCLUIDOS_FIJOS or bool(m and (m.group(1) + "USDT") in todos)


def en_paridad(v, s, dias):
    lo, hi = BANDA_PARIDAD
    return all(lo <= v.cierre[s][d] <= hi for d in dias)


def universo(datos, t):
    """Solo usa datos ≤ t−1 (se le pasa la vista truncada). Devuelve U ordenado por volumen descendente."""
    v = datos.hasta(t - 1)
    todos = set(v.cierre)
    cand = []
    if t - VENTANA < 0:
        return []
    ventana = range(t - VENTANA, t)
    for s in sorted(todos):
        if excluido(s, todos):
            continue
        if all(v.activo(s, d) for d in ventana) and not en_paridad(v, s, ventana):
            cand.append((float(np.median([v.volq[s][d] for d in ventana])), s))
    cand.sort(key=lambda x: (-x[0], x[1]))
    return [s for _, s in cand[:N_MAX]]


def senal(datos, t, U):
    v = datos.hasta(t - 1)
    return {s: -v.ret(s, t - 1) for s in U}


def rangos(x):
    """Rangos 0..n−1 con promedio en los empates."""
    x = np.asarray(x, float)
    o = np.argsort(x, kind="mergesort")
    xs = x[o]
    r = np.empty(len(x))
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and xs[j + 1] == xs[i]:
            j += 1
        r[o[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = rangos(a), rangos(b)
    ra -= ra.mean()
    rb -= rb.mean()
    den = math.sqrt((ra * ra).sum() * (rb * rb).sum())
    return float((ra * rb).sum() / den) if den > 0 else math.nan


def dia(datos, t):
    """Todo lo de la formación t. El resultado se lee con la vista hasta t+1, nunca más allá."""
    U = universo(datos, t)
    if len(U) < N_MIN:
        return {"t": t, "evaluable": False, "n_universo": len(U)}
    s = senal(datos, t, U)
    v1 = datos.hasta(t + 1)
    res = {x: v1.resultado(x, t) for x in U}
    salidas = sum(1 for x in U if math.isnan(res[x]))
    validos = [x for x in U if not math.isnan(res[x])]
    if len(validos) < N_MIN:
        return {"t": t, "evaluable": False, "n_universo": len(U), "salidas": salidas}
    ic = spearman([s[x] for x in validos], [res[x] for x in validos])
    liq = [x for x in U[:N_LIQUIDOS] if x in set(validos)]
    ic50 = spearman([s[x] for x in liq], [res[x] for x in liq]) if len(liq) >= N_MIN else math.nan
    # Secundaria: cartera solo larga del quintil con mayor señal (peores de ayer) frente a pesos iguales en U.
    orden = sorted(((s[x], x) for x in U), key=lambda z: (-z[0], z[1]))
    q = [x for _, x in orden[:max(1, len(orden) // 5)]]
    r1 = {x: (0.0 if math.isnan(r) else r) for x, r in res.items()}  # salida: se liquida al último precio (convención declarada)
    return {"t": t, "evaluable": True, "n_universo": len(U), "n_ic": len(validos), "salidas": salidas, "ic": ic, "ic50": ic50,
            "ret_q": float(np.mean([r1[x] for x in q])), "ret_ew": float(np.mean([r1[x] for x in U])),
            "mercado_senal": float(np.mean([-s[x] for x in U])), "cartera_q": q}


def rotacion(dias):
    """Rotación diaria de la cartera de quintil, con pesos iguales: 0,5 · Σ|Δw| (1 en el primer día y tras un día no evaluable)."""
    out, prev = [], None
    for d in dias:
        if not d.get("evaluable"):
            prev = None
            continue
        w = {x: 1.0 / len(d["cartera_q"]) for x in d["cartera_q"]}
        out.append(1.0 if prev is None else 0.5 * sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in set(w) | set(prev)))
        prev = w
    return out


def newey_west(x, rezagos=NW_REZAGOS):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    n = len(x)
    mu = x.mean()
    e = x - mu
    s = (e @ e) / n
    for k in range(1, rezagos + 1):
        s += 2 * (1 - k / (rezagos + 1)) * (e[k:] @ e[:-k]) / n
    return mu, math.sqrt(s / n), n


def economia(dias, comision_bps=COMISION_BPS, medio_spread_bps=MEDIO_SPREAD_BPS):
    ev = [d for d in dias if d.get("evaluable")]
    bruto = [d["ret_q"] - d["ret_ew"] for d in ev]
    costo = [r * 2 * (comision_bps + medio_spread_bps) / 1e4 for r in rotacion(dias)]
    g, _, _ = newey_west(bruto)
    c = float(np.mean(costo))
    neto_mu, neto_se, _ = newey_west([b - k for b, k in zip(bruto, costo)])
    return {"bruto_diario_medio": g, "costo_diario_medio": c, "rotacion_media": float(np.mean(rotacion(dias))),
            "descarte_rapido_economico": bool(g < 2 * c), "neto_diario_medio": neto_mu,
            "t_neto": neto_mu / neto_se if neto_se > 0 else math.nan}


def robustez(ev):
    """Señales de fragilidad (solo pueden rebajar RESPALDADA; no son pruebas adicionales). True = frágil."""
    ic = np.array([d["ic"] for d in ev])
    k = int(math.ceil(FRAC_DIAS_EXTREMOS * len(ic)))
    sin_extremos = float(np.mean(ic[np.argsort(-np.abs(ic))[k:]]))
    ic50 = np.array([d["ic50"] for d in ev], float)
    ic50 = ic50[~np.isnan(ic50)]
    m50 = float(np.mean(ic50)) if len(ic50) else math.nan
    xs = np.array([np.sign(d["mercado_senal"]) * np.sign(d["ret_ew"]) for d in ev])
    grupos = [ic[xs == v] for v in (1.0, -1.0)]
    intercepto = float((grupos[0].mean() + grupos[1].mean()) / 2) if all(len(g) for g in grupos) else math.nan
    return {"ic_sin_5pct_dias_extremos": sin_extremos, "ic_50_mas_liquidos": m50, "ic_sin_componente_signo_mercado": intercepto,
            "fragil": {"pocos_dias_extremos": sin_extremos <= 0, "iliquidos": not (m50 > 0),
                       "componente_mercado": not (intercepto > 0)}}


def evaluar_mirada(dias, k, miradas=MIRADAS, n1_registrado=None):
    """Clasificación prerregistrada (PRERREGISTRO_E4_v1 §6) en la mirada k (1-based). Una mirada intermedia que no corta
    devuelve SOLO la decisión CONTINUAR (u OMITIDA) y el número de días evaluables: ningún estadístico."""
    final = k == len(miradas)
    ev = [d for d in dias if d.get("evaluable")]
    frac_no_eval = 1 - len(ev) / len(dias) if dias else 1.0
    if not final and (frac_no_eval > FRAC_MAX_NO_EVALUABLE or len(ev) < 30):
        return {"mirada": k, "decision": "OMITIDA", "n_evaluables": len(ev), "frac_no_evaluable": frac_no_eval}
    if final and (frac_no_eval > FRAC_MAX_NO_EVALUABLE or len(ev) < (1 - FRAC_MAX_NO_EVALUABLE) * miradas[-1]):
        return {"mirada": k, "decision": "FINAL", "clasificacion": "INVALIDO", "n_evaluables": len(ev), "frac_no_evaluable": frac_no_eval}
    mu, se, n = newey_west([d["ic"] for d in ev])
    t = mu / se
    if len(miradas) == 1:
        b = SQ.limites_nw(None, n, n)[1]
    elif final:
        b = SQ.limites_nw(n1_registrado, n, miradas[-1])[1]
    else:
        b = SQ.limites_nw(n, miradas[-1], miradas[-1])[0]
    cota = mu + b * se
    if t >= b:
        clase = "RESPALDADA_INFORMACION"
    elif t <= -b:
        clase = "EN_CONTRA_SIGNO_OPUESTO"
    elif cota < SESOI:
        clase = "REFUTADA_IC_MINIMO"
    elif not final:
        return {"mirada": k, "decision": "CONTINUAR", "n_evaluables": n, "frac_no_evaluable": frac_no_eval}
    else:
        clase = "INSUFICIENTE"
    serie_ic = np.array([d["ic"] for d in ev])
    out = {"mirada": k, "decision": "FINAL", "clasificacion": clase, "ic_medio": mu, "ee_nw": se, "t": t, "limite": b,
           "cota_superior_repetida": cota, "n_dias": n, "frac_no_evaluable": frac_no_eval,
           "autocorrelacion_ic_rezago1": float(np.corrcoef(serie_ic[1:], serie_ic[:-1])[0, 1]),  # diagnóstico (§5)
           "salidas_totales": int(sum(d.get("salidas", 0) for d in ev)), **economia(dias)}
    if clase == "RESPALDADA_INFORMACION":
        r = robustez(ev)
        out["robustez"] = r
        if any(r["fragil"].values()):
            out["clasificacion"] = "RESPALDADA_NO_ROBUSTA"
    out["nota"] = ("INSUFICIENTE no equivale a refutar. REFUTADA_IC_MINIMO descarta un IC ≥ 0,01 (umbral de información, no económico). "
                   "Ninguna clase habla de rentabilidad: eso lo dice solo la parte económica (descarte rápido y neto).")
    return out
