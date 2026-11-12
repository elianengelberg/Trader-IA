"""Sonda: cuántas barras y escrituras hacen falta para abrir posición en E12, en un árbol dado."""
import asyncio
import sys
from collections import Counter
from pathlib import Path

arbol = Path(sys.argv[1])
sys.path[:0] = [str(arbol / "packages/tia/src"), str(arbol)]
from tests.integration.test_account_restore import build, open_position  # noqa: E402

kinds = Counter()


async def persist(kind, payload):
    kinds[kind] += 1
    if kind == "fill":
        raise OSError("inyectado")


async def main():
    rt, eng, market, _ = build(persist=persist)
    await rt.start()
    await open_position(rt, market)
    await rt.flush_persistence(timeout_seconds=5)
    print("barras", rt.counters["bars"], "estado", rt.machine.state.value, "escrituras", dict(kinds))
    hist = rt.machine.as_dict()["history"]
    print("transiciones", [(h["from"], h["to"], h["reason"][:80]) for h in hist[3:12]])
    await rt.stop()

asyncio.run(main())
