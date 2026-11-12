"""Caso dirigido: SOLO salidas por stop o por señal invertida (sin objetivo ni stop por tiempo) y el venue rechaza el primer
cierre de cada posición. Por inspección (engine.py, paso 3): el cierre por reversión se pide DESPUÉS de sincronizar el stop,
cancela el stop y, si se rechaza, no hay stop hasta el sync de la barra siguiente, que corre DESPUÉS del emparejamiento.
Uso: python -I ventana_reversion.py <árbol> <salida.json>"""
import json, pathlib, sys
arbol = pathlib.Path(sys.argv[1]).resolve(); sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
import tests.integration.test_engine_version_contract as g  # noqa: E402
import tia.backtest.engine as engine_module  # noqa: E402
from tia.backtest import BacktestConfig, BacktestEngine  # noqa: E402
from tia.core.config import ExecutionSimConfig  # noqa: E402
from tia.domain.enums import OrderType  # noqa: E402
from tia.domain.instruments import DEFAULT_UNIVERSE  # noqa: E402
engine_module.PaperExecutionProvider = g._Venue
filas = []
for usar_objetivo in (False, True):
    g._Venue.reject_first_close, g._Venue.closes_are_ioc, g._Venue.last = True, False, None
    res = BacktestEngine(BacktestConfig(dataset="fixtures", timeframe="1h", warmup_bars=120, use_target=usar_objetivo,
                                        max_holding_bars=0, exit_on_signal_reversal=True,
                                        execution=ExecutionSimConfig(reject_probability=0.0, partial_fill_probability=0.0)),
                         DEFAULT_UNIVERSE).run(g.SERIES)
    rec = g._Venue.last.record
    razones = {k: v for k, v in (getattr(res, "exit_reasons", None) or {}).items()} if hasattr(res, "exit_reasons") else None
    sin = [l for l in rec.looks if l.held != 0.0 and not any(g._protects(l.held, w) for w in l.working)]
    casos = []
    for l in sin:
        ant = [s for s in rec.sent if s.bar == l.bar - 1]
        stops = [s.stop_price for s in rec.sent if s.order_type is OrderType.STOP and s.bar < l.bar and s.held != 0.0]
        nivel = stops[-1] if stops else None
        v = g.SERIES[l.bar]; larga = l.held > 0
        cruza = nivel is not None and ((v.low <= nivel) if larga else (v.high >= nivel))
        casos.append({"barra": l.bar, "pos": l.held, "nivel": nivel, "low": v.low, "high": v.high, "cruza": cruza,
                      "exceso_bps": round(abs((v.low if larga else v.high) - nivel) / nivel * 1e4, 1) if cruza else None,
                      "barra_anterior": [f"{s.order_type.value}{'/ro' if s.reduce_only else ''}" for s in ant]})
    trades = getattr(res, "trades", None) or []
    motivos = {}
    for t in trades:
        k = getattr(t, "exit_reason", "?"); motivos[k] = motivos.get(k, 0) + 1
    filas.append({"use_target": usar_objetivo, "version": res.conditions.engine_version, "cierres_rechazados": rec.closes_rejected,
                  "motivos_de_salida": motivos, "barras_sin_stop_ni_cierre": len(sin),
                  "cruzan_el_nivel": sum(c["cruza"] for c in casos), "rachas_>1": len(g.uncovered_streaks(rec, 1)), "casos": casos})
    print(f"use_target={usar_objetivo}: v{res.conditions.engine_version} cierres rechazados {rec.closes_rejected} · salidas {motivos} · "
          f"barras sin stop ni cierre {len(sin)} (cruzan el nivel: {sum(c['cruza'] for c in casos)}; rachas >1 barra: {len(g.uncovered_streaks(rec, 1))})")
    for c in casos[:6]:
        print(f"   barra {c['barra']}: pos {c['pos']:+.6f} nivel {c['nivel']} low {c['low']} high {c['high']} cruza={c['cruza']} exceso={c['exceso_bps']} · anterior {c['barra_anterior']}")
json.dump(filas, open(sys.argv[2], "w"), indent=1, default=str)
