"""Simulación integral de extremo a extremo (Fase K), en papel: motor de ejecución de papel real (PaperExecutionProvider,
emparejamiento por barra), LiveRuntime real, persistencia real en SQLite (los mismos repositorios que AppState) y
reinicio por reconstrucción del diario. Fallas deterministas inyectadas con semilla. Ninguna red, ningún venue real.

Por escenario se registra: estado inicial, eventos, órdenes, transiciones de estado, protección en cada emparejamiento
(barra), escrituras (programadas/confirmadas/perdidas y filas en la base), errores, estado final, inconsistencias y
esperado vs observado. El «esperado» es el comportamiento seguro fijado ANTES de correr; se corre igual sobre la base
(A+B+03) y sobre el candidato para comparar.
Uso: python -I simulacion_integral.py <árbol> <salida.json> <semilla>"""
import asyncio
import json
import random
import shutil
import sys
import tempfile
import traceback
from datetime import UTC, datetime
from pathlib import Path

arbol, salida, semilla = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
from sqlalchemy import text  # noqa: E402

from tests.integration.test_account_restore import (  # noqa: E402
    CAPITAL, SYMBOL, build, engine_for, open_position, rebuild, register_run,
)
from tests.integration.test_live_runtime import FakeMarketData, _seed_every_bucket, live_settings  # noqa: E402
from tia.core.clock import SimulatedClock  # noqa: E402
from tia.core.errors import ExecutionError, ProviderUnavailableError, ReconciliationError  # noqa: E402
from tia.domain.enums import OrderState, OrderType, Side, TimeInForce  # noqa: E402
from tia.domain.orders import OrderIntent  # noqa: E402
from tia.persistence import (  # noqa: E402
    BacktestRepository, Database, EventRepository, FillRepository, IncidentRepository, OrderRepository, RunRepository,
)
from tests.integration.test_backtest_provenance import _row, _run  # noqa: E402  (corre asyncio.run al importarse)

rnd = random.Random(semilla)
TMP = Path(tempfile.mkdtemp(prefix="simint_", dir=str(salida.parent)))


def persister(db, *, drop=frozenset()):
    """La parte de AppState._persist que estos escenarios ejercitan, incluidos incidentes y latidos."""
    async def persist(kind, payload):
        if kind in drop:
            raise OSError(f"almacenamiento no disponible durante {kind} (inyectado)")
        async with db.session() as s:
            if kind == "order":
                await OrderRepository(s).upsert(payload["run_id"], payload["order"])
            elif kind == "fill":
                await FillRepository(s).append(payload["run_id"], payload["fill"])
            elif kind == "account_event":
                await EventRepository(s).append(payload["run_id"], payload["envelope"])
            elif kind == "account_events":
                for env in payload["envelopes"]:
                    await EventRepository(s).append(payload["run_id"], env)
            elif kind == "run_stop":
                await RunRepository(s).stop(payload["run_id"], payload["stopped_at"])
            elif kind == "run_heartbeat":
                await RunRepository(s).heartbeat(payload["run_id"], payload["at"])
            elif kind == "incident":
                await IncidentRepository(s).record(payload)
    return persist


class Observador:
    """Mira el venue en cada emparejamiento (on_bar) y tras cada llamada que cambia órdenes."""

    def __init__(self, engine):
        self.engine, self.looks, self.llamadas, self.max_stops = engine, [], [], 0
        on_bar, submit, cancel = engine.on_bar, engine.submit_order, engine.cancel_order

        def on_bar_obs(candle):
            self.looks.append(self.estado())
            return on_bar(candle)

        async def submit_obs(intent):
            try:
                return await submit(intent)
            finally:
                self.llamadas.append(("submit", intent.order_type.value, bool(intent.reduce_only), self.estado()))

        async def cancel_obs(order_id):
            try:
                return await cancel(order_id)
            finally:
                self.llamadas.append(("cancel", "", False, self.estado()))

        engine.on_bar, engine.submit_order, engine.cancel_order = on_bar_obs, submit_obs, cancel_obs

    def estado(self):
        pos = self.engine.portfolio.positions.get(SYMBOL)
        held = 0.0 if pos is None or pos.is_flat else float(pos.quantity)
        working = [o for o in self.engine.resting_orders(SYMBOL)]
        stops = sum(1 for o in working if o.order_type is OrderType.STOP)
        self.max_stops = max(self.max_stops, stops)
        if not held:
            return {"held": 0.0, "protegida": None, "stops": stops}
        against = Side.SELL if held > 0 else Side.BUY
        cubre = any(o.side is against and (o.quantity - o.filled_quantity) + 1e-12 >= abs(held)
                    and (o.order_type is OrderType.STOP or o.reduce_only) for o in working)
        return {"held": held, "protegida": cubre, "stops": stops}

    def resumen(self):
        con = [x for x in self.looks if x["protegida"] is not None]
        return {"barras_con_posicion": len(con), "barras_sin_proteccion": sum(1 for x in con if x["protegida"] is False),
                "max_stops_simultaneos": self.max_stops,
                "racha_max_llamadas_sin_proteccion": _racha([c[3]["protegida"] for c in self.llamadas])}


def _racha(xs):
    best = cur = 0
    for x in xs:
        cur = cur + 1 if x is False else 0
        best = max(best, cur)
    return best


async def filas(db):
    out = {}
    async with db.engine.connect() as conn:
        for t in ("orders", "fills", "incidents", "account_events", "runs", "backtests"):
            try:
                out[t] = (await conn.execute(text(f"select count(*) from {t}"))).scalar()  # noqa: S608 - fixed names
            except Exception:  # noqa: BLE001
                out[t] = None
        try:
            out["tipos_de_incidente"] = sorted({r[0] for r in await conn.execute(text("select kind from incidents"))})
        except Exception:  # noqa: BLE001
            out["tipos_de_incidente"] = None
    return out


def informe_persistencia(rt):
    if hasattr(rt, "persistence_report"):
        r = rt.persistence_report()
        return {k: (len(v) if k == "lost" else v) for k, v in r.items()}
    return {"sin_informe": "esta versión no lleva la cuenta de sus escrituras"}


async def cerrar(rt):
    if not rt.machine.state.is_terminal:
        await rt.stop(reason="fin del escenario")


async def nueva_db(nombre):
    db = Database(f"sqlite+aiosqlite:///{TMP / (nombre + '.db')}")
    await db.create_schema()
    return db


def foto(rt, eng):
    return {"estado": rt.machine.state.value, "bloqueos": sorted(rt.entry_blocks), "last_error": rt.last_error[:160],
            "posicion": float((eng.portfolio.positions.get(SYMBOL).quantity) if eng.portfolio.positions.get(SYMBOL) else 0.0),
            "ordenes_abiertas": sorted(f"{o.order_type.value}{'/ro' if o.reduce_only else ''}" for o in eng.resting_orders(SYMBOL)),
            "contadores": {k: rt.counters.get(k) for k in ("orders", "round_trips", "stops_placed", "unprotected_positions",
                                                            "protective_stop_failures", "exits_rejected", "exits_stop",
                                                            "exits_reversal", "exits_time", "unknown_order_states",
                                                            "cancel_failures", "orders_lost")}}


def trans(rt):
    return [f"{h.from_state.value}->{h.to_state.value}: {h.reason[:60]}" for h in rt.machine.history]


# ------------------------------------------------------------------------------------------------ escenarios


async def e01_arranque(db):
    rt, eng, market, _ = build(persist=persister(db))
    await register_run(db, rt.run_id)
    inicial = foto(rt, eng)
    await rt.start()
    market.advance()
    await rt._cycle_once()
    corriendo = rt.machine.state.value
    await rt.stop()
    return {"inicial": inicial, "corriendo": corriendo, "final": foto(rt, eng), "transiciones": trans(rt),
            "escrituras": informe_persistencia(rt), "persistence_flushed": rt.persistence_flushed, "filas": await filas(db)}, \
        [("arranca en RUNNING", corriendo == "running"), ("cierra en STOPPED", rt.machine.state.value == "stopped"),
         ("registro completo al cerrar", rt.persistence_flushed is True)]


async def e02_mercado(db):
    rt, eng, market, _ = build(persist=persister(db))
    await register_run(db, rt.run_id)
    await rt.start()
    _seed_every_bucket(rt)
    for _ in range(60):
        market.advance()
        await rt._cycle_once()
    sig = rt.counters.get("signals")
    f = foto(rt, eng)
    await cerrar(rt)
    return {"senales": sig, "final": f}, [("evalúa señales", (sig or 0) > 0), ("sin error", f["last_error"] == "")]


async def e03_apertura(db):
    rt, eng, market, _ = build(persist=persister(db))
    obs = Observador(eng)
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    await rt.flush_persistence(timeout_seconds=5)
    f, fl = foto(rt, eng), await filas(db)
    await cerrar(rt)
    return {"final": f, "filas": fl, "proteccion": obs.resumen()}, \
        [("posición abierta", f["posicion"] != 0.0), ("orden y fill guardados", (fl["orders"] or 0) >= 1 and (fl["fills"] or 0) >= 1)]


async def e04_proteccion(db, *, venue_rechaza_stops=False):
    rt, eng, market, _ = build(persist=persister(db))
    obs = Observador(eng)
    if venue_rechaza_stops:
        real = eng.submit_order

        async def sin_stops(intent):
            if intent.order_type is OrderType.STOP:
                raise ExecutionError("order type stop is not supported by this adapter (inyectado, como Binance antes de R25)")
            return await real(intent)
        eng.submit_order = sin_stops
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    for _ in range(3):
        market.advance()
        await rt._cycle_once()
    await rt.flush_persistence(timeout_seconds=5)
    f, fl, snap = foto(rt, eng), await filas(db), rt.snapshot()
    await cerrar(rt)
    res = {"final": f, "filas": fl, "proteccion": obs.resumen(), "snapshot_protected": (snap.get("position") or {}).get("protected"),
           "transiciones": trans(rt)}
    if not venue_rechaza_stops:
        return res, [("un stop trabajando", sum(x.startswith("stop") for x in f["ordenes_abiertas"]) == 1),
                     ("ninguna barra sin protección", obs.resumen()["barras_sin_proteccion"] == 0),
                     ("snapshot dice protegida", res["snapshot_protected"] is True)]
    return res, [("posición contada como desprotegida", (f["contadores"]["unprotected_positions"] or 0) >= 1),
                 ("entradas bloqueadas", "position_unprotected" in f["bloqueos"]),
                 ("sesión en alto de órdenes nuevas", f["estado"] == "halt_new_orders"),
                 ("incidente guardado", "protective_stop_failed" in (fl["tipos_de_incidente"] or [])),
                 ("snapshot no dice protegida", res["snapshot_protected"] is not True)]


async def e05_gestion(db):
    rt, eng, market, _ = build(persist=persister(db))
    obs = Observador(eng)
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    for _ in range(30):
        market.advance()
        await rt._cycle_once()
        if rt._open_trade is None:
            break
    f = foto(rt, eng)
    await cerrar(rt)
    return {"final": f, "proteccion": obs.resumen()}, \
        [("nunca dos stops", obs.resumen()["max_stops_simultaneos"] <= 1),
         ("ninguna barra sin protección", obs.resumen()["barras_sin_proteccion"] == 0)]


async def e06_stop(db):
    rt, eng, market, _ = build(persist=persister(db))
    obs = Observador(eng)
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    market.advance()
    await rt._cycle_once()
    largo = eng.portfolio.positions[SYMBOL].quantity > 0
    precio = market._candles[market.cursor - 1].close
    rt._planned_exit["stop"] = precio * (1.02 if largo else 0.98)  # el mercado ya cruzó el nivel: el stop dispara
    for _ in range(4):
        market.advance()
        await rt._cycle_once()
        if rt._open_trade is None:
            break
    f = foto(rt, eng)
    await cerrar(rt)
    return {"final": f, "proteccion": obs.resumen()}, \
        [("cerrada por stop", (f["contadores"]["exits_stop"] or 0) == 1), ("plana", f["posicion"] == 0.0),
         ("ida y vuelta puntuada", (f["contadores"]["round_trips"] or 0) == 1), ("sin órdenes colgadas", f["ordenes_abiertas"] == [])]


async def e07_reversion(db):
    rt, eng, market, _ = build(persist=persister(db))
    obs = Observador(eng)
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    market.advance()
    await rt._cycle_once()
    enviado = await rt._close_position("signal reversed")
    for _ in range(3):
        market.advance()
        await rt._cycle_once()
        if rt._open_trade is None:
            break
    f = foto(rt, eng)
    await cerrar(rt)
    return {"enviado": enviado, "final": f, "proteccion": obs.resumen()}, \
        [("cierre enviado", enviado is True), ("plana", f["posicion"] == 0.0),
         ("ninguna barra sin protección", obs.resumen()["barras_sin_proteccion"] == 0)]


async def e08_cierre_rechazado(db):
    rt, eng, market, _ = build(persist=persister(db))
    obs = Observador(eng)
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    market.advance()
    await rt._cycle_once()
    rechazos = {"n": 0}
    real = eng._should_reject

    def rechaza_primer_cierre(order):
        if order.reduce_only and order.order_type is OrderType.MARKET and rechazos["n"] == 0:
            rechazos["n"] += 1
            return True
        return real(order)
    eng._should_reject = rechaza_primer_cierre
    await rt._close_position("time stop")
    inmediatamente = obs.estado()
    market.advance()
    await rt._cycle_once()  # la barra siguiente se empareja aquí
    await rt._close_position("time stop")  # reintento
    for _ in range(3):
        market.advance()
        await rt._cycle_once()
        if rt._open_trade is None:
            break
    await rt.flush_persistence(timeout_seconds=5)
    f, fl = foto(rt, eng), await filas(db)
    await cerrar(rt)
    return {"tras_el_rechazo": inmediatamente, "final": f, "proteccion": obs.resumen(), "filas": fl}, \
        [("rechazo registrado", (f["contadores"]["exits_rejected"] or 0) == 1),
         ("protegida en la misma llamada", inmediatamente["protegida"] is True),
         ("ninguna barra sin protección", obs.resumen()["barras_sin_proteccion"] == 0),
         ("reintento cierra", f["posicion"] == 0.0)]


async def e09_parcial_y_timeout(db):
    rt, eng, market, _ = build(persist=persister(db))
    obs = Observador(eng)
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    market.advance()
    await rt._cycle_once()
    eng._config = eng.config.model_copy(update={"partial_fill_probability": 1.0})  # cierres en partes
    real = eng.submit_order
    estado = {"timeouts": 0}

    async def respuesta_perdida(intent):
        order = await real(intent)  # la orden llega...
        if intent.reduce_only and intent.order_type is OrderType.MARKET and estado["timeouts"] == 0:
            estado["timeouts"] += 1
            raise ReconciliationError("respuesta perdida (inyectado)")  # ...y la respuesta no
        return order
    eng.submit_order = respuesta_perdida

    async def resolver(*, symbol, client_order_id):
        return await eng.get_order(client_order_id)
    eng.resolve_unknown_order = resolver
    await rt._close_position("time stop")
    for i in range(12):
        if i == 2:  # dos barras de llenados parciales; después el venue llena lo que quede
            eng._config = eng.config.model_copy(update={"partial_fill_probability": 0.0})
        market.advance()
        await rt._cycle_once()
        if rt._open_trade is None:
            break
    cierres = [o for o in await eng.get_orders() if o.reduce_only and o.order_type is OrderType.MARKET]
    f = foto(rt, eng)
    await cerrar(rt)
    return {"final": f, "cierres_enviados": len(cierres), "proteccion": obs.resumen()}, \
        [("estado desconocido resuelto", (f["contadores"]["unknown_order_states"] or 0) >= 1),
         ("sin cierre duplicado por el timeout", len(cierres) <= 2), ("plana al final", f["posicion"] == 0.0),
         ("ninguna barra sin protección", obs.resumen()["barras_sin_proteccion"] == 0)]


async def e10_conexion(db):
    rt, eng, market, _ = build(persist=persister(db))
    obs = Observador(eng)
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    market.advance()
    await rt._cycle_once()
    real_candles, real_portfolio = market.get_candles, eng.get_portfolio
    caidas = {"datos": 3, "portafolio": 2}

    async def candles_caidas(*a, **k):
        if caidas["datos"] > 0:
            caidas["datos"] -= 1
            raise ProviderUnavailableError("sin conexión al feed (inyectado)")
        return await real_candles(*a, **k)

    async def portafolio_caido():
        if caidas["portafolio"] > 0:
            caidas["portafolio"] -= 1
            raise ProviderUnavailableError("sin conexión al venue (inyectado)")
        return await real_portfolio()
    market.get_candles, eng.get_portfolio = candles_caidas, portafolio_caido
    errores = 0
    for _ in range(8):
        market.advance()
        try:
            await rt._cycle_once()
        except Exception:  # noqa: BLE001 - el bucle real lo atrapa y cuenta
            errores += 1
    f = foto(rt, eng)
    await cerrar(rt)
    return {"final": f, "excepciones_al_bucle": errores, "proteccion": obs.resumen(), "transiciones": trans(rt)}, \
        [("posición sigue protegida en el venue", "stop" in f["ordenes_abiertas"] or f["posicion"] == 0.0),
         ("ninguna barra sin protección", obs.resumen()["barras_sin_proteccion"] == 0)]


async def e11_escrituras_concurrentes(db):
    base = _row(_run())
    otra = {**base, "trades": base["trades"] + 1, "total_return_pct": base["total_return_pct"] + 1.0}
    descartados = ambos = 0
    for i in range(20):
        async with db.engine.begin() as conn:
            await conn.execute(text("delete from backtests"))
        listo = asyncio.Event()

        async def w(fila):
            try:
                async with db.session() as s:
                    await listo.wait()
                    await BacktestRepository(s).save(fila)
                return True
            except ValueError:
                return False
        filas_ = [base, otra] if i % 2 == 0 else [otra, base]
        t = [asyncio.create_task(w(x)) for x in filas_]
        await asyncio.sleep(0.01)
        listo.set()
        res = await asyncio.gather(*t, return_exceptions=True)
        async with db.session() as s:
            guardada = (await BacktestRepository(s).list_recent())[0]
        ambos += all(r is True for r in res)
        descartados += sum(1 for f_, r in zip(filas_, res, strict=True) if r is True and f_["trades"] != guardada.trades)
    return {"intentos": 20, "ambos_aceptados": ambos, "exito_descartado": descartados, "nota": "SQLite serializa escritores; la carrera real está medida en PostgreSQL (F1)"}, \
        [("ningún escritor descartado recibe éxito", descartados == 0)]


async def e12_persistencia_incompleta(db):
    rt, eng, market, _ = build(persist=persister(db, drop=frozenset({"fill"})))
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    dijo = await rt.flush_persistence(timeout_seconds=5)
    rep = informe_persistencia(rt)
    await rt.stop()
    restore = await rebuild(db)
    b, _, _, _ = build(account=restore)
    await b.start()
    bloqueada = "account_state" in b.entry_blocks
    await b.stop()
    return {"flush_dijo": dijo, "escrituras": rep, "persistence_flushed": rt.persistence_flushed, "last_error": rt.last_error[:160],
            "reconstruccion_completa": restore.complete, "siguiente_sesion_bloqueada": bloqueada}, \
        [("flush NO dice completo", dijo is False), ("cierre no limpio", rt.persistence_flushed is False),
         ("la siguiente sesión no opera sobre un registro corto", bloqueada)]


async def e13_apagado_y_recuperacion(db):
    rt, eng, market, clock = build(persist=persister(db))
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    market.advance()
    await rt._cycle_once()
    held = eng.portfolio.positions[SYMBOL].quantity
    await rt.stop()
    restore = await rebuild(db)
    clock_b = SimulatedClock(clock.now())
    market_b = FakeMarketData(market._candles, clock_b)
    market_b.cursor = market.cursor
    eng_b = engine_for(clock_b, live_settings())
    eng_b.restore_portfolio(restore.portfolio_state())
    obs = Observador(eng_b)
    b, _, _, _ = build(persist=persister(db), account=restore, engine=eng_b, clock=clock_b, market=market_b)
    await register_run(db, b.run_id)
    await b.start()
    al_arrancar = obs.estado()  # antes del primer emparejamiento de la sesión nueva
    market_b.advance()
    await b._cycle_once()
    reprotegida = sum(x.startswith("stop") for x in foto(b, eng_b)["ordenes_abiertas"]) == 1
    await b._close_position("time stop")
    for _ in range(3):
        market_b.advance()
        await b._cycle_once()
        if b._open_trade is None:
            break
    f = foto(b, eng_b)
    await b.stop()
    final = await rebuild(db)
    return {"posicion_al_apagar": held, "reconstruccion": {"completa": restore.complete, "posicion": restore.position_quantity},
            "al_arrancar": al_arrancar, "reprotegida": reprotegida, "final": f, "final_reconstruido": {"completo": final.complete, "posicion": final.has_position},
            "proteccion_sesion_b": obs.resumen()}, \
        [("la reconstrucción ve la posición", restore.complete and abs(restore.position_quantity - held) < 1e-9),
         ("la sesión nueva la protege", reprotegida),
         ("protegida antes de su primera barra", al_arrancar["protegida"] is True and obs.resumen()["barras_sin_proteccion"] == 0),
         ("se cierra y el registro queda completo y plano", final.complete and not final.has_position)]


async def e14_reconciliacion(db):
    rt, eng, market, _ = build(persist=persister(db))
    await register_run(db, rt.run_id)
    await rt.start()
    await open_position(rt, market)
    market.advance()
    await rt._cycle_once()
    precio = market._candles[market.cursor - 1].close
    ajena = OrderIntent(intent_id="ajena", client_order_id="ajena-manual-1", signal_id="manual", risk_decision_id="manual",
                        symbol=SYMBOL, side=Side.BUY, quantity=0.01, order_type=OrderType.LIMIT, limit_price=round(precio * 0.9, 2),
                        time_in_force=TimeInForce.GTC, created_at=datetime.now(UTC))
    puesta = await eng.submit_order(ajena)  # una orden puesta a mano en el venue
    assert not puesta.state.is_terminal, f"la orden ajena debe quedar trabajando ({puesta.state.value})"
    await rt._reconcile()
    estado = rt.machine.state.value
    f = foto(rt, eng)
    await rt.flush_persistence(timeout_seconds=5)
    fl = await filas(db)
    await cerrar(rt)
    return {"estado_tras_conciliar": estado, "final": f, "filas": fl, "transiciones": trans(rt)}, \
        [("la orden ajena detiene la operatoria", estado in ("safe_mode", "halt_new_orders"))]


ESCENARIOS = [
    ("E01_arranque_en_papel", e01_arranque), ("E02_mercado_y_senales", e02_mercado), ("E03_apertura", e03_apertura),
    ("E04_proteccion_colocada_y_confirmada", e04_proteccion),
    ("E04b_venue_que_rechaza_stops_R25", lambda db: e04_proteccion(db, venue_rechaza_stops=True)),
    ("E05_gestion_normal", e05_gestion), ("E06_cierre_por_stop", e06_stop), ("E07_cierre_por_reversion", e07_reversion),
    ("E08_cierre_rechazado_y_reintento", e08_cierre_rechazado), ("E09_parcial_y_timeout", e09_parcial_y_timeout),
    ("E10_perdida_de_conexion", e10_conexion), ("E11_escrituras_concurrentes", e11_escrituras_concurrentes),
    ("E12_persistencia_incompleta", e12_persistencia_incompleta), ("E13_apagado_y_recuperacion", e13_apagado_y_recuperacion),
    ("E14_reconciliacion", e14_reconciliacion),
]  # E15 (reversión de versión) corre aparte: necesita dos árboles sobre la misma base (reversion_version.sh)


async def main():
    resultados = []
    for nombre, f in ESCENARIOS:
        db = await nueva_db(nombre)
        try:
            obs, checks = await f(db)
            error = None
        except Exception as exc:  # noqa: BLE001 - un escenario que revienta es un resultado
            obs, checks, error = {}, [("el escenario corre sin excepción", False)], f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-1500:]}"
        finally:
            await db.close()
        fallos = [c for c, ok in checks if not ok]
        resultados.append({"escenario": nombre, "semilla": semilla, "observado": obs, "esperado": [c for c, _ in checks],
                           "incumplidos": fallos, "error": error, "veredicto": "CUMPLE" if not fallos and not error else "NO CUMPLE"})
        print(f"{'CUMPLE   ' if not fallos and not error else 'NO CUMPLE'} {nombre:40s} {fallos} {('ERROR ' + error.splitlines()[0]) if error else ''}")
    json.dump({"arbol": str(arbol), "semilla": semilla, "escenarios": resultados}, open(salida, "w"), indent=1,
              default=str, ensure_ascii=False)
    shutil.rmtree(TMP, ignore_errors=True)


asyncio.run(main())
