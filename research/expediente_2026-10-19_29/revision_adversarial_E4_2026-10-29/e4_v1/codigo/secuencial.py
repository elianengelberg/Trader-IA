"""E4 v1 · Diseño secuencial de grupo con dos miradas fijas en el calendario (sin datos; solo la normal estándar).
Gasto de α de Lan-DeMets tipo O'Brien-Fleming, unilateral por cola (α = 0,025 en cada cola, simétrico):
    α(τ) = 2 − 2·Φ(z_{1−α/2} / √τ),  τ = fracción de información = días evaluables / días planificados.
Mirada 1: b1 = z_{1−α(τ1)}. Mirada final: se gasta todo α; b2 resuelve  α(τ1) + P(Z1 < b1, Z2 ≥ b2) = α,
con corr(Z1, Z2) = √(n1 / n2). Si la mirada 1 se omitió (por falta de días evaluables), b2 = z_{1−α}.
El mismo par (b1, b2) se usa para la cola inferior (EN_CONTRA) y para los intervalos de confianza repetidos
(media ± b_k·EE), que tienen cobertura simultánea en las dos miradas.
`limites` da los valores con un t normal (para la tabla de potencia); la evaluación usa `limites_nw`, calibrados por simulación
para el t de Newey-West con los n observados, porque con valores normales ese t rechaza de más (registro/alfa_preciso.json).
Uso: biblioteca (`limites`) y, como script, la tabla de potencia del diseño (python -I -B secuencial.py)."""
import functools
import math
from statistics import NormalDist

_N = NormalDist()
ALFA = 0.025


def Phi(x):
    return _N.cdf(x)


def z(p):
    return _N.inv_cdf(p)


def gasto(tau, alfa=ALFA):
    tau = min(max(tau, 1e-12), 1.0)
    return 2.0 - 2.0 * Phi(z(1 - alfa / 2) / math.sqrt(tau))


def _p_no1_si2(b1, b2, rho, m1=0.0, m2=0.0, pasos=4000):
    """P(Z1 < b1, Z2 ≥ b2) con Z1 ~ N(m1,1), Z2 ~ N(m2,1), corr ρ. Integración de Simpson sobre z1."""
    a, b = m1 - 9.0, b1
    if b <= a:
        return 0.0
    h = (b - a) / pasos
    s = 0.0
    r = math.sqrt(1 - rho * rho)
    for i in range(pasos + 1):
        z1 = a + i * h
        f = math.exp(-0.5 * (z1 - m1) ** 2) / math.sqrt(2 * math.pi) * (1 - Phi((b2 - m2 - rho * (z1 - m1)) / r))
        s += f * (1 if i in (0, pasos) else (4 if i % 2 else 2))
    return s * h / 3


@functools.lru_cache(maxsize=None)
def limites(n1, n2, n_plan, alfa=ALFA):
    """Devuelve (b1, b2). n1 = días evaluables en la mirada 1 (None si se omitió), n2 = en la final, n_plan = planificados."""
    if n1 is None:
        return None, z(1 - alfa)
    a1 = gasto(n1 / n_plan, alfa)
    b1 = z(1 - a1)
    rho = math.sqrt(n1 / n2)
    lo, hi = 0.0, 6.0
    for _ in range(80):
        m = (lo + hi) / 2
        if a1 + _p_no1_si2(b1, m, rho) > alfa:
            lo = m
        else:
            hi = m
    return b1, (lo + hi) / 2


NW_REZAGOS = 5
SEMILLA_CALIBRACION, SIMS_CALIBRACION, LOTE = 20261029, 200000, 20000


def t_newey_west(X, rezagos=NW_REZAGOS):
    """t de Newey-West (Bartlett) por fila; idéntico a nucleo.newey_west."""
    import numpy as np
    n = X.shape[1]
    e = X - X.mean(1)[:, None]
    s = (e * e).sum(1) / n
    for k in range(1, rezagos + 1):
        s += 2 * (1 - k / (rezagos + 1)) * (e[:, k:] * e[:, :-k]).sum(1) / n
    return X.mean(1) / np.sqrt(s / n)


@functools.lru_cache(maxsize=None)
def limites_nw(n1, n2, n_plan, alfa=ALFA):
    """Límites calibrados para el t de Newey-West (los de `limites` suponen un t normal y, con estos n, rechazan de más).
    Simulación determinista (semilla fija, numpy PCG64) de SIMS_CALIBRACION series gaussianas iid de largo n2, con sus
    antitéticas (−X), bajo el nulo. Mirada 1: b1 = cuantil 1 − α(τ1) del t en los primeros n1 días. Final: b2 tal que
    P(t1 < b1, t2 ≥ b2) = α − α(τ1). Sin mirada 1: b2 = cuantil 1 − α del t con n2 días."""
    import numpy as np
    g = np.random.default_rng(SEMILLA_CALIBRACION)
    t1s, t2s = [], []
    for _ in range(SIMS_CALIBRACION // LOTE):
        X = g.standard_normal((LOTE, n2))
        t2 = t_newey_west(X)
        t2s += [t2, -t2]
        if n1 is not None:
            t1 = t_newey_west(X[:, :n1])
            t1s += [t1, -t1]
    t2 = np.concatenate(t2s)
    if n1 is None:
        return None, float(np.quantile(t2, 1 - alfa))
    t1 = np.concatenate(t1s)
    a1 = gasto(n1 / n_plan, alfa)
    b1 = float(np.quantile(t1, 1 - a1))
    resto = np.sort(t2[t1 < b1])[::-1]
    k = int(round((alfa - a1) * len(t2)))
    return b1, float(resto[k - 1])


def potencia(ic, sd, phi, n1, n2, n_plan, lim=None):
    """Potencia (cola superior) del diseño de dos miradas para un IC verdadero, con desvío diario sd y AR(1) φ.
    `lim` = (b1, b2); por defecto, los normales."""
    f = math.sqrt((1 + phi) / (1 - phi))
    m1, m2 = ic / (sd * f / math.sqrt(n1)), ic / (sd * f / math.sqrt(n2))
    b1, b2 = lim if lim else limites(n1, n2, n_plan)
    p1 = 1 - Phi(b1 - m1)
    return p1, p1 + _p_no1_si2(b1, b2, math.sqrt(n1 / n2), m1, m2)


if __name__ == "__main__":
    LN, LC = limites(365, 730, 730), limites_nw(365, 730, 730)
    c365, c730 = limites_nw(None, 365, 365)[1], limites_nw(None, 730, 730)[1]
    print(f"Límites normales 365/730: b1 = {LN[0]:.4f}, b2 = {LN[1]:.4f}. Calibrados para el t de Newey-West (los que usa la v1): "
          f"b1 = {LC[0]:.4f}, b2 = {LC[1]:.4f}; una mirada: {c365:.4f} (365) y {c730:.4f} (730). α por cola = {ALFA}")
    print("Aproximación normal con los límites calibrados; supuestos [Hip]: sd del IC diario y AR(1) φ no medidos.")
    print("sd    φ    IC    | 1 mirada 365 | 1 mirada 730 | 2 miradas: P(cortar en 365) · potencia total")
    for sd in (0.10, 0.15, 0.20, 0.25):
        for phi in (0.0, 0.1):
            f = math.sqrt((1 + phi) / (1 - phi))
            for ic in (0.01, 0.02, 0.03):
                a = 1 - Phi(c365 - ic / (sd * f / math.sqrt(365)))
                d = 1 - Phi(c730 - ic / (sd * f / math.sqrt(730)))
                p1, pt = potencia(ic, sd, phi, 365, 730, 730, LC)
                print(f"{sd:.2f} {phi:.1f}  {ic:.2f}  |     {a:.2f}     |     {d:.2f}     |     {p1:.2f} · {pt:.2f}")
