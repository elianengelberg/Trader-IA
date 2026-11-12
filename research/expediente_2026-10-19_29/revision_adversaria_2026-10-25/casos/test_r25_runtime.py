"""R25 a nivel de runtime (sin red): la sesión del vivo con un venue de papel que, como el adaptador de Binance, rechaza
OrderType.STOP con ExecutionError «not supported» ANTES de enviarlo. Mismo procedimiento que
test_every_open_position_gets_exactly_one_protective_stop (tests/integration/test_live_runtime.py), que con el venue de
papel normal exige 1 stop y position.protected=True. Aquí se OBSERVA qué hace la sesión; las aserciones describen el
comportamiento esperado de un sistema seguro y deben FALLAR si R25 es real."""
from __future__ import annotations

import pytest

from tests.integration.test_live_runtime import _open_a_position, build_runtime_paper
from tia.core.errors import ExecutionError
from tia.domain.enums import OrderType

OBSERVADO: dict = {}


async def test_r25_la_sesion_frente_a_un_venue_que_no_acepta_stop() -> None:
    runtime, execution, market = build_runtime_paper()
    original = execution.submit_order
    rechazos = []

    async def como_binance(intent):  # type: ignore[no-untyped-def]
        if intent.order_type is OrderType.STOP:
            rechazos.append(intent.client_order_id)
            raise ExecutionError(f"order type {intent.order_type.value} is not supported by this adapter; "
                                 "it is not in the documented spot order-type set", order_type=intent.order_type.value)
        return await original(intent)

    execution.submit_order = como_binance  # type: ignore[method-assign]
    await runtime.start()
    try:
        await _open_a_position(runtime, execution, market)
        for _ in range(5):  # cinco barras de gestión de la posición
            market.advance()
            await runtime._cycle_once()
        snap = runtime.snapshot()
        position = await execution.get_positions()
        OBSERVADO.update({
            "posicion_abierta": {k: float(v.quantity) for k, v in position.items() if not v.is_flat},
            "stops_en_el_venue": sum(1 for o in execution.orders.values() if o.order_type is OrderType.STOP),
            "intentos_de_stop_rechazados": len(rechazos),
            "counters.stops_placed": runtime.counters.get("stops_placed"),
            "counters.unprotected_positions": runtime.counters.get("unprotected_positions"),
            "snapshot.position.protected": (snap.get("position") or {}).get("protected"),
            "estado": str(runtime.machine.state), "last_error": runtime.last_error,
        })
        print("\nOBSERVADO:", OBSERVADO)
        # Lo que un sistema seguro debería cumplir (esperado: FALLA si R25 es real)
        assert OBSERVADO["snapshot.position.protected"] is not True, "la instantánea declara protegida una posición sin stop"
        assert OBSERVADO["counters.unprotected_positions"], "la posición sin stop no se cuenta como desprotegida"
    finally:
        await runtime.stop()
