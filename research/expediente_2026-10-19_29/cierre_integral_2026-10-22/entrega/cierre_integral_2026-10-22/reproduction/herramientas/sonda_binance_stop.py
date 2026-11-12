"""Sonda sintética (sin red) del defecto de protección del adaptador de Binance, independiente de R19 y de la guarda 05.

Qué comprueba, contra el código de un árbol dado:
 1. el adaptador declara supports_stop_orders=True;
 2. una orden con la MISMA forma que el stop protector del vivo (live.py: OrderType.STOP, reduce_only=True, GTC, stop_price)
    se rechaza en submit_order con ExecutionError «not supported» y NO llega al transporte (0 pedidos);
 3. como control, una orden MARKET con el mismo adaptador sí llega al transporte (el rechazo es por el tipo, no por la sonda);
 4. por inspección (no ejecutado): las líneas del vivo que construyen el stop y que tragan la excepción.
Usa transporte simulado (httpx.MockTransport), modo testnet (simulated=True) y NINGÚN token de activación ni credencial real.
Uso: python -I sonda_binance_stop.py <árbol> <salida.json>"""
import asyncio
import json
import pathlib
import sys

arbol = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(arbol / "packages/tia/src"))

from datetime import UTC, datetime  # noqa: E402

import httpx  # noqa: E402

from tia.core.clock import SimulatedClock  # noqa: E402
from tia.core.errors import ExecutionError  # noqa: E402
from tia.data.providers.binance_live import BinanceExecutionProvider  # noqa: E402
from tia.data.providers.binance_signing import BinanceCredentials, BinanceSigner  # noqa: E402
from tia.domain.enums import OrderType, Side, TimeInForce  # noqa: E402
from tia.domain.orders import OrderIntent  # noqa: E402

START = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def adaptador(pedidos):
    def handler(request):
        pedidos.append(str(request.url.path))
        q = dict(httpx.QueryParams(request.url.query.decode()))
        return httpx.Response(200, json={"symbol": "BTCUSDT", "orderId": 1, "clientOrderId": q.get("newClientOrderId", ""),
                                         "transactTime": int(START.timestamp() * 1000), "price": "0", "origQty": "0.01",
                                         "executedQty": "0.01", "cummulativeQuoteQty": "500", "status": "FILLED", "side": "BUY",
                                         "fills": [{"price": "50000", "qty": "0.01", "commission": "0", "tradeId": 1}]})
    clock = SimulatedClock(START)
    cred = BinanceCredentials.from_values(api_key="sonda-sin-clave", secret="sonda-sin-secreto")  # noqa: S106 - material de prueba
    return BinanceExecutionProvider(signer=BinanceSigner(cred, clock), clock=clock, activation=None, simulated=True,
                                    client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://sonda.invalid"))


def intento(order_type, **extra):
    return OrderIntent(
        intent_id="int-sonda", client_order_id=OrderIntent.build_client_order_id(
            signal_id=f"protective:BTC-USD:sonda:{order_type.value}", symbol="BTC-USD", side=Side.SELL, quantity=0.01, order_type=order_type),
        signal_id="protective:BTC-USD", risk_decision_id="protective:BTC-USD", symbol="BTC-USD", side=Side.SELL, quantity=0.01,
        order_type=order_type, created_at=START, **extra)


async def main():
    rep = {"arbol": str(arbol)}
    pedidos = []
    a = adaptador(pedidos)
    rep["supports_stop_orders"] = a.capabilities.supports_stop_orders
    stop = intento(OrderType.STOP, stop_price=49000.0, time_in_force=TimeInForce.GTC, reduce_only=True)
    try:
        await a.submit_order(stop)
        rep["stop_protector"] = {"resultado": "aceptado"}
    except ExecutionError as exc:
        rep["stop_protector"] = {"resultado": "ExecutionError", "mensaje": str(exc)[:200]}
    rep["stop_protector"]["pedidos_al_transporte"] = len(pedidos)
    pedidos_ctrl = []
    b = adaptador(pedidos_ctrl)
    o = await b.submit_order(intento(OrderType.MARKET))
    rep["control_market"] = {"estado": o.state.value, "pedidos_al_transporte": len(pedidos_ctrl)}
    live = (arbol / "packages/tia/src/tia/runtime/live.py").read_text().splitlines()
    rep["inspeccion_live"] = {f"live.py:{i}": live[i - 1].strip() for i in range(1, len(live) + 1)
                              if "order_type=OrderType.STOP," in live[i - 1] or "protective_stop_failed" in live[i - 1]
                              or (i > 1 and "protective_stop_failed" in live[i] if i < len(live) else False)}
    rep["DEFECTO_REPRODUCIDO"] = (rep["supports_stop_orders"] is True and rep["stop_protector"]["resultado"] == "ExecutionError"
                                  and "not supported" in rep["stop_protector"].get("mensaje", "")
                                  and rep["stop_protector"]["pedidos_al_transporte"] == 0 and rep["control_market"]["pedidos_al_transporte"] == 1)
    json.dump(rep, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
    print(json.dumps(rep, indent=1, ensure_ascii=False))


asyncio.run(main())
