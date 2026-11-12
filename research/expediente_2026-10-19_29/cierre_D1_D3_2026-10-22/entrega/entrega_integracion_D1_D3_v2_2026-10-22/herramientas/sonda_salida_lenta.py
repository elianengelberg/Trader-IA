"""Sonda (solo lectura): reproduce el escenario combinado y rastrea barra a barra la pierna cuya salida tardó."""
import asyncio, sys
sys.path.insert(0, "tests/unit"); sys.path.insert(0, ".")
import pytest
import tests.unit.test_backtest_order_hygiene as t
import tia.backtest.engine as engine_module

objetivo = sys.argv[1]
class Traza(t._Instrumented):
    def _sync_protective_stop(self, provider, leg, current_id, counts, **kw):
        out = super()._sync_protective_stop(provider, leg, current_id, counts, **kw)
        if leg is not None and leg.signal_id == objetivo:
            ordenes = [o for o in asyncio.run(provider.get_orders()) if o.symbol == leg.symbol and (o.reduce_only or o.order_type.value == "stop")]
            ult = sorted(ordenes, key=lambda o: o.created_at)[-4:]
            pos = provider.portfolio.positions.get(leg.symbol)
            print(f"barra {self.bar}: pierna {leg.direction.value} q={leg.quantity:.6f} exit_pending={leg.exit_pending!r} exit_order={leg.exit_order_id[-8:] if leg.exit_order_id else ''} stop={out[-8:] if out else None} venue={pos.quantity if pos else 0:.6f}")
            for o in ult:
                print(f"     {o.order_id[-8:]} {o.order_type.value:6s} {o.side.value:4s} ro={o.reduce_only} q={o.quantity:.6f} fill={o.filled_quantity:.6f} {o.state.value:16s} sig={o.signal_id[:40]}")
        return out
mp = pytest.MonkeyPatch()
mp.setattr(engine_module, "PaperExecutionProvider", t._RejectsEveryCloseTwice)
mp.setattr(t._RejectsEveryCloseTwice, "attempts", {})
e = t._run(reject=0.3, partial=0.6, entry_order_type="limit", max_holding_bars=t.TIME_STOP_BARS, engine=Traza)
print({k: len(v) for k, v in e.violations.items()})
print("intentos por cierre (máx):", max(t._RejectsEveryCloseTwice.attempts.values()))
for k, v in sorted(t._RejectsEveryCloseTwice.attempts.items()):
    if objetivo in k: print("  ", k, v)
