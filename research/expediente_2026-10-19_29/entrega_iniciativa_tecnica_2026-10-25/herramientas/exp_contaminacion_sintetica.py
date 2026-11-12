"""TI · Experimento: ¿puede la deriva de los escenarios sintéticos hacer «operable» un bucket del motor de EV del vivo?

Corre corridas COMPLETAS del motor de escenarios del repositorio (RuntimeEngine, como las corridas de demo/entrenamiento
de la API, que persisten sus resultados con market_data="synthetic"), toma los resultados que registró su estimador y los
entrega al motor de EV con la configuración del vivo (umbral y razón de costos de settings.live), filtrados con la regla
de admisión del vivo (LiveRuntime._evidence_admitted: «legacy» admite todo, «real_only» solo market_data == "real").
Costos de la evaluación: los del cierre con taker por defecto (comisión 2×7,5 bps) + deslizamiento base 2×2 bps; sin
spread ni impacto (cota favorable a operar: si con esto no aprueba, con más costos tampoco).
Esperado de un sistema seguro (fijado antes): bajo ninguna política un resultado sintético vuelve operable un bucket
para el vivo. Uso: python -I exp_contaminacion_sintetica.py <árbol> <salida.json>"""
import asyncio
import json
import statistics
import sys
from pathlib import Path

arbol, salida = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(arbol / "packages/tia/src")]
from tia.core.config import Environment, settings_for_env  # noqa: E402
from tia.domain.enums import Direction, MarketRegime  # noqa: E402
from tia.economics.costs import TradeCosts  # noqa: E402
from tia.economics.expected_value import EdgeEstimator, ExpectedValueEngine, Outcome  # noqa: E402
from tia.runtime import RuntimeConfig, RuntimeEngine  # noqa: E402

ESCENARIOS = ("trend_up", "trend_down")
SEMILLAS = tuple(range(1, 7))


async def corrida(escenario, semilla):
    eng = RuntimeEngine(settings_for_env(Environment.DEMO),
                        RuntimeConfig(scenario=escenario, seed=semilla, bar_interval_seconds=0.0, initial_capital=10_000.0,
                                      llm_enabled=False, news_enabled=False))
    await eng.start()
    for _ in range(80_000):
        await asyncio.sleep(0)
        if not eng.is_running:
            break
    await eng.stop()
    return eng._edges.buckets()


def admitido(politica, market_data):
    return True if politica == "legacy" else market_data == "real"


async def main():
    s = settings_for_env(Environment.PRODUCTION) if hasattr(Environment, "PRODUCTION") else settings_for_env(Environment.DEMO)
    umbral, razon = s.live.ev_threshold_bps, s.live.max_cost_ratio
    taker, slip = s.execution.taker_fee_bps, s.execution.base_slippage_bps
    costos = TradeCosts(fee_bps=2 * taker, spread_bps=0.0, slippage_bps=2 * slip, latency_bps=0.0, impact_bps=0.0, notional=1.0)
    resultados = []
    for esc in ESCENARIOS:
        for sem in SEMILLAS:
            for (reg, dire, banda), xs in (await corrida(esc, sem)).items():
                for x in xs:
                    resultados.append({"escenario": esc, "semilla": sem, "regimen": reg, "direccion": dire,
                                       "banda": list(banda), "bruto_bps": x})
    buckets = {}
    for r in resultados:
        buckets.setdefault((r["regimen"], r["direccion"], tuple(r["banda"])), []).append(r["bruto_bps"])
    resumen = []
    for politica in ("legacy", "real_only"):
        est = EdgeEstimator()
        for r in resultados:
            if admitido(politica, "synthetic"):
                est.record(Outcome(regime=MarketRegime(r["regimen"]), direction=Direction(r["direccion"]),
                                   confidence=(r["banda"][0] + min(r["banda"][1], 1.0)) / 2, net_return_bps=r["bruto_bps"],
                                   gross_return_bps=r["bruto_bps"], market_data="synthetic"))
        ev = ExpectedValueEngine(est, threshold_bps=umbral, max_cost_ratio=razon)
        for (reg, dire, banda), xs in sorted(buckets.items()):
            r = ev.evaluate(regime=MarketRegime(reg), direction=Direction(dire), confidence=(banda[0] + min(banda[1], 1.0)) / 2,
                            costs=costos)
            resumen.append({"politica": politica, "regimen": reg, "direccion": dire, "banda": list(banda), "n": len(xs),
                            "media_bruta_bps": round(statistics.fmean(xs), 2),
                            "ee_bps": round(statistics.stdev(xs) / len(xs) ** 0.5, 2) if len(xs) > 1 else None,
                            "estimacion_ajustada_bps": round(r.gross_edge_bps, 2), "costos_bps": costos.total_bps,
                            "operable": r.is_tradeable, "razon": (r.reason or "")[:160]})
    out = {"diseno": __doc__.split("Uso:")[0].strip(), "umbral_bps": umbral, "razon_costos": razon,
           "escenarios": ESCENARIOS, "semillas": SEMILLAS, "operaciones_sinteticas": len(resultados), "buckets": resumen}
    salida.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    for b in resumen:
        if b["n"] >= 10:
            print(json.dumps(b, ensure_ascii=False))


asyncio.run(main())
