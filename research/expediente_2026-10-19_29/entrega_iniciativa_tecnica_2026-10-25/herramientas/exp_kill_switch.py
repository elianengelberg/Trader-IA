"""TI · Experimento: ¿qué le pasa a una posición abierta cuando el operador acciona el kill switch?
Papel (PaperExecutionProvider + LiveRuntime reales, mercado de las pruebas). Se coloca el stop protector cerca del precio
(0,2 % por debajo, posición larga), se acciona el kill switch y se avanzan barras hasta que el mínimo de una barra cruza el
nivel del stop anterior. Se registra: órdenes en reposo, posición, estado, lo que dice la instantánea («protected») y si la
posición quedó cubierta en cada emparejamiento. Esperado de un sistema seguro (fijado antes de correr): la posición
sigue cubierta después del kill switch y, cuando el precio cruza el nivel, el stop la cierra.
Uso: python -I exp_kill_switch.py <árbol> <salida.json> [accion: kill|flatten_rechazado]"""
import asyncio
import json
import sys
from pathlib import Path

arbol, salida = Path(sys.argv[1]), Path(sys.argv[2])
accion = sys.argv[3] if len(sys.argv) > 3 else "kill"
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
from tests.integration.test_account_restore import SYMBOL, build, open_position  # noqa: E402
from tia.domain.enums import OrderType  # noqa: E402


def vista(rt, eng):
    pos = eng.portfolio.positions.get(SYMBOL)
    held = 0.0 if pos is None or pos.is_flat else float(pos.quantity)
    stops = [o for o in eng.resting_orders(SYMBOL) if o.order_type is OrderType.STOP]
    return {"estado": rt.machine.state.value, "posicion": held,
            "stops_en_reposo": [{"precio": o.stop_price, "cantidad": o.quantity - o.filled_quantity} for o in stops],
            "snapshot_protected": (rt.snapshot().get("position") or {}).get("protected"),
            "unprotected_positions": rt.counters.get("unprotected_positions"), "bloqueos": sorted(rt.entry_blocks),
            "incidentes": sorted({i["kind"] for i in rt.incidents}) if hasattr(rt, "incidents") else None}


async def main():
    rt, eng, market, _ = build()
    await rt.start()
    await open_position(rt, market)
    market.advance()
    await rt._cycle_once()
    precio = market._candles[market.cursor - 1].close
    rt._planned_exit["stop"] = round(precio * 0.9995, 2)  # el stop se repone cerca del precio en el próximo ciclo
    market.advance()
    await rt._cycle_once()
    antes = vista(rt, eng)
    nivel = antes["stops_en_reposo"][0]["precio"]  # el nivel REAL del stop en reposo antes de la acción
    if accion == "kill":
        resultado = await rt.kill_switch(reason="experimento", actor="experimento")
    else:  # cierre de emergencia cuyo cierre a mercado rechaza el venue
        real = eng._should_reject
        eng._should_reject = lambda order: True if order.reduce_only and order.order_type is OrderType.MARKET else real(order)
        resultado = await rt.emergency_flatten(reason="experimento", actor="experimento")
        eng._should_reject = real
    despues = vista(rt, eng)
    barras = []
    for _ in range(200):
        market.advance()
        vela = market._candles[market.cursor - 1]
        await rt._cycle_once()
        v = vista(rt, eng)
        barras.append({"minimo": vela.low, "cruza_nivel": vela.low <= nivel, "posicion": v["posicion"],
                       "stops": len(v["stops_en_reposo"]), "estado": v["estado"]})
        if any(b["cruza_nivel"] for b in barras) and len(barras) >= 3:
            break
    cruces = [i for i, b in enumerate(barras) if b["cruza_nivel"]]
    out = {"arbol": arbol.name, "accion": accion, "nivel_stop": nivel, "antes": antes, "resultado": resultado, "despues": despues,
           "barras": barras, "primer_cruce": cruces[0] if cruces else None,
           "posicion_tras_el_cruce": barras[cruces[0]]["posicion"] if cruces else None,
           "final": vista(rt, eng)}
    await rt.stop(reason="fin")
    salida.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
    print(json.dumps({k: out[k] for k in ("accion", "nivel_stop", "antes", "despues", "primer_cruce", "posicion_tras_el_cruce")},
                     default=str, ensure_ascii=False))


asyncio.run(main())
