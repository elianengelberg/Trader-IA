import sys, collections
sys.path.insert(0, ".")
import pytest
import tests.unit.test_backtest_order_hygiene as t
import tia.backtest.engine as engine_module
for mh in (0, 6, 12, 24):
    for entry in ("market", "limit"):
        mp = pytest.MonkeyPatch()
        mp.setattr(engine_module, "PaperExecutionProvider", t._RejectsEveryCloseTwice)
        mp.setattr(t._RejectsEveryCloseTwice, "attempts", {})
        e = t._run(reject=0.3, partial=0.6, entry_order_type=entry, max_holding_bars=mh)
        r = e.result
        c = collections.Counter(x.exit_reason for x in r.trades)
        viol = {k: len(v) for k, v in e.violations.items() if v}
        print(f"max_holding={mh:2d} entry={entry:6s} trades={len(r.trades)} expired={r.decisions.orders_expired} maxint={max(t._RejectsEveryCloseTwice.attempts.values(), default=0)} reasons={dict(c)} viol={viol}")
        mp.undo()
