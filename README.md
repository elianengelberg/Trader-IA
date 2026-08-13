# Trader-IA

Quantitative research, backtesting and **paper trading** — simulation only.

This platform holds no money, connects to no broker, and has no custody of any asset. The
"capital" in it is a number in a simulation and the fills come from a bar-based matching
engine. Nothing it produces is a prediction or a recommendation.

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
make verify   # lint, unit, property, end-to-end, frontend types, browser smoke test
make smoke    # start the server, drive the dashboard in a real browser, stop it
make test     # the fast tests only
```

`make verify` prints PASS / FAIL / WARN per area and runs every area even when one fails —
a report that stops at the first failure hides whether the rest works.

---

## What it does

```
market data → data quality gate → features → market regime → strategies → fusion
            → AI context (advisory) → risk engine → order intent
            → paper execution → fill → position → P&L → dashboard → audit log
```

Two properties define the design.

**The language model cannot create risk.** Its entire response schema is a *caution*
level, converted to a modifier clamped to `[-1, 0]`. There is no field it can return that
opens a trade, enlarges one, chooses a direction, or overrides a limit. A hallucination, a
poisoned news item or a prompt injection can only ever cost trades that would otherwise
have been taken. This is enforced by the type system, re-clamped at the conversion
boundary, and checked by a property test over adversarial inputs.

**The risk engine is deterministic and has absolute veto.** It is not a model, it never
consults one, and nothing downstream can override it. It may only ever *shrink* a
requested size — an engine that could grow one would be a second, unreviewed sizing model.

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

## What is not here, deliberately

* **No real-money execution.** `ExecutionProvider.__init__` raises if a provider declares
  `is_simulated=False`, so there is no code path that constructs a live one.
* **No deposits, withdrawals, transfers, custody, bank details or card details.** No route
  exists for any of them, and a test asserts the API exposes none.
* **No risk-limit editing from the interface.** Limits are immutable at runtime and no API
  route changes them. Altering one is a code change that goes through review.
* **No claim of profitability anywhere.** Backtest verdicts are
  `insufficient_evidence`, `no_edge_demonstrated`, `mixed`, `beat_all_baselines` — none of
  which means "good", and the strongest is a statement about one dataset.

---

## Known limitations

Stated here rather than discovered later.

* **The paper simulator has no order book.** Fills are matched against bar OHLCV, so queue
  position and book depletion do not exist. Our own orders have no market impact. There
  are no halts, auctions, funding or borrow costs. `docs/ARCHITECTURE.md` §12.1.
* **Binance and TradingView integrations are unverified.** Both hosts are blocked by the
  build environment's egress proxy, so not a single request was ever made. They are opt-in,
  refused by the demo environment, and labelled `REQUIRES VALIDATION`.
* **No database migrations.** A clean install creates the schema correctly; there is no
  automated upgrade path from an older database, and the version guard refuses to open a
  mismatched one rather than misreading it.
* **Docker is untested here** — see above.
* **The mock LLM is not a model of Claude's judgement.** It is a stand-in that exercises
  the pipeline, and every assessment it produces says so in its own text.

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
  risk/         the deterministic risk engine and position sizing
  execution/    order state machine, paper matching engine, reconciliation
  backtest/     backtest engine, baselines, walk-forward, experiment verdicts
  llm/          structured output, providers, validation, cost governance
  persistence/  schema and repositories
  runtime/      the live paper-trading loop and the demo scenarios
  api/          HTTP API, SSE, auth, and the served dashboard
frontend/       the dashboard (Vite + React + TypeScript)
tests/          unit, property, end-to-end
scripts/        diagnose, verify, smoke, fixtures, backtest, browser smoke
```

---

## Licence

Apache-2.0.
