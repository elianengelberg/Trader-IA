"""¿Queda una posición SIN stop ni cierre trabajando al empezar una barra (cuando el venue empareja), y esa barra cruza el
nivel de stop que la pierna tenía? Usa el venue que registra de la guarda 05v2 (solo observa) sobre el motor del árbol dado.
Escenarios: cierres rechazados (el primero de cada posición), rechazos aleatorios, con y sin salida por señal invertida.
Uso: python -I ventana_sin_stop.py <árbol> <salida.json>"""
import json
import pathlib
import sys

arbol = pathlib.Path(sys.argv[1]).resolve()
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
import tests.integration.test_engine_version_contract as g  # noqa: E402
import tia.backtest.engine as engine_module  # noqa: E402
from tia.backtest import BacktestConfig, BacktestEngine  # noqa: E402
from tia.core.config import ExecutionSimConfig  # noqa: E402
from tia.domain.enums import OrderType, Side  # noqa: E402
from tia.domain.instruments import DEFAULT_UNIVERSE  # noqa: E402

engine_module.PaperExecutionProvider = g._Venue


def correr(nombre, *, reject_first_close=False, reject=0.0, partial=0.0, semilla=None, **cfg):
    g._Venue.reject_first_close, g._Venue.closes_are_ioc, g._Venue.last = reject_first_close, False, None
    ex = dict(reject_probability=reject, partial_fill_probability=partial)
    if semilla is not None:
        ex["seed"] = semilla
    try:
        ejec = ExecutionSimConfig(**ex)
    except TypeError:
        ex.pop("seed", None); ejec = ExecutionSimConfig(**ex)
    res = BacktestEngine(BacktestConfig(dataset="fixtures", timeframe="1h", warmup_bars=120, execution=ejec, **cfg),
                         DEFAULT_UNIVERSE).run(g.SERIES)
    rec = g._Venue.last.record
    ultimo_stop = {}  # episodio -> nivel del último stop enviado
    for s in rec.sent:
        if s.order_type is OrderType.STOP and s.stop_price is not None and s.held != 0.0:
            ultimo_stop.setdefault(s.episode, []).append((s.bar, s.stop_price))
    ventanas = []
    for look in rec.looks:
        if look.held != 0.0 and not any(g._protects(look.held, w) for w in look.working):
            vela = g.SERIES[look.bar]
            previos = [s for s in rec.sent if s.bar == look.bar - 1]
            # nivel vigente: el último stop enviado antes de esta barra en la posición abierta
            niveles = [p for ep in ultimo_stop.values() for (b, p) in ep if b < look.bar]
            nivel = niveles[-1] if niveles else None
            larga = look.held > 0
            cruza = nivel is not None and ((vela.low <= nivel) if larga else (vela.high >= nivel))
            exceso_bps = None
            if cruza:
                peor = vela.low if larga else vela.high
                exceso_bps = round(abs(peor - nivel) / nivel * 1e4, 1)
            ventanas.append({"barra": look.bar, "posicion": look.held, "nivel_stop_previo": nivel,
                             "low": vela.low, "high": vela.high, "cruza_el_nivel": cruza, "exceso_bps": exceso_bps,
                             "enviado_barra_anterior": [f"{s.order_type.value}{'/ro' if s.reduce_only else ''} {s.side.value}"
                                                        for s in previos],
                             "cierre_rechazado_antes": any(g._is_close(s) for s in previos)})
    return {"escenario": nombre, "version": res.conditions.engine_version, "barras": len(rec.looks),
            "cierres_rechazados": rec.closes_rejected, "ventanas_sin_proteccion": len(ventanas),
            "de_ellas_cruzan_el_nivel_del_stop": sum(v["cruza_el_nivel"] for v in ventanas),
            "rachas_mayores_a_1_barra": len(g.uncovered_streaks(rec, 1)),
            "detalle": ventanas[:12]}


salida = [
    correr("cierres_rechazados_con_reversion", reject_first_close=True),
    correr("cierres_rechazados_sin_reversion", reject_first_close=True, exit_on_signal_reversal=False),
    correr("rechazo_aleatorio_30", reject=0.3),
    correr("rechazo_aleatorio_30_con_cierre_rechazado", reject=0.3, reject_first_close=True, partial=0.5),
    correr("sin_rechazos", ),
]
json.dump(salida, open(sys.argv[2], "w"), indent=1, default=str)
for s in salida:
    print(f"{s['escenario']:44s} v{s['version']} cierres_rechazados={s['cierres_rechazados']:3d} "
          f"ventanas_sin_proteccion={s['ventanas_sin_proteccion']:3d} cruzan_el_stop={s['de_ellas_cruzan_el_nivel_del_stop']}")
    for v in s["detalle"][:4]:
        print(f"    barra {v['barra']}: pos {v['posicion']:+.6f} nivel {v['nivel_stop_previo']} low {v['low']} high {v['high']} "
              f"cruza={v['cruza_el_nivel']} exceso={v['exceso_bps']} bps · barra anterior envió {v['enviado_barra_anterior']}")
