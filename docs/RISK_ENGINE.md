# The risk system

Four layers, each answering a different question. Any one of them can refuse, and none of
them can be overridden by anything downstream — including a language model, including the
UI, including a configuration change made while the system is running.

```
     is this data trustworthy?   →  Data Quality Engine
     is this trade survivable?   →  Risk Engine          (absolute veto)
     how much, right now?        →  Risk Budget
     is what's left worth it?    →  Expected Value Engine
```

---

## 1. The Risk Engine: absolute veto

Deterministic. It is not a language model, it never asks one, and nothing downstream can
override it.

It may only ever **shrink** a requested size. An engine that could grow one would be a
second, unreviewed sizing model wearing a safety label.

Its limits (`RiskLimits`) are a frozen model. Assigning to any field raises
`RiskLimitImmutableError`. The system may *propose* a limit change — `propose_change()`
returns a copy — and may never *apply* one. The path from proposal to configuration goes
backtest → out-of-sample validation → shadow test → human approval → versioned config
change, and there is no API route that shortens it.

---

## 2. The Risk Budget: how much

Three multipliers, each capped at 1.0. The cap matters: a multiplier that can exceed 1.0 is
a mechanism for the system to take more risk than its profile allows, and it will eventually
find a way to.

### Drawdown state

| State | Trigger | Effect |
|---|---|---|
| `NORMAL` | drawdown < defensive threshold | Budget tapers from 1.0 toward the defensive multiplier |
| `DEFENSIVE` | drawdown ≥ defensive threshold | Budget tapers from the defensive multiplier to 0 |
| `EMERGENCY` | drawdown ≥ emergency threshold | **No new positions.** Not a smaller size — none. |

Two straight lines that meet exactly at the defensive threshold. Both segments are anchored
to the profile's own `defensive_multiplier`, so they join for every profile.

> This was a real bug. The normal-state taper used to end at a hardcoded 0.5 while the
> defensive state began at the profile's `defensive_multiplier`. For `balanced` (0.5) they
> met; for `aggressive` (0.6) they did not, and the budget **rose by 6%** as drawdown
> crossed 8%. That is martingale behaviour arriving by arithmetic rather than by intent —
> the kind that survives review, because every hand-written test used the one profile where
> the numbers happened to line up. The property test found it in about three hundred
> examples.

Emergency stops trading rather than shrinking it because a very small position is still a
position, and the emergency state exists because the evidence says stop, not slow down.

### Volatility scaling

```
multiplier = min(1.0, target_annual_volatility / realised_annual_volatility)
```

So a fixed *fractional* risk stays a fixed *monetary* risk as the market's volatility
changes. Capped at 1.0 because uncapped volatility targeting is how a quiet market builds
leverage that a single gap erases.

A realised volatility of zero means "not measured yet", and is treated as a multiplier of
1.0 rather than as "the market is calm" — the optimistic reading of missing data is the one
to avoid.

### Loss streak

After `consecutive_loss_dampener` losses in a row, the budget halves. And keeps halving:
0.5, 0.25, 0.125, floored at 0.05.

A losing streak is evidence the strategy is out of step with the market. The response is a
smaller position. The opposite response is the one that empties accounts.

### Profiles

| | Conservative | Balanced | Aggressive |
|---|---|---|---|
| Risk per trade | 0.25% | 0.50% | 1.00% |
| Defensive at | 3% | 5% | 8% |
| Emergency at | 6% | 10% | 15% |
| Max gross exposure | 40% | 80% | 120% |
| Target volatility | 10% | 20% | 35% |
| Max trades/day | 8 | 20 | 40 |

Every field moves together. Scaling one and leaving the others is how a "conservative"
profile ends up with a conservative position size and an aggressive drawdown tolerance —
and labelling bugs in risk parameters are the expensive kind. `assert_profiles_are_ordered`
checks conservative ≤ balanced ≤ aggressive on every dimension.

---

## 3. The no-Martingale property

Martingale, revenge trading and "increase size to recover the drawdown" are the same
behaviour under three names. All three are forbidden by one property:

> **Risk never increases because the account is losing.**

Stated as a checkable function rather than a comment, because "we would never do that" is
exactly what every blown-up account's code said:

```python
def assert_no_martingale(engine, inputs):
    deeper = replace(inputs, drawdown_pct=inputs.drawdown_pct + 1.0)
    if engine.compute(deeper).risk_currency > engine.compute(inputs).risk_currency:
        raise AssertionError("risk increased with drawdown — martingale, forbidden")

    longer = replace(inputs, consecutive_losses=inputs.consecutive_losses + 1)
    if engine.compute(longer).risk_currency > engine.compute(inputs).risk_currency:
        raise AssertionError("risk increased after a loss — revenge trading, forbidden")
```

Hypothesis searches for a counterexample across equity, drawdown, volatility, streak length,
trade count, exposure and all three profiles. There must be none. This is the property that
caught the taper discontinuity above.

---

## 4. Probability of ruin

A positive expectancy is not protection. Betting too much of a winning edge goes bankrupt
with probability approaching one — the single most common way a *correct* edge produces a
zero balance, and nothing in a Sharpe ratio warns about it.

**Ruin is defined as equity below 50% of its starting value**, not zero. An account is
finished long before zero: position sizes shrink with equity, the strategy stops being
viable, and a halved account needs a 100% gain to recover. Almost none do. The threshold is
stated in every result rather than left implicit.

Two estimates, deliberately both:

- **Analytic** — closed form for fixed-fractional betting. Instant, and a sanity check on
  the simulation.
- **Monte Carlo** — resamples the actual trade distribution. Makes no distributional
  assumption, and is the one to trust when they disagree, because real trade returns are
  neither normal nor independent enough for the closed form to be exact.

Every simulation is **seeded**. A risk number that changes each time you look at it is not a
risk number.

### Where the estimate is optimistic

The bootstrap samples with replacement, which assumes trades are exchangeable. That is wrong
when returns are autocorrelated, and wrong in the flattering direction: **resampling breaks
up losing streaks, and losing streaks are what actually empty accounts.**

So the result reports `longest_losing_streak` alongside the probability, making that
optimism visible rather than leaving it in a docstring. If your strategy strings losses
together more tightly than the bootstrap does, the true ruin probability is higher than the
number shown.

### Safe sizing

`max_safe_risk_fraction` searches a fixed ladder — 0.25%, 0.5%, 0.75%, 1%, 1.5%, 2%, 3%, 5%
— for the largest per-trade risk whose simulated ruin probability stays under 1%. A ladder
rather than a continuous optimisation because the input distribution does not support
three-decimal precision, and printing "1.37%" would imply it does.

It returns `None` when even the smallest candidate ruins too often. That is a real answer,
not a failure to compute one, and it means: **do not trade this.**

---

## 5. Capital accounting

The error this prevents has a direction. People deposit after losses far more often than
they withdraw after gains, so a system that counts a balance increase as profit does not
produce a *noisy* performance figure — it produces a systematically flattering one, and it
flatters most exactly when the strategy is doing worst.

```
equity = allocated capital + realised P&L + unrealised P&L − fees
return = (realised + unrealised) / net contributed        ← never divided by starting balance
```

**A balance change at the venue is never assumed to be trading P&L.** Trading P&L arrives
through fills, which the system already knows about. Anything left over came from somewhere
else:

| Difference | Classification | Trading |
|---|---|---|
| Within tolerance | Rounding | Continues |
| Increase, no matching fill | Deposit — *not* profit | Continues |
| Decrease, no matching fill | Withdrawal — *not* a loss | Continues |
| More than 10% of the ceiling | **Unexplained** | **Halted** |

A system that does not know how much money it has cannot size a position. Clearing the halt
requires a named approver — an unattributed override is one nobody decided to make.

`max_live_capital` is a hard ceiling, and allocating above it is **refused rather than
truncated**: silently allocating less than asked is how someone ends up believing the system
is trading half of what it is, or twice.

---

## 6. Expected value

See `docs/LIVE_TRADING.md` §2 for the full treatment. The short version:

- The edge comes from **realised outcomes**, bucketed by `(regime, direction, confidence
  band)`. Never from the confidence score, which is a number on an arbitrary scale until
  something has demonstrated what it means.
- A bucket needs **30 closed trades** before it produces any estimate at all. Below that it
  returns nothing, and the caller must treat that as NO_TRADE.
- The bucket mean is shrunk toward zero by its own standard error, so eleven trades that
  averaged +40 bps do not get to claim +40 bps.
- Costs are subtracted for a **round trip**, itemised across fees, spread, slippage, latency
  and impact.
- A trade whose costs exceed 60% of its expected edge is refused even when the absolute net
  is positive — netting 6 bps out of 200 is fine, netting 6 out of 30 is a coin flip on the
  cost model being exactly right, and the cost model is an estimate too.
