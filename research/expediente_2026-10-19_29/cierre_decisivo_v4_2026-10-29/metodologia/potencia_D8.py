"""D-8 · Potencia analítica SIN DATOS, con los supuestos declarados de la v3 §7.1 ([Hip, ninguno medido]):
H1: IC semanal con desvío 0,12–0,16; H2: tracking error 25–35 %/año (sensibilidad v3: 41–59 %/año); normal, unilateral.
Agrega lo que la v3 no reporta para 158 semanas:
  - curva de potencia por tamaño de efecto (H1: IC 0,01/0,02/0,03; H2: 5/10/20/30 %/año);
  - efecto mínimo detectable con 80 %;
  - el ajuste por autocorrelación AR(1) con φ = 0,1 (el de la calibración N9): factor de varianza (1+φ)/(1−φ);
  - P(ninguna rechaza | efecto) y su razón de verosimilitud frente al nulo: cuánto informa un resultado INSUFICIENTE.
Holm m = 2: la menor p se compara con 0,025 y la mayor con 0,05. P(RESPALDADA) ≤ P(H2 rechaza a 0,05).
Primero valida la fórmula reproduciendo la v3 §7.2. Uso: python3 -I -B potencia_D8.py"""
from statistics import NormalDist

N = NormalDist()
SEM_ANIO = 52.1775


def pot(efecto, ee, alfa):
    return 1 - N.cdf(N.inv_cdf(1 - alfa) - efecto / ee)


def ee_h1(n, sd, phi=0.0):
    return sd / n ** 0.5 * ((1 + phi) / (1 - phi)) ** 0.5


def ee_h2(semanas, te):
    return te / (semanas / SEM_ANIO) ** 0.5


def mde(ee, alfa, potencia=0.8):
    return (N.inv_cdf(1 - alfa) + N.inv_cdf(potencia)) * ee


def r(x):
    return round(x, 2)


print("Validación (v3 §7.2, 345 semanas, 6,75 años): H1 IC 0,02 α 0,025 →", [r(pot(0.02, ee_h1(345, s), 0.025)) for s in (0.16, 0.12)],
      "(v3 0,56–0,79; la v3 usa un EE más conservador) · H2 10 %/año α 0,025 →",
      [r(pot(0.10, ee_h2(6.75 * SEM_ANIO, te), 0.025)) for te in (0.35, 0.25)], "(v3 0,11–0,17)")
for semanas in (158, 160):
    print(f"\n=== {semanas} semanas ({semanas / SEM_ANIO:.2f} años) ===")
    for phi in (0.0, 0.1):
        for alfa in (0.025, 0.05):
            fila = {ic: [r(pot(ic, ee_h1(semanas, s, phi), alfa)) for s in (0.16, 0.12)] for ic in (0.01, 0.02, 0.03)}
            print(f"H1 φ={phi} α={alfa}: potencia por IC {fila} · MDE80 IC = "
                  f"{mde(ee_h1(semanas, 0.12, phi), alfa):.4f}–{mde(ee_h1(semanas, 0.16, phi), alfa):.4f}")
    for alfa in (0.025, 0.05):
        fila = {f"{int(e * 100)}%": [r(pot(e, ee_h2(semanas, te), alfa)) for te in (0.35, 0.25)] for e in (0.05, 0.10, 0.20, 0.30)}
        sens = [r(pot(0.10, ee_h2(semanas, te), alfa)) for te in (0.59, 0.41)]
        print(f"H2 α={alfa}: potencia por exceso neto {fila} · con TE 41–59 %: 10 %/año → {sens} · MDE80 = "
              f"{mde(ee_h2(semanas, 0.25), alfa):.0%}–{mde(ee_h2(semanas, 0.35), alfa):.0%} por año")
    print("Cota P(RESPALDADA) ≤ P(H2 rechaza a 0,05): 10 %/año →", [r(pot(0.10, ee_h2(semanas, te), 0.05)) for te in (0.35, 0.25)],
          "· 20 %/año →", [r(pot(0.20, ee_h2(semanas, te), 0.05)) for te in (0.35, 0.25)])
    # Cuánto informa un INSUFICIENTE (ninguna rechaza), aproximando independencia entre H1 y H2 y el umbral 0,025 de Holm
    for ic, ex in ((0.02, 0.10), (0.03, 0.20)):
        for s, te in ((0.16, 0.35), (0.12, 0.25)):
            p1, p2 = pot(ic, ee_h1(semanas, s), 0.025), pot(ex, ee_h2(semanas, te), 0.025)
            p_ninguna = (1 - p1) * (1 - p2)
            print(f"  Efecto IC {ic} y {int(ex * 100)} %/año (desvío {s}, TE {te}): P(ninguna rechaza) ≈ {p_ninguna:.2f};"
                  f" bajo el nulo ≈ {(1 - 0.025) ** 2:.2f}; razón de verosimilitud ≈ {p_ninguna / (1 - 0.025) ** 2:.2f}")
