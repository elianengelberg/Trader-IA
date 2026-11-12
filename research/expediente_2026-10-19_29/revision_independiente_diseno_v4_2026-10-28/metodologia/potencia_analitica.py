"""Potencia analítica con los supuestos DECLARADOS en la v3 §7.1 (sin datos): aproximación normal, sin autocorrelación
adicional, prueba unilateral.
- H1: IC semanal con desvío 0,12–0,16; EE = desvío / sqrt(n semanas).
- H2: exceso neto anual con tracking error 25–35 %/año; EE = TE / sqrt(años).
Primero reproduce las cifras de la v3 §7.2 (≈ 330–360 semanas; 6,5–7 años) para validar la fórmula, y después las
calcula para 158, 160 y 274 semanas. Uso: python -B -I potencia_analitica.py"""
from statistics import NormalDist

N = NormalDist()


def pot(efecto, ee, alfa):
    return 1 - N.cdf(N.inv_cdf(1 - alfa) - efecto / ee)


def h1(n, ic, alfa):
    return [round(pot(ic, d / n ** 0.5, alfa), 2) for d in (0.16, 0.12)]


def h2(semanas, neto, alfa):
    anios = semanas / 52.1775
    return [round(pot(neto, te / anios ** 0.5, alfa), 2) for te in (0.35, 0.25)]


print("Validación contra la v3 §7.2 (n = 345 semanas para H1; 6,5–7 años para H2):")
print("  H1 IC 0,02, α 0,025:", h1(345, 0.02, 0.025), "(v3: 0,56–0,79)")
print("  H1 IC 0,02, α 0,05 :", h1(345, 0.02, 0.05), "(v3: 0,68–0,87)")
print("  H2 10 %/año, α 0,025, 6,5 años:", h2(6.5 * 52.1775, 0.10, 0.025), "· 7 años:", h2(7 * 52.1775, 0.10, 0.025), "(v3: 0,11–0,17)")
print("  H2 20 %/año, α 0,025, 6,75 años:", h2(6.75 * 52.1775, 0.20, 0.025), "(v3: 0,30–0,52)")
for n in (158, 160, 274):
    print(f"n = {n} semanas:")
    for alfa in (0.025, 0.05):
        print(f"  α {alfa}: H1 IC 0,02 → {h1(n, 0.02, alfa)} · H1 IC 0,03 → {h1(n, 0.03, alfa)} · "
              f"H2 10 %/año → {h2(n, 0.10, alfa)} · H2 20 %/año → {h2(n, 0.20, alfa)}")
