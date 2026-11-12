"""Diagnóstico mecánico de D3 (solo cantidades y estados de órdenes; no imprime precios ni resultados)."""
from datetime import datetime, timezone
import e1_comun as C
from tia.backtest import engine as EM
velas, _ = C.leer_velas()
corte = datetime(2022, 11, 8, tzinfo=timezone.utc)
velas = [v for v in velas if v.open_time < corte]
registro = []
orig = C.MotorE1._sync_protective_stop
def espia(self, provider, leg, current_id, counts):
    if leg is not None and leg.exit_pending is not None and leg.entry_at >= datetime(2022, 11, 4, tzinfo=timezone.utc):
        o = EM._sync(provider.get_order(leg.exit_order_id)) if leg.exit_order_id else None
        pos = provider.portfolio.positions.get(leg.symbol)
        registro.append((leg.exit_pending, leg.quantity, o.quantity if o else None, o.filled_quantity if o else None,
                         o.state.value if o else None, pos.quantity if pos else None))
    return orig(self, provider, leg, current_id, counts)
C.MotorE1._sync_protective_stop = espia
r = C.correr(velas, ("breakout",))
vistos = []
for x in registro:
    if x not in vistos:
        vistos.append(x)
print("estados distintos tras pedir la salida (motivo, cantidad de la pierna, cantidad de la orden, llenado, estado, posición):")
for x in vistos[:8]:
    print("  ", x)
print("barras con la salida pendiente:", len(registro), "| lote del instrumento: 1e-05")
