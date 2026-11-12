import sys, collections
sys.path.insert(0, ".")
import pytest
import tests.unit.test_backtest_order_hygiene as t
import tia.backtest.engine as engine_module
import tia.strategy.library as library
from tia.backtest import BacktestConfig
from tia.core.config import ExecutionSimConfig
from tia.domain.instruments import DEFAULT_UNIVERSE

for adx, mult in ((22.0, 6.0), (15.0, 8.0), (10.0, 12.0)):
    class Wide(library.TrendFollowingStrategy):
        def __init__(self, **kw):
            super().__init__(adx_threshold=adx, atr_stop_multiple=mult)
    for rej, part in ((0.0, 0.0), (0.3, 0.6)):
        mp = pytest.MonkeyPatch()
        mp.setitem(library.STRATEGY_REGISTRY, "trend_following", Wide)
        mp.setattr(engine_module, "PaperExecutionProvider", t._RejectsEveryCloseTwice)
        mp.setattr(t._RejectsEveryCloseTwice, "attempts", {})
        e = t._Instrumented(BacktestConfig(dataset="fixtures", timeframe="1h", warmup_bars=120,
                execution=ExecutionSimConfig(reject_probability=rej, partial_fill_probability=part),
                use_target=False, trail_atr_multiple=50.0, breakeven_after_r=50.0, entry_order_type="limit"),
                DEFAULT_UNIVERSE, strategies=("trend_following",))
        r = e.run(t.SERIES)
        c = collections.Counter(x.exit_reason for x in r.trades)
        viol = {k: len(v) for k, v in e.violations.items() if v}
        print(f"adx={adx} mult={mult} rej={rej} part={part} trades={len(r.trades)} expired={r.decisions.orders_expired} maxint={max(t._RejectsEveryCloseTwice.attempts.values(), default=0)} reasons={dict(c)} viol={viol}")
        mp.undo()
