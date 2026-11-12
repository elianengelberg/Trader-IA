"""TI · Experimento complementario: ¿cuánto de la baja potencia del motor de EV viene de la razón de costos (0,6)?
Mismo diseño que exp_ev_falsos_positivos.py parte 1 (clases reales, retornos normales i.i.d. sintéticos, 5.000 réplicas por
celda), σ=100 bps, c ∈ {10,20}, n ∈ {30,120}, razón ∈ {0,6 (actual), 1,0 (sin el límite efectivo)}. Fijado antes de correr.
Uso: python -I exp_ev_razon_costos.py <árbol> <salida.json>"""
import json, random, sys
from pathlib import Path
arbol, salida = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(arbol / "packages/tia/src")]
from tia.domain.enums import Direction, MarketRegime  # noqa: E402
from tia.economics.costs import TradeCosts  # noqa: E402
from tia.economics.expected_value import EdgeEstimator, ExpectedValueEngine, Outcome  # noqa: E402
REG, DIR, CONF, UMBRAL = MarketRegime.TRENDING_UP, Direction.LONG, 0.75, 5.0
rnd = random.Random(20261026)
def aprueba(samples, c, razon):
    est = EdgeEstimator()
    est.record_many([Outcome(regime=REG, direction=DIR, confidence=CONF, net_return_bps=g, gross_return_bps=g) for g in samples])
    ev = ExpectedValueEngine(est, threshold_bps=UMBRAL, max_cost_ratio=razon)
    costs = TradeCosts(fee_bps=c, spread_bps=0.0, slippage_bps=0.0, latency_bps=0.0, impact_bps=0.0, notional=1.0)
    return ev.evaluate(regime=REG, direction=DIR, confidence=CONF, costs=costs).is_tradeable
filas = []
for c in (10.0, 20.0):
    for n in (30, 120):
        for razon in (0.6, 1.0):
            f = {"sigma_bps": 100.0, "costo_bps": c, "n": n, "razon": razon}
            for h, mu in (("H0", 0.0), ("H1", c + UMBRAL + 10.0)):
                f[f"P_aprobado_{h}"] = sum(aprueba([rnd.gauss(mu, 100.0) for _ in range(n)], c, razon) for _ in range(5000)) / 5000
            filas.append(f); print(json.dumps(f))
salida.write_text(json.dumps({"diseno": __doc__.split("Uso:")[0].strip(), "semilla": 20261026, "filas": filas}, indent=1, ensure_ascii=False))
