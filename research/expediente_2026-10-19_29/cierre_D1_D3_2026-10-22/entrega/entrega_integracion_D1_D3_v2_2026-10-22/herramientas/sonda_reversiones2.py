import sys, collections
sys.path.insert(0, ".")
import pytest
import tests.unit.test_backtest_order_hygiene as t
import tia.backtest.engine as engine_module
for extra in ({"use_target": False}, {"use_target": False, "trail_atr_multiple": 50.0, "breakeven_after_r": 50.0},
              {"use_target": False, "trail_atr_multiple": 50.0, "breakeven_after_r": 50.0, "entry_order_type": "limit"}):
    mp = pytest.MonkeyPatch()
    mp.setattr(engine_module, "PaperExecutionProvider", t._RejectsEveryCloseTwice)
    mp.setattr(t._RejectsEveryCloseTwice, "attempts", {})
    e = t._run(reject=0.3, partial=0.6, **extra)
    r = e.result
    c = collections.Counter(x.exit_reason for x in r.trades)
    viol = {k: len(v) for k, v in e.violations.items() if v}
    print(f"{extra} trades={len(r.trades)} expired={r.decisions.orders_expired} maxint={max(t._RejectsEveryCloseTwice.attempts.values(), default=0)} reasons={dict(c)} viol={viol}")
    mp.undo()
