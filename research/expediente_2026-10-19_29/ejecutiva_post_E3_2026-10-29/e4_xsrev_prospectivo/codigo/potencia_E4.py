"""E4 · Potencia analítica SIN DATOS, con supuestos declarados [Hip, ninguno medido]:
desvío del IC diario de Spearman en ~100 monedas = 0,10 / 0,15 / 0,20; AR(1) del IC diario φ = 0 / 0,1; prueba unilateral
α = 0,025 (t > 1,96). Se informan, para cada horizonte prospectivo (180, 365, 540 días evaluables):
  - potencia para IC verdadero 0,01 / 0,02 / 0,03;
  - P(REFUTADA_TAMANO_RELEVANTE | IC = 0): cota superior 97,5 % < 0,01 (qué tan seguido el nulo cierra la pregunta);
  - el IC mínimo detectable con 80 %.
Uso: python3 -I -B potencia_E4.py"""
from statistics import NormalDist

N = NormalDist()
z = N.inv_cdf(0.975)
for dias in (180, 365, 540):
    print(f"=== {dias} días evaluables ===")
    for phi in (0.0, 0.1):
        for sd in (0.10, 0.15, 0.20):
            se = sd / dias ** 0.5 * ((1 + phi) / (1 - phi)) ** 0.5
            pot = {ic: round(1 - N.cdf(z - ic / se), 2) for ic in (0.01, 0.02, 0.03)}
            refuta = round(N.cdf(0.01 / se - z), 2)
            mde = (z + N.inv_cdf(0.8)) * se
            print(f"  φ={phi} sd={sd}: potencia {pot} · P(refutar tamaño ≥0,01 | IC=0) = {refuta} · IC mínimo con 80 % = {mde:.4f}")
