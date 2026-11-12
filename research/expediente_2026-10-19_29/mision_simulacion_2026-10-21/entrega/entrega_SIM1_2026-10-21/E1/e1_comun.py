"""E1 — piezas comunes: datos, motor corregido, configuraciones y escenarios.

Nada aquí cambia las reglas de las estrategias (``tia.strategy.library``) ni el repositorio. El motor es el
``BacktestEngine`` del paquete con DOS correcciones de su mecánica de órdenes, copiadas de la sesión en vivo
(``tia.runtime.live``), porque sin ellas el backtest no representa las salidas que el bot ejecuta:

* D1 — ``_request_exit`` y ``_sync_protective_stop`` construyen el ``client_order_id`` sin la barra: tras un
  rechazo (1 % simulado) o una cancelación, el reintento colisiona con la orden anterior, se suprime como
  duplicado y la posición queda sin stop y sin salida. La sesión en vivo usa un id único por barra
  (``protective:{symbol}:{run_id}:{bars}``).
* D2 — ``_sync_protective_stop`` solo reemplaza el stop si cambia la cantidad, no si cambia el NIVEL: el
  break-even y el trailing ajustan ``leg.stop_price`` pero la orden activa conserva el stop original. La sesión
  en vivo compara también el nivel (``same_level``).
"""

from __future__ import annotations

import contextlib
import csv
import dataclasses
import hashlib
import io
import logging
import math
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import structlog

import tia.backtest.engine as EM
from tia.backtest.engine import BacktestConfig, BacktestEngine
from tia.core.config import ExecutionSimConfig, RiskLimits, StrategyConfig
from tia.domain.enums import AssetClass, Direction, OrderType, Side, TimeInForce
from tia.domain.instruments import Instrument, InstrumentUniverse
from tia.domain.market import Candle
from tia.domain.orders import OrderIntent
from tia.core.ids import deterministic_id
from tia.execution.paper import PaperExecutionProvider
from tia.risk.budget import RiskBudgetEngine

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))

SIMBOLO = "BTCUSDT"
DATOS = Path("/home/user/Trader-IA/research/hcarry_next/datos/binance_vision/spot")
ESTRATEGIAS = ("trend_following", "mean_reversion", "breakout")
SEMILLA = 20261019
HORA = timedelta(hours=1)


# ----------------------------------------------------------------------------------------------- datos
def leer_velas(raiz: Path = DATOS) -> tuple[list[Candle], dict]:
    """Velas 1 h oficiales de data.binance.vision, verificadas contra su .CHECKSUM antes de leerlas.
    Tiempos en ms (hasta 2024) o µs (desde 2025). close_time = open_time + 1 h exacto (UTC)."""
    filas: dict[int, tuple] = {}
    conflictos: dict[int, set] = {}
    archivos = []
    for z in sorted(raiz.rglob("*.zip")):
        datos = z.read_bytes()
        h = hashlib.sha256(datos).hexdigest()
        chk = z.with_name(z.name + ".CHECKSUM")
        oficial = chk.read_text().split()[0] if chk.is_file() else None
        if oficial != h:
            raise SystemExit(f"{z} no coincide con su .CHECKSUM oficial: se detiene")
        archivos.append({"archivo": str(z.relative_to(raiz)), "sha256": h, "bytes": len(datos)})
        with zipfile.ZipFile(io.BytesIO(datos)) as f:
            for n in f.namelist():
                for r in csv.reader(io.TextIOWrapper(f.open(n))):
                    t = int(r[0])
                    t = t // 1000 if t > 10**14 else t          # µs -> ms
                    fila = (float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), int(r[8]))
                    if t in filas and filas[t] != fila:
                        # Adenda 1: la misma hora con valores distintos en el archivo mensual y en el diario no se
                        # puede resolver sin elegir una fuente; se trata como faltante (regla neutral, fijada antes
                        # de ejecutar ninguna estrategia).
                        conflictos.setdefault(t, {filas[t]}).add(fila)
                    filas[t] = fila
    for t in conflictos:
        del filas[t]
    velas = []
    for t in sorted(filas):
        o, hi, lo, c, v, n = filas[t]
        ini = datetime.fromtimestamp(t / 1000, tz=timezone.utc)
        velas.append(Candle(symbol=SIMBOLO, timeframe="1h", open_time=ini, close_time=ini + HORA, open=o, high=hi,
                            low=lo, close=c, volume=v, trade_count=n, provider="data.binance.vision"))
    esperadas = int((velas[-1].open_time - velas[0].open_time) / HORA) + 1
    huecos = [(a.open_time.isoformat(), int((b.open_time - a.open_time) / HORA) - 1)
              for a, b in zip(velas, velas[1:]) if b.open_time - a.open_time > HORA]
    meta = {"fuente": "data.binance.vision spot klines 1h BTCUSDT (mensuales + diarios), verificados contra .CHECKSUM",
            "archivos": archivos, "n_archivos": len(archivos),
            "sha256_lista_archivos": hashlib.sha256("\n".join(f"{a['sha256']}  {a['archivo']}" for a in archivos)
                                                   .encode()).hexdigest(),
            "primera_vela": velas[0].open_time.isoformat(), "ultima_vela": velas[-1].open_time.isoformat(),
            "velas": len(velas), "esperadas": esperadas, "faltantes": esperadas - len(velas), "huecos": huecos,
            "zona_horaria": "UTC", "transformaciones": "ninguna: sin relleno ni ajuste; close_time = open_time + 1 h",
            "horas_en_conflicto_excluidas": [datetime.fromtimestamp(t / 1000, tz=timezone.utc).isoformat() for t in sorted(conflictos)]}
    return velas, meta


def sinteticas(n: int, semilla: int, *, desde: Candle | None = None, t0: datetime | None = None) -> list[Candle]:
    """SINTÉTICAS — solo para pruebas de funcionamiento y de look-ahead. Nunca para afirmar una ventaja."""
    rng = np.random.default_rng(semilla)
    t = t0 or (desde.close_time if desde else datetime(2020, 1, 1, tzinfo=timezone.utc))
    p = desde.close if desde else 30000.0
    out = []
    for i in range(n):
        o = p
        camino = o * np.exp(np.cumsum(rng.normal(0.0003 * math.sin((i + semilla) / 250), 0.004, 4)))
        c = float(camino[-1])
        out.append(Candle(symbol=SIMBOLO, timeframe="1h", open_time=t, close_time=t + HORA, open=o,
                          high=float(max(o, camino.max())) * 1.0005, low=float(min(o, camino.min())) * 0.9995, close=c,
                          volume=float(rng.lognormal(7, 0.5)), provider="SINTETICO"))
        p, t = c, t + HORA
    return out


# ----------------------------------------------------------------------------------------- motor E1
class MotorE1(BacktestEngine):
    """``BacktestEngine`` con D1 y D2 corregidos como en ``tia.runtime.live``; el resto, idéntico."""

    def __init__(self, *a, **k) -> None:
        super().__init__(*a, **k)
        self._colocaciones = 0
        #: intervenciones de D3, contadas para el informe
        self.d3 = {"entradas_restantes_canceladas_al_salir": 0, "restos_de_entrada_cancelados_en_plano": 0,
                   "salidas_terminadas_con_posicion_restante": 0, "piernas_sin_stop_huerfanas": 0}

    @staticmethod
    def _entradas_restantes(provider, symbol):
        """Órdenes de entrada aún activas (no reduce-only, no stop) del símbolo."""
        out = []
        for oid in list(provider._resting):
            o = provider._orders.get(oid)
            if (o is not None and not o.state.is_terminal and o.symbol == symbol and not o.reduce_only
                    and o.order_type is not OrderType.STOP):
                out.append(o)
        return out

    def _request_exit(self, provider, leg, reason, stop_order_id, candle, counts):
        # D3 (como `_close_position` de la sesión): antes de cerrar, cancelar el resto de la entrada que aún
        # descansa, para que no se sume a la posición mientras la salida (dimensionada a la pierna) está en vuelo.
        for o in self._entradas_restantes(provider, leg.symbol):
            EM._sync(provider.cancel_order(o.order_id))
            self.d3["entradas_restantes_canceladas_al_salir"] += 1
        if stop_order_id is not None:
            EM._sync(provider.cancel_order(stop_order_id))
        side = Side.SELL if leg.direction is Direction.LONG else Side.BUY
        clave = f"exit:{reason.replace(' ', '-')}:{leg.signal_id}"
        intent = OrderIntent(
            intent_id=deterministic_id("int", "exit", leg.signal_id, reason, candle.close_time),
            # D1: id único por barra, como la sesión (antes: igual en cada reintento -> suprimido como duplicado)
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=f"{clave}:{candle.close_time.isoformat()}", symbol=leg.symbol, side=side,
                quantity=leg.quantity, order_type=OrderType.MARKET),
            signal_id=clave, risk_decision_id=f"exit:{leg.signal_id}", symbol=leg.symbol, side=side,
            quantity=leg.quantity, order_type=OrderType.MARKET, time_in_force=TimeInForce.GTC,
            created_at=candle.close_time, reduce_only=True)
        order = EM._sync(provider.submit_order(intent))
        counts.exits_requested[reason] = counts.exits_requested.get(reason, 0) + 1
        if order.state.is_terminal and not order.fills:
            counts.orders_rejected += 1
            return None
        leg.exit_pending = reason
        leg.exit_order_id = order.order_id
        return None

    def _sync_protective_stop(self, provider, leg, current_id, counts):
        if leg is None:
            # D3: en plano, un resto de una entrada ya parcialmente llenada es una orden vencida (abriría una
            # pierna sin stop ni objetivo); una entrada nueva sin ningún llenado no se toca.
            for o in self._entradas_restantes(provider, SIMBOLO):
                if o.filled_quantity > 0:
                    EM._sync(provider.cancel_order(o.order_id))
                    self.d3["restos_de_entrada_cancelados_en_plano"] += 1
        elif leg.exit_pending is not None and leg.exit_order_id:
            # D3, red de seguridad: si la salida ya terminó pero queda posición, se libera la marca para que el
            # stop se reponga y la salida pueda volver a pedirse (si no, la pierna queda trabada para siempre).
            o = EM._sync(provider.get_order(leg.exit_order_id))
            if o is not None and o.state.is_terminal and leg.quantity > 0:
                leg.exit_pending = None
                leg.exit_order_id = ""
                self.d3["salidas_terminadas_con_posicion_restante"] += 1
        if leg is not None and leg.stop_price is None and leg.exit_pending is None:
            self.d3["piernas_sin_stop_huerfanas"] += 1
        if leg is None or leg.stop_price is None or leg.exit_pending is not None:
            if current_id is not None:
                EM._sync(provider.cancel_order(current_id))
            return None
        existing = EM._sync(provider.get_order(current_id)) if current_id else None
        if existing is not None and not existing.state.is_terminal:
            covered = existing.quantity - existing.filled_quantity
            mismo_tamano = abs(covered - leg.quantity) <= max(leg.quantity * 1e-6, 1e-9)
            # D2: también el nivel, como `same_level` en la sesión (antes: solo la cantidad)
            mismo_nivel = abs(float(existing.stop_price or 0.0) - float(leg.stop_price)) <= 1e-9 * float(leg.stop_price)
            if mismo_tamano and mismo_nivel:
                return current_id
            EM._sync(provider.cancel_order(current_id))
        side = Side.SELL if leg.direction is Direction.LONG else Side.BUY
        self._colocaciones += 1
        intent = OrderIntent(
            intent_id=deterministic_id("int", "stop", leg.signal_id, leg.quantity, self._colocaciones),
            # D1: id único por colocación (antes: igual tras una cancelación -> stop nunca re-colocado)
            client_order_id=OrderIntent.build_client_order_id(
                signal_id=f"{leg.signal_id}:protective:{self._colocaciones}", symbol=leg.symbol, side=side,
                quantity=leg.quantity, order_type=OrderType.STOP),
            signal_id=leg.signal_id, risk_decision_id=f"protective:{leg.signal_id}", symbol=leg.symbol, side=side,
            quantity=leg.quantity, order_type=OrderType.STOP, stop_price=leg.stop_price,
            time_in_force=TimeInForce.GTC, created_at=leg.entry_at)
        try:
            order = EM._sync(provider.submit_order(intent))
        except Exception:  # noqa: BLE001 — mismo tratamiento que el motor original
            counts.protective_stops_unplaced += 1
            return None
        if order.state.is_terminal:
            counts.protective_stops_unplaced += 1
            return None
        return order.order_id


# --------------------------------------------------------------------------- escenarios (parches en proceso)
class _PresupuestoSinGobernadorDeCaida(RiskBudgetEngine):
    """Neutraliza SOLO el estado de caída de la cuenta (defensivo/emergencia), que en el perfil por defecto
    corta las entradas para siempre al 6 % (el capital solo se recupera operando). Se conservan el
    multiplicador de volatilidad, el de racha de pérdidas, el máximo de operaciones diarias y todo lo demás."""

    def compute(self, inputs):
        return super().compute(dataclasses.replace(inputs, drawdown_pct=0.0, peak_equity=inputs.equity))


class _ProveedorConRetraso(PaperExecutionProvider):
    """Estrés de latencia: una orden creada al cierre de t no puede ejecutarse hasta la apertura de t+2."""

    def on_bar(self, candle):
        self._last_price[candle.symbol] = candle.close
        producidos = []
        for order_id in list(self._resting):
            order = self._orders.get(order_id)
            if order is None or order.state.is_terminal:
                self._resting.remove(order_id)
                continue
            if order.symbol != candle.symbol or order.created_at >= candle.open_time:
                continue
            fill = self._try_fill(order, candle)
            if fill is not None:
                producidos.append(fill)
            if order.state.is_terminal and order_id in self._resting:
                self._resting.remove(order_id)
        self._portfolio.mark(candle.symbol, candle.close, candle.close_time)
        return producidos


@contextlib.contextmanager
def escenario(*, gobernadores_en_vivo: bool, retraso: bool):
    viejo_p, viejo_x = EM.RiskBudgetEngine, EM.PaperExecutionProvider
    try:
        if not gobernadores_en_vivo:
            EM.RiskBudgetEngine = _PresupuestoSinGobernadorDeCaida
        if retraso:
            EM.PaperExecutionProvider = _ProveedorConRetraso
        yield
    finally:
        EM.RiskBudgetEngine, EM.PaperExecutionProvider = viejo_p, viejo_x


def universo(shortable: bool) -> InstrumentUniverse:
    return InstrumentUniverse(instruments=(Instrument(
        symbol=SIMBOLO, asset_class=AssetClass.CRYPTO, base_currency="BTC", quote_currency="USDT", tick_size=0.01,
        lot_size=1e-5, min_notional=5.0, shortable=shortable, correlation_cluster="crypto",
        venue="binance_spot_simulado"),))


def configuracion(estrategias: tuple[str, ...], *, cortos: bool, comision_bps: float = 10.0,
                  deslizamiento_base_bps: float = 2.0, impacto: float = 0.35, gobernadores_en_vivo: bool = False,
                  dataset: str = "BTCUSDT-1h") -> BacktestConfig:
    riesgo = RiskLimits() if gobernadores_en_vivo else RiskLimits(max_drawdown_pct=90.0)
    return BacktestConfig(
        dataset=dataset, timeframe="1h", initial_capital=100_000.0, seed=SEMILLA,
        strategy=StrategyConfig(enabled=estrategias), risk=riesgo,
        execution=ExecutionSimConfig(taker_fee_bps=comision_bps, maker_fee_bps=comision_bps,
                                     base_slippage_bps=deslizamiento_base_bps, impact_coefficient=impacto,
                                     allow_shorting=cortos))


def correr_con_d3(velas: list[Candle], estrategias: tuple[str, ...], *, cortos: bool = False, retraso: bool = False,
                  gobernadores_en_vivo: bool = False, motor_original: bool = False, **costes):
    cfg = configuracion(estrategias, cortos=cortos, gobernadores_en_vivo=gobernadores_en_vivo, **costes)
    clase = BacktestEngine if motor_original else MotorE1
    motor = clase(cfg, universo(cortos), strategies=estrategias)
    with escenario(gobernadores_en_vivo=gobernadores_en_vivo, retraso=retraso):
        r = motor.run(velas)
    return r, dict(getattr(motor, "d3", {}))


def correr(velas: list[Candle], estrategias: tuple[str, ...], **kw):
    return correr_con_d3(velas, estrategias, **kw)[0]


def round_trips(trades) -> list[dict]:
    """Agrega las piezas de un mismo round trip (cierres parciales) en una sola operación."""
    grupos: dict[tuple, list] = {}
    for t in trades:
        grupos.setdefault((t.signal_id, t.entry_at, t.direction), []).append(t)
    out = []
    for (sid, entrada, direccion), piezas in grupos.items():
        nocional = sum(p.entry_price * p.quantity for p in piezas)
        neto = sum(p.net_pnl for p in piezas)
        bruto = sum(p.gross_pnl for p in piezas)
        comisiones = sum(p.fees for p in piezas)
        out.append({"entrada": entrada.isoformat(), "salida": max(p.exit_at for p in piezas).isoformat(),
                    "direccion": direccion.value, "nocional": nocional,
                    "neto_pct": neto / nocional * 100.0 if nocional > 0 else 0.0,
                    "bruto_pct": bruto / nocional * 100.0 if nocional > 0 else 0.0,
                    "comisiones_pct": comisiones / nocional * 100.0 if nocional > 0 else 0.0,
                    "barras": max(p.bars_held for p in piezas),
                    "razon_salida": sorted({p.exit_reason for p in piezas}), "confianza": piezas[0].confidence,
                    "regimen_bot": piezas[0].regime_at_entry.value, "piezas": len(piezas)})
    return sorted(out, key=lambda x: x["entrada"])
