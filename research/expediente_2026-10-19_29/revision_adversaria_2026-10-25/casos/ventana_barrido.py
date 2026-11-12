"""Barrido del escenario de reversión con stops más estrechos: ¿alguna barra sin stop ni cierre al emparejar en la que el precio
cruza el nivel del stop cancelado? Mismo venue que registra; el venue rechaza el primer cierre de cada posición.
Uso: python -I ventana_barrido.py <árbol>"""
import pathlib, sys
arbol = pathlib.Path(sys.argv[1]).resolve(); sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
import tests.integration.test_engine_version_contract as g  # noqa: E402
import tia.backtest.engine as engine_module  # noqa: E402
from tia.backtest import BacktestConfig, BacktestEngine  # noqa: E402
from tia.core.config import ExecutionSimConfig  # noqa: E402
from tia.domain.enums import OrderType  # noqa: E402
from tia.domain.instruments import DEFAULT_UNIVERSE  # noqa: E402
from tia.strategy import library  # noqa: E402
from tia.strategy.library import TrendFollowingStrategy  # noqa: E402
engine_module.PaperExecutionProvider = g._Venue
for adx in (10.0, 15.0):
    for mult in (1.5, 2.0, 3.0, 4.0, 6.0):
        class _S(TrendFollowingStrategy):
            def __init__(self, a=adx, m=mult) -> None:
                super().__init__(adx_threshold=a, atr_stop_multiple=m)
        library.STRATEGY_REGISTRY["trend_following"] = _S
        g._Venue.reject_first_close, g._Venue.closes_are_ioc, g._Venue.last = True, False, None
        res = BacktestEngine(BacktestConfig(dataset="fixtures", timeframe="1h", warmup_bars=120, use_target=False,
                                            trail_atr_multiple=50.0, breakeven_after_r=50.0,
                                            execution=ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)),
                             DEFAULT_UNIVERSE, strategies=("trend_following",)).run(g.SERIES)
        rec = g._Venue.last.record
        motivos = {}
        for t in res.trades:
            motivos[t.exit_reason] = motivos.get(t.exit_reason, 0) + 1
        sin = [l for l in rec.looks if l.held != 0.0 and not any(g._protects(l.held, w) for w in l.working)]
        cruces = []
        for l in sin:
            stops = [s.stop_price for s in rec.sent if s.order_type is OrderType.STOP and s.bar < l.bar and s.held != 0.0]
            nivel = stops[-1] if stops else None; v = g.SERIES[l.bar]; larga = l.held > 0
            if nivel is not None and ((v.low <= nivel) if larga else (v.high >= nivel)):
                peor = v.low if larga else v.high
                cruces.append(f"barra {l.bar} pos {l.held:+.5f} nivel {nivel:.2f} {'low' if larga else 'high'} {peor:.2f} ({abs(peor-nivel)/nivel*1e4:.1f} bps más allá)")
        print(f"adx {adx:4} atr_stop {mult:3}: salidas {motivos} · cierres rechazados {rec.closes_rejected} · sin stop ni cierre al emparejar {len(sin)} · cruzan el nivel {len(cruces)} {cruces[:3]}")
