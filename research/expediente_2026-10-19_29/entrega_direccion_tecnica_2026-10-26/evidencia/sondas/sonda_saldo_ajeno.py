"""Sonda: una cuenta que ya tiene BTC que la sesión no compró. ¿Qué hace la sesión?"""
import asyncio
import sys
from pathlib import Path

arbol = Path(sys.argv[1])
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
from tests.integration.test_live_runtime import FakeExecution, build_runtime  # noqa: E402
from tia.domain.portfolio import Position  # noqa: E402


async def main():
    execution = FakeExecution()
    runtime, _, market = build_runtime(execution=execution)
    execution.positions["BTC-USD"] = Position(symbol="BTC-USD", quantity=0.5, average_price=0.0)
    await runtime.start()
    for _ in range(5):
        market.advance()
        await runtime._cycle_once()
    orders = [(o.side.value, o.order_type.value, o.quantity) for o in execution._orders.values()] if hasattr(execution, "_orders") else "n/a"
    print("estado", runtime.machine.state.value, "| bloqueos", dict(runtime.entry_blocks), "| incidentes/errores", runtime.last_error[:200])
    print("órdenes enviadas", orders, "| envíos", execution.submissions)
    print("posición vista por la sesión", runtime._open_trade)
    await runtime.stop()

asyncio.run(main())
