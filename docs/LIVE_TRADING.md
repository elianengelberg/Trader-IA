# Live trading

This document is about the point where the system stops being a simulation and starts
spending your money. Read all of it before you get there.

---

## The one-paragraph version

Your funds stay at Binance. This application has no wallet, takes no custody, and cannot
withdraw or transfer anything — there is no code path for it, and the API key you create
must not have the permission either. What it can do, once you deliberately arm it, is place
and cancel spot orders on your behalf, within a capital ceiling you set. It can lose money
doing that. Nothing here prevents that, and nothing in this repository is evidence that it
won't.

---

## 1. What the system can and cannot do

| | |
|---|---|
| **Can** | Read public market data |
| **Can** | Read your account balance and open orders |
| **Can** | Place and cancel spot orders, up to `MAX_LIVE_CAPITAL` |
| **Cannot** | Withdraw funds — no code path exists |
| **Cannot** | Transfer between wallets, sub-accounts, or to anyone else |
| **Cannot** | Hold, receive, or store your money |
| **Cannot** | Use leverage, margin or futures |
| **Cannot** | Change its own risk limits or capital ceiling |

The "cannot" rows are enforced three ways, deliberately overlapping so a mistake in any one
of them is not sufficient:

1. **No code.** `tests/unit/test_scope_boundary.py` fails the build if any source file in
   the package so much as names a withdrawal or transfer endpoint. That test has no
   allowance list and is not getting one.
2. **No permission.** `tia/live/permissions.py` reads what the key is allowed to do from
   Binance and refuses to trade if the answer includes moving funds — including
   permissions it does not recognise, if their names suggest fund movement.
3. **No custody.** There is no account this system could pay into. The only address your
   funds can be at is your own Binance account.

---

## 2. The two-stage risk model

A signal passes through five gates before it becomes an order. Each answers a different
question and any one of them can refuse:

```
signal → data quality → risk engine → risk budget → cost model → expected value → order
             ↓               ↓             ↓            ↓              ↓
      "is this data      "is this     "how much     "what will    "is what's left
        trustworthy?"   survivable?"  right now?"   it cost?"      worth taking?"
```

The last two are the ones most trading systems do not have, and they refuse far more often
than the risk engine does.

### The risk budget

Answers *how much*, from three multipliers that are each capped at 1.0 and none of which
ever rises because the account is losing:

- **Drawdown state** — `NORMAL → DEFENSIVE → EMERGENCY`. Risk tapers smoothly as drawdown
  deepens and reaches zero at the emergency threshold, where the system stops opening
  positions entirely.
- **Volatility scaling** — position size falls as realised volatility rises, so a fixed
  *fractional* risk stays a fixed *monetary* risk. Capped at 1.0: a quiet market does not
  license a bigger position than the profile allows.
- **Loss streak** — after N consecutive losses the budget halves, and keeps halving.

`assert_no_martingale` asserts over randomised inputs that risk never increases with
drawdown or with another loss. Martingale, revenge trading and "size up to recover" are the
same behaviour under three names, and this is the property that forbids all of them.

> A note on how that property earned its keep: it found a real defect. The `aggressive`
> profile's budget **rose by 6%** as drawdown crossed 8%, because the normal-state taper
> ended at a hardcoded 0.5 while the defensive state began at the profile's own 0.6. No
> example-based test would have caught it — the balanced profile, which every hand-written
> test used, happened to line up exactly.

### The expected value engine

Answers *is it worth it*:

```
net edge = expected gross edge − round-trip costs
trade only if net edge ≥ threshold
```

The hard part is the first term, and it is where trading systems lie to themselves. A
confidence score is not a probability. Multiplying it by a target produces a random number
with an equals sign in front of it. So the edge here comes from **realised outcomes**:
past trades bucketed by `(regime, direction, confidence band)`, requiring at least 30
closed trades in a bucket before it will produce any estimate at all, and shrinking the
bucket mean toward zero by its own standard error.

Below 30 samples it returns nothing, and the caller must treat that as NO_TRADE. **A fresh
system trades nothing until it has evidence.**

### The cost model

Prices a **round trip**, itemised, because a one-way estimate flatters every strategy that
has to get out again:

| Component | What it is |
|---|---|
| Fees | The venue's commission, both legs |
| Spread | You buy at the ask and sell at the bid |
| Slippage | The gap between the price you decided on and the price you got |
| Latency | The market moving between the decision and the fill |
| Impact | Your own order moving the price against you |

Every choice point is conservative. When book depth is unknown the model does not assume
infinite liquidity — it prices a volatility-scaled floor, because "we could not see the
book" is a reason for more caution, not less.

---

## 3. The number that decides whether any of this is worth doing

At Binance's standard 10 bps taker fee, a round trip costs **20 bps in fees alone**, before
spread, slippage, latency or impact. Add those and a realistic round trip on BTC/USDT is
roughly **22–23 bps**.

So a strategy must produce **more than ~25 bps of gross edge per trade** just to break even.

The first run of the expected-value engine on this system's own numbers produced:

```
expected gross   23.37 bps   (from 200 past trades)
round-trip cost  22.92 bps   (fees dominant)
net               0.45 bps   → NO_TRADE (threshold 5.00 bps)
```

That is not a bug and it is not pessimism. It is the arithmetic that most retail strategies
never do, and it is why so many backtests that look profitable are not. **A strategy that
does not clear this number does not work, no matter how good its win rate looks.**

The honest implication: high-frequency retail crypto strategies are structurally difficult
at these fee levels. Fewer, larger, higher-conviction trades clear the bar more easily than
many small ones, because the cost is per-round-trip and does not shrink with holding time.

---

## 4. Paper mode observes, live mode enforces

There is a circularity in the design and it is worth understanding rather than being
surprised by:

- The EV engine refuses to trade without a measured edge.
- An edge is measured from closed trades.
- Enforcing that in paper mode means: no trades → no evidence → no trades. Forever.

The resolution is the one the design always assumed: **paper trading is how the evidence is
produced without risking money.** So:

| Mode | EV engine | What happens |
|---|---|---|
| `paper`, `backtest` | **Observing** | Prices every decision, records the full arithmetic, counts what it *would* have refused. The trade proceeds and its outcome becomes a sample. |
| `live` | **Enforcing** | A signal without a measured edge that clears its costs does not become an order. |

The counter to watch while observing is `ev_would_reject`. **If it stays near the signal
count once the buckets have filled, the strategy does not clear its own costs, and turning
enforcement on would stop it trading entirely.** That is a finding about the strategy, not a
malfunction of the engine.

---

## 5. The Live Activation Gate

Fourteen checks. Every one must pass, and **a check that reports nothing counts as failed** —
absence is failure, never neutral, because the most dangerous check is the one nobody wired
up.

| Check | What it prevents |
|---|---|
| `tests_pass` | Trading on a commit whose suite was never run |
| `market_data_healthy` | Trading on a market that no longer exists |
| `venue_connected` | Sending an order into a dropped connection |
| `database_healthy` | A restart that cannot tell a sent order from an unsent one |
| `execution_healthy` | Opening a position it cannot close |
| `risk_engine_healthy` | Nothing stopping a bad trade |
| `reconciliation_healthy` | Sizing off the wrong picture of the account |
| `security_review` | A leaked key — a total loss, not a degraded service |
| `fees_verified_at_source` | A fee tier guessed 5 bps low, which flatters everything |
| `capital_policy_set` | Risking whatever happens to be in the account |
| `kill_switch_clear` | Discarding the reason something halted |
| `credentials_scoped` | A key that can withdraw |
| `edge_evidence` | Going live with no measured edge |
| `paper_track_record` | Discovering the first reconnect in production |

Passing the gate means **the machinery is in a known state**. It does not mean the strategy
is profitable, and the report says so in those words.

### Three properties of the activation token

**It cannot be forged.** There is no boolean anywhere meaning "allowed to trade live". The
only evidence is a `LiveActivationToken`, and its constructor refuses outside the gate
module. A test asserts this.

**It expires.** One hour by default, six maximum. A gate that passed at nine says nothing
about eleven, and it is re-validated on *every order* rather than once at construction — so
an expiry stops the next order rather than being noticed at the next restart.

**It is bound to the configuration it was issued against.** The token carries a fingerprint
of the active risk limits and capital policy. If either changes after arming, by any
mechanism at all, the token is void. This is the structural half of "the system may propose
limit changes and may never apply them": even if something did apply one, it could not then
trade on it.

---

## 6. Going live, step by step

Do these in order. Each step exists because skipping it has cost someone money.

### Step 1 — Run the suite

```bash
make verify
```

Writes `data/runtime/verify_passed.json`, which is what satisfies the gate's `tests_pass`
check. A file from a separate process on purpose: a check the API could satisfy from its
own memory is a check the API could satisfy by being wrong.

### Step 2 — Create a Binance API key

**Binance → Account → API Management → Create API.**

Enable **only**:

- [x] Enable Reading
- [x] Enable Spot & Margin Trading

Leave **disabled** — this is the part that matters:

- [ ] Enable Withdrawals
- [ ] Enable Internal Transfer
- [ ] Permits Universal Transfer
- [ ] Enable Futures
- [ ] Enable Margin

Restrict the key to your server's IP address. It is the cheapest reduction in blast radius
available.

Binance shows the secret exactly once. If you lose it, delete the key and make another. If
you ever paste it anywhere by accident — including into a chat with an AI assistant —
delete the key immediately. That is the whole remedy and it takes thirty seconds.

### Step 3 — Configure

In `.env` (never in a committed file, never through the web interface):

```bash
TIA_LIVE__BINANCE_API_KEY=...
TIA_LIVE__BINANCE_API_SECRET=...
TIA_LIVE__MAX_LIVE_CAPITAL=100        # start small. An amount you would be fine losing.
TIA_LIVE__USE_TESTNET=true            # keep this true for now
TIA_LIVE__RISK_PROFILE=conservative
```

### Step 4 — Validate against the venue

```bash
python scripts/validate_binance.py --account --json-out data/runtime/binance_validation.json
```

This is not optional and it is not a formality. Every endpoint path, parameter name and
response field in the Binance adapters was written from documentation and **has never been
exercised** — the environment they were built in blocks every Binance host. The script
turns each of those assumptions into a checked fact or a named failure. It specifically
checks:

- the kline array's positional layout (a reordering produces candles that parse cleanly and
  are wrong);
- clock skew against the venue (signed requests are rejected outside `recvWindow`, and the
  error does not mention the clock);
- the real fee tier from your account;
- what your API key is actually permitted to do;
- **whether the venue really rejects a duplicate client order id** — if it does not,
  venue-side idempotency cannot be relied on and a retry after a timeout could open a
  second position.

### Step 5 — Testnet

```bash
python scripts/validate_binance.py --account --order --testnet
```

`--order` requires `--testnet` and the restriction is not overridable. Run the system
against the testnet for long enough to exercise its failure paths — a disconnect, a
restart, a rejected order.

### Step 6 — Paper, on real prices, for real time

`TIA_LIVE__MIN_PAPER_DAYS` and `TIA_LIVE__MIN_PAPER_TRADES` gate this. Thirty closed round
trips is the floor for the edge estimator to produce any number at all; it is not a lot.

### Step 7 — Read the gate, then arm

The **Live Trading** page shows all fourteen checks with their verdicts and remedies. When
every one passes, type the confirmation phrase exactly. It is long on purpose — a
confirmation that can be produced by hitting Enter is not a confirmation.

Start with the smallest `MAX_LIVE_CAPITAL` that produces a valid order size.

---

## 7. What will go wrong

Not "might". These are the ones worth expecting.

**A timeout on order submission.** Common. The order's state is genuinely unknown — the
venue may or may not have it. The adapter does *not* retry, because retrying after a timeout
is how one signal becomes two positions. It raises, and reconciliation resolves what
actually happened by querying the venue. If you see this, do not "just restart it".

**The fee tier being different from what you assumed.** This is why the gate refuses to arm
until fees are read from the account. A tier 5 bps below reality turns a losing strategy
into a winning-looking one, and every downstream number inherits the error.

**A strategy that worked in paper not working live.** Slippage and spread on real fills are
worse than any simulator's model, latency is real, and your own orders move thin books. The
cost model here is deliberately pessimistic for exactly this reason, and it will still be
optimistic sometimes.

**A drawdown deeper than the backtest's worst.** The backtest's maximum drawdown is a
sample from a distribution, not a bound. The ruin analytics page exists to show you the rest
of that distribution.

---

## 8. What this system will never do

- Guarantee a profit. It cannot, nobody can, and any system that claims otherwise is lying
  to you.
- Guarantee zero losses.
- Guarantee zero bugs.
- Withdraw or transfer your funds.
- Store your funds.
- Put an API secret in the frontend, in a log, in a database, or in a response body.
- Let a language model modify the risk engine, the risk limits, or the capital ceiling.
- Trade on data it knows is invalid.
- Trade when the state of a previous order is unknown.
- Use Martingale, revenge trading, or increase risk to recover a loss.
- Trade merely to increase the number of trades.
