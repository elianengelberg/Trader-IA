import sys
sys.path.insert(0, "tests/unit")
import tia.backtest.engine as em
import test_backtest_order_hygiene as T
em.PaperExecutionProvider = T._ImmediateOrCancelCloses
e = T._run(reject=0.0, partial=0.9, max_holding_bars=T.TIME_STOP_BARS)
tr = e.result.trades
por = {}
for t in tr:
    por.setdefault(t.signal_id, []).append(t)
largos = {k: v for k, v in por.items() if max(x.bars_held for x in v) > 12}
print("trades", len(tr), "legs", len(por), "legs >12 bars", len(largos), "hygiene", e.order_hygiene)
for k, v in list(largos.items())[:3]:
    print(k, [(x.bars_held, x.exit_reason, round(x.quantity, 6)) for x in v])
