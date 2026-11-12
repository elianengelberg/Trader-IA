"""Aritmética normal pura (sin datos de mercado ni retornos): cota de P(RESPALDADA) con los supuestos de la v3 §7.1.
RESPALDADA exige que Holm rechace H1 y H2: (p1<=.025 y p2<=.05) o (p2<=.025 y p1<=.05).
Cota válida con cualquier dependencia: P <= P(p2<=.05) y P <= P(p1<=.05). Caso independiente: P(A)+P(B)-P(A y B)."""
from statistics import NormalDist
N = NormalDist()
q = lambda a: N.inv_cdf(1 - a)
pw = lambda d, a: 1 - N.cdf(q(a) - d)
for n in (158, 160, 274):
    anios = n / 52.1775
    for sd, te in ((0.16, 0.35), (0.12, 0.25)):
        d1 = 0.02 / (sd / n ** 0.5)
        d2 = 0.10 / (te / anios ** 0.5)
        cota = min(pw(d1, .05), pw(d2, .05))
        cota025 = min(pw(d1, .025), pw(d2, .025))
        indep = pw(d1, .025) * pw(d2, .05) + pw(d2, .025) * pw(d1, .05) - pw(d1, .025) * pw(d2, .025)
        print(f"n={n} sd_IC={sd} TE={te}: min potencias a 0,025 = {cota025:.3f} | cota válida (min a 0,05) = {cota:.3f} | independientes = {indep:.3f}")
