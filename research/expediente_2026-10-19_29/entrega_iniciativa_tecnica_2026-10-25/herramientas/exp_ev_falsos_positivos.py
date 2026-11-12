"""TI · Experimento: ¿cuántas veces aprueba el motor de EV un bucket SIN ventaja? (Hipótesis nula: retorno bruto medio 0.)

Usa las clases REALES del repositorio (EdgeEstimator, ExpectedValueEngine, TradeCosts); los retornos son sintéticos y el
supuesto se declara: normales i.i.d. (y una variante t de Student con 3 g.l., colas gruesas, reescalada a la misma σ).
No se usa ningún dato de mercado. Diseño fijado ANTES de correr:

Parte 1 (estática): para σ ∈ {50,100,200} bps por operación, costo de ida y vuelta c ∈ {10,20} bps y n ∈ {30,60,120}
muestras en el bucket, se mide P(aprobado) bajo H0 (μ=0) y la potencia bajo H1 (μ = c + umbral + 10 bps), con 5.000
réplicas por celda y la regla actual (umbral 5 bps, razón de costos 0,6, encogimiento 1 EE). Se informa también
P(≥1 de K=10 buckets aprobado), que es lo que importa con ~10 buckets con datos (regímenes × direcciones × bandas).

Parte 2 (secuencial, lo que de verdad cuesta): un bucket arranca con n0=30 muestras de exploración bajo H0 y enfrenta
T=300 oportunidades (1.000 réplicas); opera cuando el motor aprueba y cada operación agrega su resultado al bucket (como en el vivo).
Se mide: fracción de réplicas que llegan a operar, operaciones tomadas y pérdida neta acumulada (bps de nocional),
para la regla actual y dos alternativas implementadas FUERA del repositorio (encogimiento z=2,33 —unilateral 1 %— y
z de Bonferroni para K=10 a 5 %, z=2,58), más la potencia secuencial bajo H1.

Uso: python -I exp_ev_falsos_positivos.py <árbol> <salida.json>"""
import json
import math
import random
import sys
import time
from pathlib import Path

arbol, salida = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(arbol / "packages/tia/src")]
from tia.domain.enums import Direction, MarketRegime  # noqa: E402
from tia.economics.costs import TradeCosts  # noqa: E402
from tia.economics.expected_value import EdgeEstimator, ExpectedValueEngine, Outcome  # noqa: E402

UMBRAL, RAZON = 5.0, 0.6
REG, DIR, CONF = MarketRegime.TRENDING_UP, Direction.LONG, 0.75


def costos(c):
    return TradeCosts(fee_bps=c, spread_bps=0.0, slippage_bps=0.0, latency_bps=0.0, impact_bps=0.0, notional=1.0)


def muestra(rnd, mu, sigma, colas):
    if colas == "t3":  # t de Student con 3 g.l. reescalada a varianza sigma²: var(t3) = 3
        z = rnd.gauss(0, 1) / math.sqrt(sum(rnd.gauss(0, 1) ** 2 for _ in range(3)) / 3)
        return mu + sigma * z / math.sqrt(3)
    return rnd.gauss(mu, sigma)


def outcome(gross):
    return Outcome(regime=REG, direction=DIR, confidence=CONF, net_return_bps=gross, fees_bps=0.0, gross_return_bps=gross)


def aprueba_repo(samples, c):
    est = EdgeEstimator()
    est.record_many([outcome(g) for g in samples])
    ev = ExpectedValueEngine(est, threshold_bps=UMBRAL, max_cost_ratio=RAZON)
    return ev.evaluate(regime=REG, direction=DIR, confidence=CONF, costs=costos(c)).is_tradeable


def aprueba_z(samples, c, z):
    n = len(samples)
    if n < 30:
        return False
    m = sum(samples) / n
    var = sum((x - m) ** 2 for x in samples) / (n - 1)
    adj = max(0.0, m - z * math.sqrt(var / n))
    return adj > 0 and adj - c >= UMBRAL and c / adj <= RAZON


def parte1(rnd, reps):
    filas = []
    for colas in ("normal", "t3"):
        for sigma in (50.0, 100.0, 200.0):
            if colas == "t3" and sigma != 100.0:
                continue
            for c in (10.0, 20.0):
                for n in (30, 60, 120):
                    fila = {"colas": colas, "sigma_bps": sigma, "costo_bps": c, "n": n}
                    for nombre, mu in (("H0", 0.0), ("H1", c + UMBRAL + 10.0)):
                        ok = sum(aprueba_repo([muestra(rnd, mu, sigma, colas) for _ in range(n)], c) for _ in range(reps))
                        fila[f"P_aprobado_{nombre}"] = ok / reps
                    fila["P_al_menos_1_de_10_H0"] = 1 - (1 - fila["P_aprobado_H0"]) ** 10
                    filas.append(fila)
                    print(json.dumps(fila))
    return filas


def parte2(rnd, reps, sigma=100.0, c=20.0, n0=30, T=500):
    reglas = {"repo_1EE": None, "z_2.33": 2.33, "z_2.58_bonferroni_K10": 2.58}
    out = {}
    for hip, mu in (("H0", 0.0), ("H1", c + UMBRAL + 10.0)):
        for nombre, z in reglas.items():
            operaron = tomadas = 0
            neto_total = []
            for _ in range(reps):
                s = [muestra(rnd, mu, sigma, "normal") for _ in range(n0)]
                k = neto = 0.0
                est = EdgeEstimator()
                est.record_many([outcome(g) for g in s])
                ev = ExpectedValueEngine(est, threshold_bps=UMBRAL, max_cost_ratio=RAZON)
                for _t in range(T):
                    ok = (ev.evaluate(regime=REG, direction=DIR, confidence=CONF, costs=costos(c)).is_tradeable
                          if z is None else aprueba_z(s, c, z))
                    if ok:
                        g = muestra(rnd, mu, sigma, "normal")
                        s.append(g)
                        est.record(outcome(g))
                        k += 1
                        neto += g - c
                operaron += k > 0
                tomadas += k
                neto_total.append(neto)
            neto_total.sort()
            fila = {"hipotesis": hip, "regla": nombre, "replicas": reps, "frac_que_opera": operaron / reps,
                    "operaciones_medias": tomadas / reps, "neto_medio_bps_por_replica": sum(neto_total) / reps,
                    "neto_p05_bps": neto_total[int(0.05 * reps)], "neto_p50_bps": neto_total[reps // 2]}
            out[f"{hip}/{nombre}"] = fila
            print(json.dumps(fila))
    return out


t0 = time.time()
rnd = random.Random(20261025)
res = {"diseno": __doc__.split("Uso:")[0].strip(), "semilla": 20261025, "umbral_bps": UMBRAL, "razon_costos": RAZON,
       "parte1": parte1(rnd, 5_000), "parte2": parte2(rnd, 1_000, T=300), "segundos": None}
res["segundos"] = round(time.time() - t0, 1)
salida.write_text(json.dumps(res, indent=1, ensure_ascii=False))
