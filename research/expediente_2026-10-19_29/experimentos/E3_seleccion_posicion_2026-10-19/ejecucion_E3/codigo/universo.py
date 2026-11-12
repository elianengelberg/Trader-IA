"""E3 · panel, elegibilidad, universos y señal (v3 §2.2, §4.3–4.6). Sin rendimientos de estrategia.

Convención de índices: día i = INICIO + i (UTC). Formación en el lunes t usa días ≤ t − 1.
"""
import datetime as dt
import re

import numpy as np

INICIO = dt.date(2017, 7, 1)
FIAT_ISO = {"AED", "ARS", "AUD", "BRL", "CAD", "CHF", "CLP", "CNY", "COP", "CZK", "DKK", "EUR", "GBP", "HKD", "HUF", "IDR", "ILS", "INR",
            "JPY", "KES", "KRW", "KZT", "MXN", "NGN", "NOK", "NZD", "PEN", "PHP", "PKR", "PLN", "RON", "RUB", "SAR", "SEK", "SGD", "THB",
            "TRY", "TWD", "UAH", "USD", "VND", "ZAR"}
LISTA_FIJA = {"USDC", "BUSD", "TUSD", "USDP", "PAX", "DAI", "FDUSD", "USDS", "USDSB", "UST", "USTC", "SUSD", "PAXG", "XAUT", "AEUR",
              "EURI", "USD1", "BIDR", "IDRT", "BVND"} | FIAT_ISO


def base_de(s: str) -> str:
    return s[:-4] if s.endswith("USDT") else s


class Panel:
    """Series diarias por símbolo. act = día activo (operaciones > 0 y fila válida)."""

    def __init__(self, simbolos, O, C, QV, act, mapeos_renombre=None):
        self.sym = list(simbolos)
        self.O, self.C, self.QV, self.act = O, C, QV, act.astype(bool)
        self.S, self.D = act.shape
        self.base = [base_de(s) for s in self.sym]
        bases = set(self.base)
        self.apalancado = np.array([any(b.endswith(suf) and b[:-len(suf)] in bases for suf in ("UP", "DOWN", "BULL", "BEAR")) for b in self.base])
        self.fijo = np.array([b in LISTA_FIJA for b in self.base])
        self.mapeos = mapeos_renombre or []
        self._derivados()

    def _derivados(self):
        S, D, act = self.S, self.D, self.act
        self.ult_act = np.full((S, D), -1, dtype=np.int64)        # último día activo ≤ d
        self.inact_run = np.zeros((S, D), dtype=np.int64)           # días inactivos seguidos que terminan en d
        self.ep_ini = np.full((S, D), -1, dtype=np.int64)          # inicio del listado vigente del último día activo ≤ d
        for s in range(S):
            a = act[s]
            last, run, ini = -1, 0, -1
            for d in range(D):
                if a[d]:
                    if last < 0 or d - last - 1 >= 30:
                        ini = d
                    last, run = d, 0
                else:
                    run += 1
                self.ult_act[s, d], self.inact_run[s, d], self.ep_ini[s, d] = last, run, ini
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.log(self.C[:, 1:] / self.C[:, :-1])
        ok = act[:, 1:] & act[:, :-1]
        self.r = np.full((S, D), np.nan)
        self.r[:, 1:] = np.where(ok, r, np.nan)

    def pval(self, s, d):
        j = self.ult_act[s, d]
        return self.C[s, j] if j >= 0 else np.nan


def _rangos_promedio(x: np.ndarray) -> np.ndarray:
    orden = np.argsort(x, kind="mergesort")
    r = np.empty(x.size)
    xs = x[orden]
    i = 0
    while i < x.size:
        j = i
        while j + 1 < x.size and xs[j + 1] == xs[i]:
            j += 1
        r[orden[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra, rb = _rangos_promedio(a), _rangos_promedio(b)
    ra -= ra.mean()
    rb -= rb.mean()
    den = np.sqrt((ra @ ra) * (rb @ rb))
    return float(ra @ rb / den) if den > 0 else float("nan")


def universo(P: Panel, t: int, excluidos=frozenset(), N_inv: int = 30, N_pred: int = 100, horizontes=(7, 14, 21, 28)):
    """Elegibles en t (v3 §4.4–4.5), U_pred (100) y U_inv (30) por V; señal S en U_pred (§4.6). Solo datos ≤ t − 1."""
    if t < 91:
        return None
    w = slice(t - 30, t)
    c1 = P.act[:, w].all(axis=1)                                   # (a)
    edad = t - P.ep_ini[:, t - 1]
    c2 = (P.ep_ini[:, t - 1] >= 0) & (edad >= 180)                 # (b) días calendario (N, v3 §4.4)
    V = np.nanmedian(np.where(P.act[:, w], P.QV[:, w], np.nan), axis=1)
    c4 = V >= 1_000_000                                            # (d)
    cand = c1 & c2 & c4 & ~P.fijo & ~P.apalancado
    if excluidos:
        cand &= np.array([s not in excluidos for s in P.sym])
    idx = np.flatnonzero(cand)
    if idx.size == 0:
        return {"t": t, "elegibles": [], "U_pred": [], "U_inv": [], "V": V}
    R90 = P.r[idx, t - 90:t]                                        # retornos diarios en [t−90, t−1]
    M = ~np.isnan(R90)
    nvol = M.sum(axis=1)
    with np.errstate(invalid="ignore"):
        sd = np.nanstd(np.where(M, R90, np.nan), axis=1, ddof=1)
    vol_baja = (nvol >= 60) & (sd * np.sqrt(365) < 0.10)          # N3
    idx, R90, M = idx[~vol_baja], R90[~vol_baja], M[~vol_baja]
    orden = sorted(range(idx.size), key=lambda k: (-V[idx[k]], P.sym[idx[k]]))
    idx, R90, M = idx[orden], R90[orden], M[orden]
    X = np.where(M, R90, 0.0)
    Mf = M.astype(float)
    n = Mf @ Mf.T
    Sx = X @ Mf.T
    Sxx = (X * X) @ Mf.T
    Sxy = X @ X.T
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = n * Sxy - Sx * Sx.T
        var = (n * Sxx) - Sx ** 2
        corr = cov / np.sqrt(var * var.T)
    aceptados = []
    for k in range(idx.size):                                       # duplicados: se excluye el de menor V (orden V desc)
        if any(n[k, a] >= 60 and corr[k, a] > 0.98 for a in aceptados):
            continue
        aceptados.append(k)
    eleg = idx[aceptados]
    U_pred = eleg[:N_pred]
    U_inv = eleg[:N_inv]
    Rh = {h: np.log(P.C[U_pred, t - 1] / P.C[U_pred, t - 1 - h]) for h in horizontes}
    n_p = U_pred.size
    S = np.zeros(n_p)
    for h in horizontes:
        S += (_rangos_promedio(Rh[h]) - 1.0) / (n_p - 1) if n_p > 1 else 0.0
    S /= len(horizontes)
    A = np.mean([Rh[h] for h in horizontes], axis=0)
    pos_pred = {int(s): k for k, s in enumerate(U_pred)}
    inv_orden = sorted(U_inv.tolist(), key=lambda s: (-S[pos_pred[s]], -V[s], P.sym[s]))
    rk = {int(s): k + 1 for k, s in enumerate(inv_orden)}
    rango_V = {int(s): k + 1 for k, s in enumerate(eleg.tolist())}
    return {"t": t, "elegibles": eleg.tolist(), "U_pred": U_pred.tolist(), "U_inv": U_inv.tolist(), "S": S, "A": A,
            "pos_pred": pos_pred, "rk": rk, "rango_V": rango_V, "V": V, "n_elegibles": int(eleg.size)}


def lunes(desde: dt.date, hasta: dt.date, dia_semana: int = 0):
    d = desde + dt.timedelta(days=(dia_semana - desde.weekday()) % 7)
    out = []
    while d <= hasta:
        out.append((d - INICIO).days)
        d += dt.timedelta(days=7)
    return out
