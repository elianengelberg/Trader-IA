"""Falsos positivos y potencia de la guarda (solo mide): corre los 5 escenarios de la guarda con otras semillas y otros
datos sobre un árbol, con las MISMAS comprobaciones del archivo de la guarda, y registra cuáles saltan y qué
precondiciones no se cumplen. Uso: python robustez_guarda.py <árbol> <salida.json> <semilla_desde> <semilla_hasta>"""
import asyncio, json, sys, pathlib
raiz = pathlib.Path(sys.argv[1]); sys.path.insert(0, str(raiz / "packages/tia/src")); sys.path.insert(0, str(raiz / "tests/integration"))
import test_engine_version_contract as g
from tia.backtest import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig
from tia.data.providers.csv_replay import CsvReplayProvider
from tia.domain.instruments import DEFAULT_UNIVERSE
from tia.domain.enums import OrderType
import tia.backtest.engine as engine_module

prov = CsvReplayProvider(raiz / "data/fixtures")
DATOS = {"BTC-USD_1h": ("1h", asyncio.run(prov.get_candles("BTC-USD", "1h", limit=700))),
         "BTC-USD_1m": ("1m", asyncio.run(prov.get_candles("BTC-USD", "1m", limit=700))),
         "ETH-USD_1m": ("1m", asyncio.run(prov.get_candles("ETH-USD", "1m", limit=700)))}
T = g.TIME_STOP_BARS
ESC = {  # nombre: (venue, config, comprobaciones, precondición)
    "d1_cierre_rechazado": (dict(reject_first_close=True), dict(max_holding_bars=T),
        ["dead_orders_sent_again", "positions_held_too_long", "uncovered_streaks"], lambda r: r.closes_rejected > 0),
    "d2_stop_sigue": ({}, {}, ["stop_moves_wrong", "stop_moves_none", "dead_orders_sent_again", "uncovered_streaks"], lambda r: True),
    "d3_parciales": ({}, dict(partial=0.9), ["growth_after_close", "entries_filling_a_later_position", "dead_orders_sent_again",
        "closes_without_reduce_only", "uncovered_streaks"],
        lambda r: any(f.after != 0.0 and not f.reduce_only and f.order_type is not OrderType.STOP for f in r.fills)),
    "d3_ioc": (dict(closes_are_ioc=True), dict(partial=0.9, max_holding_bars=T), ["uncovered_streaks", "growth_after_close",
        "dead_orders_sent_again", "closes_without_reduce_only"], lambda r: r.closes_expired_with_position > 0),
    "todo_junto": (dict(reject_first_close=True), dict(reject=0.3, partial=0.6, entry_order_type="limit", max_holding_bars=T),
        ["dead_orders_sent_again", "growth_after_close", "entries_filling_a_later_position", "closes_without_reduce_only"], lambda r: True),
}

def chequear(nombre, r):
    if nombre == "stop_moves_wrong": return g.stop_moves(r)[1]
    if nombre == "stop_moves_none": return [] if g.stop_moves(r)[0] else ["ningún stop se movió"]
    if nombre == "positions_held_too_long": return g.positions_held_too_long(r, T + g.TIME_STOP_SLACK)
    return getattr(g, nombre)(r)

def correr(tf, serie, seed, venue, cfg):
    engine_module.PaperExecutionProvider = g._Venue
    g._Venue.reject_first_close = venue.get("reject_first_close", False); g._Venue.closes_are_ioc = venue.get("closes_are_ioc", False); g._Venue.last = None
    cfg = dict(cfg); reject = cfg.pop("reject", 0.0); partial = cfg.pop("partial", 0.0)
    e = BacktestEngine(BacktestConfig(dataset="fixtures", timeframe=tf, warmup_bars=120, seed=seed,
                       execution=ExecutionSimConfig(reject_probability=reject, partial_fill_probability=partial), **cfg), DEFAULT_UNIVERSE)
    res = e.run(serie)
    return res, g._Venue.last.record

out = {"arbol": str(raiz), "filas": []}
for dn, (tf, serie) in DATOS.items():
    for seed in range(int(sys.argv[3]), int(sys.argv[4]) + 1):
        for en, (venue, cfg, checks, pre) in ESC.items():
            try:
                res, r = correr(tf, serie, seed, venue, cfg)
            except Exception as exc:
                out["filas"].append({"datos": dn, "semilla": seed, "escenario": en, "error": f"{type(exc).__name__}: {exc}"[:300]}); continue
            saltan = {c: chequear(c, r)[:2] for c in checks}
            out["filas"].append({"datos": dn, "semilla": seed, "escenario": en, "version": getattr(res.conditions, "engine_version", None),
                                 "posiciones": max((f.episode for f in r.fills), default=0), "precondicion": bool(pre(r)),
                                 "saltan": {c: v for c, v in saltan.items() if v}})
json.dump(out, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
print("filas", len(out["filas"]))
