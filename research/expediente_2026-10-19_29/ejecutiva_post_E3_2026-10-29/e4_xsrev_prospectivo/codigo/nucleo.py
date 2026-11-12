"""E4 · H-XS-REV-1 prospectivo: núcleo de cálculo (sin red, sin escritura). Especificación: PRERREGISTRO_E4.md.

Convenciones (fijadas en el prerregistro):
  - día d = día UTC; vela 1d de Binance spot, pares X/USDT;
  - día activo: hay vela, operaciones > 0 y cierre > 0;
  - r_s(d) = cierre_d / cierre_{d-1} − 1 si d−1 y d son activos; si no, NaN;
  - universo U(t): pares no excluidos, activos los 30 días [t−30, t−1], los N_MAX con mayor mediana de volumen en USDT de
    esos 30 días (solo datos ≤ t−1);
  - señal en t: s = −r(t−1) (reversión), con datos ≤ t−1;
  - resultado: r(t+1) (un día de retraso: la cartera se arma al cierre de t y se cierra al cierre de t+1);
  - IC_t = correlación de Spearman entre s y r(t+1) en U(t), con los pares que tienen ambos valores.
Todo acceso a datos pasa por `Datos.hasta(t)`, que devuelve una vista truncada: es imposible leer un día > límite.
"""
import math
import re

import numpy as np

N_MAX, N_MIN, VENTANA = 100, 30, 30
EXCLUIDOS_FIJOS = {"USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDS", "USDSB", "UST", "USTC", "SUSD", "PAXG",
                   "XAUT", "AEUR", "EURI", "USD1", "BIDR", "IDRT", "BVND", "EUR", "GBP", "AUD", "TRY", "BRL", "RUB", "UAH",
                   "NGN", "ZAR", "JPY", "PLN", "RON", "ARS", "MXN", "COP", "CZK"}
APALANCADO = re.compile(r"^(.+)(UP|DOWN|BULL|BEAR)$")
COMISION_BPS, MEDIO_SPREAD_BPS = 7.5, 5.0
NW_REZAGOS = 5


class FugaDeFuturo(Exception):
    pass


class Datos:
    """cierre[s], volq[s], ops[s]: arreglos por índice de día (0 = primer día del panel). `limite` es el último día legible."""

    def __init__(self, cierre, volq, ops, limite=None):
        self.cierre, self.volq, self.ops = cierre, volq, ops
        self.n = len(next(iter(cierre.values())))
        self.limite = self.n - 1 if limite is None else limite

    def hasta(self, t):
        if t > self.limite:
            raise FugaDeFuturo(f"se pidió hasta {t} con límite {self.limite}")
        return Datos(self.cierre, self.volq, self.ops, limite=t)

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


def excluido(simbolo, todos):
    base = simbolo[:-4]
    m = APALANCADO.match(base)
    return base in EXCLUIDOS_FIJOS or bool(m and (m.group(1) + "USDT") in todos)


def universo(datos, t):
    """Solo usa datos ≤ t−1 (se le pasa la vista truncada)."""
    v = datos.hasta(t - 1)
    todos = set(v.cierre)
    cand = []
    for s in sorted(todos):
        if excluido(s, todos) or t - VENTANA < 0:
            continue
        if all(v.activo(s, d) for d in range(t - VENTANA, t)):
            cand.append((float(np.median([v.volq[s][d] for d in range(t - VENTANA, t)])), s))
    cand.sort(key=lambda x: (-x[0], x[1]))
    return [s for _, s in cand[:N_MAX]]


def senal(datos, t, U):
    v = datos.hasta(t - 1)
    return {s: -v.ret(s, t - 1) for s in U}


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra, rb = a.argsort().argsort().astype(float), b.argsort().argsort().astype(float)
    ra -= ra.mean()
    rb -= rb.mean()
    den = math.sqrt((ra * ra).sum() * (rb * rb).sum())
    return float((ra * rb).sum() / den) if den > 0 else math.nan


def dia(datos, t):
    """Todo lo de la formación t. El resultado r(t+1) se lee con la vista hasta t+1, nunca más allá."""
    U = universo(datos, t)
    if len(U) < N_MIN:
        return {"t": t, "evaluable": False, "n_universo": len(U)}
    s = senal(datos, t, U)
    v1 = datos.hasta(t + 1)
    pares = [(s[x], v1.ret(x, t + 1)) for x in U if not math.isnan(s[x])]
    salidas = sum(1 for x in U if not v1.activo(x, t + 1))
    validos = [(a, b) for a, b in pares if not math.isnan(b)]
    if len(validos) < N_MIN:
        return {"t": t, "evaluable": False, "n_universo": len(U), "salidas": salidas}
    ic = spearman([a for a, _ in validos], [b for _, b in validos])
    # Secundaria (descarte rápido): cartera solo larga del quintil con mayor señal (peores de ayer) frente a pesos iguales en U.
    orden = sorted(((a, x) for x in U for a in [s[x]] if not math.isnan(a)), key=lambda z: (-z[0], z[1]))
    q = [x for _, x in orden[:max(1, len(orden) // 5)]]
    r1 = {x: (0.0 if not v1.activo(x, t + 1) else v1.ret(x, t + 1)) for x in U}  # salida: liquidación al último cierre
    r1 = {x: (0.0 if math.isnan(r) else r) for x, r in r1.items()}
    ret_q = float(np.mean([r1[x] for x in q]))
    ret_ew = float(np.mean([r1[x] for x in U]))
    return {"t": t, "evaluable": True, "n_universo": len(U), "n_ic": len(validos), "salidas": salidas, "ic": ic,
            "ret_q": ret_q, "ret_ew": ret_ew, "cartera_q": q}


def rotacion(dias):
    """Rotación diaria de la cartera de quintil, con pesos iguales: 0,5 · Σ|Δw|."""
    out, prev = [], None
    for d in dias:
        if not d.get("evaluable"):
            prev = None
            continue
        w = {x: 1.0 / len(d["cartera_q"]) for x in d["cartera_q"]}
        if prev is None:
            out.append(1.0)
        else:
            out.append(0.5 * sum(abs(w.get(k, 0) - prev.get(k, 0)) for k in set(w) | set(prev)))
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


def evaluar(dias, medio_spread_bps=MEDIO_SPREAD_BPS):
    """Clasificación prerregistrada (PRERREGISTRO_E4 §6). Una sola mirada."""
    ev = [d for d in dias if d.get("evaluable")]
    frac_no_eval = 1 - len(ev) / len(dias) if dias else 1.0
    if not dias or frac_no_eval > 0.20 or len(ev) < 250:
        return {"clasificacion": "INVALIDO", "dias": len(dias), "evaluables": len(ev), "frac_no_evaluable": frac_no_eval}
    mu, se, n = newey_west([d["ic"] for d in ev])
    t = mu / se
    cota_sup = mu + 1.96 * se
    bruto = [d["ret_q"] - d["ret_ew"] for d in ev]
    rot = rotacion(dias)
    costo = [r * 2 * (COMISION_BPS + medio_spread_bps) / 1e4 for r in rot]
    g, g_se, _ = newey_west(bruto)
    c = float(np.mean(costo))
    neto_mu, neto_se, _ = newey_west([b - k for b, k in zip(bruto, costo)])
    if t > 1.96:
        clase = "RESPALDADA_INFORMACION"
    elif t < -1.96:
        clase = "EN_CONTRA_SIGNO_OPUESTO"
    elif cota_sup < 0.01:
        clase = "REFUTADA_TAMANO_RELEVANTE"
    else:
        clase = "INSUFICIENTE"
    return {"clasificacion": clase, "ic_medio": mu, "ee_nw": se, "t": t, "cota_superior_975": cota_sup, "n_dias": n,
            "frac_no_evaluable": frac_no_eval, "bruto_diario_medio": g, "costo_diario_medio": c,
            "descarte_rapido_economico": bool(g < 2 * c), "neto_diario_medio": neto_mu, "t_neto": neto_mu / neto_se if neto_se > 0 else math.nan,
            "nota": "INSUFICIENTE no equivale a refutar la hipótesis; solo REFUTADA_TAMANO_RELEVANTE descarta el efecto de tamaño ≥ 0,01"}
