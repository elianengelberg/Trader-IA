"""Pruebas SINTÉTICAS para validar la sonda R19 v2 (no son del producto; fallan a propósito)."""
import asyncio

from tests.integration.test_account_restore import build


async def settle(runtime, plazo):
    assert await runtime.flush_persistence(timeout_seconds=plazo), "persistence writes still in flight"


def con(persist):
    runtime, *_ = build(persist=persist)
    return runtime


async def test_lenta_con_productor():
    async def persist(kind, payload):
        await asyncio.sleep(0.2)
    runtime = con(persist)
    await runtime.start()
    for i in range(10):
        runtime._save("fill", {"i": i})
    await settle(runtime, 0.3)


async def test_trabada():
    nunca = asyncio.Event()
    async def persist(kind, payload):
        if payload.get("trabar"):
            await nunca.wait()
    runtime = con(persist)
    await runtime.start()
    runtime._save("order", {"trabar": True})
    await settle(runtime, 0.2)


async def test_errores_inyectado_y_no_inyectado():
    async def persist(kind, payload):
        if payload.get("x") == 1:
            raise RuntimeError(f"database unavailable during {kind}")
        if payload.get("x") == 2:
            raise ValueError("boom")
    runtime = con(persist)
    runtime._save("fill", {"x": 1})
    runtime._save("order", {"x": 2})
    await settle(runtime, 2.0)


async def test_vaciado_que_no_pide_settle():
    async def persist(kind, payload):
        await asyncio.sleep(0.5)
    runtime = con(persist)
    runtime._save("fill", {})
    async def otro_llamador():
        return await runtime.flush_persistence(timeout_seconds=0.05)
    assert not await otro_llamador()
    await settle(runtime, 5.0)
