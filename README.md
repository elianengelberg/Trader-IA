# Trader-IA

Quantitative research, backtesting and autonomous trading. **Paper by default; live only
through a gate that has to actually pass.**

Whichever mode it runs in, two things are unconditionally true:

**Your money never leaves your exchange account.** This application has no wallet, takes no
custody, and never receives a deposit. In live mode it places and cancels spot orders
against your own Binance account; that is the entire relationship.

**It cannot withdraw or transfer anything.** Not "does not" — cannot. There is no code path
for it, a test fails the build if one is added, and the API key you create must not have the
permission either. Three independent barriers, none relying on the others.

Nothing here is a prediction or a recommendation, and nothing in this repository is evidence
that any strategy is profitable.

> **The number that decides whether this is worth doing.** At Binance's standard 10 bps
> taker fee, a round trip costs 20 bps in fees alone — closer to 23 with spread, slippage
> and latency. A strategy must produce more than ~25 bps of gross edge *per trade* just to
> break even. The Expected Value Engine computes exactly this before every order and refuses
> the ones that do not clear it. Most signals do not clear it. That is the arithmetic most
> retail strategies never do, and it is why so many profitable-looking backtests are not.

---

## Run it

Needs Python 3.11+ and Node 18+. Nothing else — no database server, no message broker, no
API key, no network.

```bash
git clone <this repository> && cd Trader-IA

make install     # venv, Python dependencies, dashboard build
make diagnose    # says exactly what is present and what is missing
make demo        # http://127.0.0.1:8000
```

Then, in the dashboard: pick a scenario, choose a simulated capital, press **Start paper
trading**. The system generates market data, analyses it, forms signals, asks the context
layer, passes everything through the risk engine, creates orders, fills them in the
simulator, and shows every step as it happens.

**Credentials.** Set `TIA_DEMO_USER` and `TIA_DEMO_PASSWORD` before starting. If you do
not, the server generates a password at startup and prints it once to its own log — there
is no default password, because a demo whose password is `admin/admin` is a demo that gets
deployed with `admin/admin`.

```bash
TIA_DEMO_USER=me TIA_DEMO_PASSWORD='choose-something' make demo
```

### With Docker

```bash
docker compose up --build     # http://127.0.0.1:8000
```

**Status: REQUIRES VALIDATION.** The compose file and Dockerfile are written and reviewed
but have **never been executed** — the environment they were authored in has no Docker
daemon. Every other instruction on this page was run and its output recorded in
[`AUDIT_REPORT.md`](AUDIT_REPORT.md). This one was not.

---

## Verify it

```bash
make verify   # lint, unit, integration, property, failure, e2e, frontend, browser
make smoke    # start the server, drive the dashboard in a real browser, stop it
make test     # the fast tests only
```

`make verify` prints PASS / FAIL / WARN per area and runs every area even when one fails —
a report that stops at the first failure hides whether the rest works.

---

## What it does

```
market data → data quality gate → features → market regime → strategies → fusion
            → AI context (advisory) → risk engine → risk budget
            → cost model → expected value → order intent
            → execution → fill → position → P&L → dashboard → audit log
```

Three properties define the design.

**The language model cannot create risk.** Its entire response schema is a *caution*
level, converted to a modifier clamped to `[-1, 0]`. There is no field it can return that
opens a trade, enlarges one, chooses a direction, or overrides a limit. A hallucination, a
poisoned news item or a prompt injection can only ever cost trades that would otherwise
have been taken. This is enforced by the type system, re-clamped at the conversion
boundary, and checked by a property test over adversarial inputs.

**The risk engine is deterministic and has absolute veto.** It is not a model, it never
consults one, and nothing downstream can override it. It may only ever *shrink* a
requested size — an engine that could grow one would be a second, unreviewed sizing model.

**A risk-approved signal is still not a trade.** The risk engine answers "is this
survivable?"; it does not answer "is this worth doing?". Two more gates sit between
approval and an order: the risk budget, which decides how much may be risked given the
current drawdown, volatility and losing streak — possibly nothing — and the expected-value
engine, which subtracts the round-trip cost from a *measured* edge and refuses when the
remainder does not clear a threshold. Both refuse far more often than the risk engine does.

Full design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Demo scenarios

Nine, each seeded and reproducible. Three of them are **passing when they produce no
trades at all** — a system that only demonstrates the happy path demonstrates very little.

| Scenario | Shows |
|---|---|
| Sustained uptrend | Trend following finds setups; orders reach fills |
| Sustained downtrend | The same machinery on the short side |
| Range-bound | Mean reversion applies; trend following is excluded by regime |
| Volatility spike | Sizing shrinks, then the volatility gate starts refusing outright |
| News shock | News reaching the context layer; caution rises, position size does not |
| Risk limits bind | Named risk checks refusing trades the strategies wanted |
| **Degraded market data** | The quality gate refusing to trade on a broken feed |
| **Context layer unavailable** | Total loss of the LLM; the deterministic pipeline is unaffected |
| Mixed regimes | Regime transitions and hysteresis over a longer sample |

---

## Using Claude instead of the offline mock

The default provider is a deterministic offline mock. It needs no credential, makes no
network call, and returns the same assessment for the same market state on every machine.
The demo is fully functional without an API key.

To use Claude:

```bash
# in .env, or exported in your shell — never in the source, never in a prompt
TIA_ANTHROPIC_API_KEY=sk-ant-...
TIA_LLM__PROVIDER=anthropic
TIA_LLM__ENABLED=true
```

The key is read by the server process only. It is never placed in a prompt, returned by an
endpoint, or written to a log — `tests/unit/test_llm_layer.py` asserts the first and
`tests/unit/test_api_security.py` asserts the others. If the key is missing while the
Anthropic provider is requested, the system downgrades to the mock with a logged warning
rather than failing to start.

---

## Going live

Paper is the default and stays the default until fourteen activation checks pass and a
human types a confirmation phrase. Read [`docs/LIVE_TRADING.md`](docs/LIVE_TRADING.md)
before you get there — all of it.

```bash
make verify                                    # 1. writes the record the gate reads
                                               # 2. create a Binance key: reading + spot
                                               #    trading ONLY, IP-restricted
vim .env                                       # 3. key, secret, MAX_LIVE_CAPITAL
python scripts/validate_binance.py --account \
  --json-out data/runtime/binance_validation.json   # 4. verify every assumption
python scripts/validate_binance.py --account --order --testnet   # 5. testnet round trip
                                               # 6. paper, on real prices, for real time
                                               # 7. read the gate, then arm
```

Three properties of the activation token are worth knowing up front:

* **It cannot be forged.** There is no boolean anywhere meaning "allowed to trade live".
  The only evidence is a token whose constructor refuses outside the gate module.
* **It expires** — one hour by default — and is re-validated on *every order*, so a lapse
  stops the next order rather than being noticed at the next restart.
* **It is bound to a fingerprint of the active risk limits.** Change a limit after arming,
  by any mechanism, and the token is void.

---

## What is not here, deliberately

* **No custody, deposits, withdrawals, transfers, bank details or card details.** No route
  exists for any of them; a test greps every source file for withdrawal and transfer
  endpoints and fails the build on a match, with no allowance list.
* **No live execution from a configuration flag.** Declaring `is_simulated=False` is not
  enough and never becomes enough — construction requires a token the activation gate
  alone can mint.
* **No risk-limit editing from the interface.** Limits are immutable at runtime and no API
  route changes them. Altering one is a code change that goes through review.
* **No secret through the browser.** `POST /api/live/arm` accepts a confirmation phrase and
  nothing else — no key, no secret, no capital amount.
* **No Martingale, no revenge trading, no sizing up to recover a loss.** Forbidden by a
  property asserted over randomised inputs, not by a comment.
* **No claim of profitability anywhere.** Backtest verdicts are
  `insufficient_evidence`, `no_edge_demonstrated`, `mixed`, `beat_all_baselines` — none of
  which means "good", and the strongest is a statement about one dataset.

---

## Known limitations

Stated here rather than discovered later.

* **The Binance integration has never made a request.** Every Binance host is blocked by
  the build environment's egress proxy, so every endpoint path, parameter name and response
  field in it was written from documentation and confirmed against nothing. It is labelled
  `REQUIRES VALIDATION` in three places and `scripts/validate_binance.py` exists to close
  the gap. **Run it before trusting anything in that adapter.**
  See [`docs/BINANCE_INTEGRATION.md`](docs/BINANCE_INTEGRATION.md).
* **The paper simulator has no order book.** Fills are matched against bar OHLCV, so queue
  position and book depletion do not exist. There are no halts, auctions, funding or borrow
  costs. `docs/ARCHITECTURE.md` §12.1.
* **The expected-value engine observes rather than enforces in paper mode.** Enforcing it
  there is a deadlock — it refuses to trade without a measured edge, and an edge is measured
  from closed trades. Paper trading is how that evidence gets produced. The `ev_would_reject`
  counter shows what enforcing would cost. `docs/LIVE_TRADING.md` §4.
* **No WebSocket market data.** Prices are polled, which is adequate for 1-minute bars and
  not for anything faster.
* **No database migrations.** A clean install creates the schema correctly; there is no
  automated upgrade path, and the version guard refuses to open a mismatched database
  rather than misreading it.
* **Docker is untested here** — see above.
* **The mock LLM is not a model of Claude's judgement.** It is a stand-in that exercises
  the pipeline, and every assessment it produces says so in its own text.

---

## Documentation

| | |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | How the whole thing is put together, and why |
| [`docs/LIVE_TRADING.md`](docs/LIVE_TRADING.md) | Costs, expected value, the activation gate, going live |
| [`docs/RISK_ENGINE.md`](docs/RISK_ENGINE.md) | The four risk layers, ruin analytics, capital accounting |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Custody, fund movement, secrets, what the AI may not do |
| [`docs/BINANCE_INTEGRATION.md`](docs/BINANCE_INTEGRATION.md) | Every unverified assumption, and how to verify it |

---

## Layout

```
packages/tia/src/tia/
  core/         clock, config, ids, errors, logging, seeded RNG
  domain/       instruments, market data, orders, portfolio, risk, signals
  events/       versioned envelopes, bus, idempotency
  data/         market-data providers and the data-quality engine
  quant/        indicators, features, performance statistics
  regime/       market-regime classifier
  strategy/     strategy library, fusion, signal engine
  risk/         risk engine, risk budget, ruin analytics, position sizing
  economics/    cost model and expected-value engine
  portfolio/    capital accounting: contributions vs trading P&L
  live/         the activation gate and API-key permission checks
  execution/    order state machine, paper matching engine, reconciliation
  backtest/     backtest engine, baselines, walk-forward, experiment verdicts
  llm/          structured output, providers, validation, cost governance
  persistence/  schema and repositories
  runtime/      the live paper-trading loop and the demo scenarios
  api/          HTTP API, SSE, auth, and the served dashboard
frontend/       the dashboard (Vite + React + TypeScript)
tests/          unit, integration, property, failure, adversarial, end-to-end
scripts/        diagnose, verify, smoke, fixtures, backtest, browser smoke,
                validate_binance
```

---

## Licence

Apache-2.0.
