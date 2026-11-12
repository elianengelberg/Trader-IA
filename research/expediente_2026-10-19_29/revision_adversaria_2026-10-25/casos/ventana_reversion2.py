"""El escenario de reversión de las pruebas de higiene de 01 (estrategia «paciente»: stop ancho, sin objetivo, salidas por
señal invertida), con el venue que REGISTRA de la guarda: qué hay trabajando al EMPEZAR cada barra (cuando el venue empareja).
Variante 1: el venue rechaza el primer cierre de cada posición. Variante 2: sin rechazos (control).
Uso: python -I ventana_reversion2.py <árbol> <salida.json>"""
import json, pathlib, sys
arbol = pathlib.Path(sys.argv[1]).resolve(); sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
import tests.integration.test_engine_version_contract as g  # noqa: E402
import tia.backtest.engine as engine_module  # noqa: E402
from tia.backtest import BacktestConfig, BacktestEngine  # noqa: E402
from tia.core.config import ExecutionSimConfig  # noqa: E402
from tia.domain.enums import OrderType  # noqa: E402
from tia.domain.instruments import DEFAULT_UNIVERSE  # noqa: E402
from tia.strategy import library  # noqa: E402
from tia.strategy.library import TrendFollowingStrategy  # noqa: E402

class _Paciente(TrendFollowingStrategy):
    def __init__(self) -> None:
        super().__init__(adx_threshold=10.0, atr_stop_multiple=12.0)

library.STRATEGY_REGISTRY["trend_following"] = _Paciente
engine_module.PaperExecutionProvider = g._Venue
filas = []
for rechazar in (True, False):
    g._Venue.reject_first_close, g._Venue.closes_are_ioc, g._Venue.last = rechazar, False, None
    res = BacktestEngine(BacktestConfig(dataset="fixtures", timeframe="1h", warmup_bars=120, use_target=False,
                                        trail_atr_multiple=50.0, breakeven_after_r=50.0,
                                        execution=ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)),
                         DEFAULT_UNIVERSE, strategies=("trend_following",)).run(g.SERIES)
    rec = g._Venue.last.record
    motivos = {}
    for t in res.trades:
        motivos[t.exit_reason] = motivos.get(t.exit_reason, 0) + 1
    sin, casos = [l for l in rec.looks if l.held != 0.0 and not any(g._protects(l.held, w) for w in l.working)], []
    for l in sin:
        ant = [s for s in rec.sent if s.bar == l.bar - 1]
        canc = [c for c in rec.cancels if c.bar == l.bar - 1]
        stops = [s.stop_price for s in rec.sent if s.order_type is OrderType.STOP and s.bar < l.bar and s.held != 0.0]
        nivel = stops[-1] if stops else None; v = g.SERIES[l.bar]; larga = l.held > 0
        cruza = nivel is not None and ((v.low <= nivel) if larga else (v.high >= nivel))
        sig = [s for s in rec.sent if s.bar == l.bar]
        casos.append({"barra": l.bar, "pos": l.held, "nivel_stop": nivel, "low": v.low, "high": v.high, "cruza_el_nivel": cruza,
                      "barra_anterior_envio": [f"{s.order_type.value}{'/ro' if s.reduce_only else ''}" for s in ant],
                      "barra_anterior_cancelo": [c.order_type.value for c in canc],
                      "esta_barra_envio": [f"{s.order_type.value}{'/ro' if s.reduce_only else ''}" for s in sig]})
    filas.append({"rechaza_primer_cierre": rechazar, "version": res.conditions.engine_version, "salidas": motivos,
                  "cierres_rechazados": rec.closes_rejected, "barras_sin_stop_ni_cierre_al_emparejar": len(sin),
                  "de_ellas_el_precio_cruza_el_nivel_del_stop": sum(c["cruza_el_nivel"] for c in casos),
                  "rachas_mayores_a_1": len(g.uncovered_streaks(rec, 1)), "casos": casos})
    print(f"rechaza_primer_cierre={rechazar}: v{res.conditions.engine_version} salidas {motivos} · cierres rechazados {rec.closes_rejected} · "
          f"barras sin stop ni cierre al emparejar: {len(sin)} (el precio cruza el nivel: {sum(c['cruza_el_nivel'] for c in casos)}; rachas >1: {len(g.uncovered_streaks(rec, 1))})")
    for c in casos[:8]:
        print(f"   barra {c['barra']}: pos {c['pos']:+.6f} nivel {c['nivel_stop']} low {c['low']:.2f} high {c['high']:.2f} cruza={c['cruza_el_nivel']} · "
              f"barra anterior envió {c['barra_anterior_envio']} canceló {c['barra_anterior_cancelo']} · esta barra envía {c['esta_barra_envio']}")
json.dump(filas, open(sys.argv[2], "w"), indent=1, default=str)
