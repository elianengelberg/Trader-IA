# Audit Report

**Date:** 2026-08-13 · **Branch:** `claude/algo-trading-simulation-platform-ngf7xo`
**Baseline at audit start:** `4e47c3b` · **At audit end:** see `git log`

This is what was inspected, what was executed, what broke, and what was done about it.
Nothing in it is a claim about profitability. Where something could not be verified, that
is stated rather than implied.

---

## 1. Environment (measured, not assumed)

| Tool | Version | State |
|---|---|---|
| Python | 3.11.15 | OK |
| Node | 22.22.2 | OK |
| npm / pnpm | 10.9.7 / 10.33.0 | OK |
| PostgreSQL | 16.13 | server installed, was down → started and tested |
| Redis | 7.0.15 | server installed, was down → started and tested |
| Docker CLI | 29.3.1 | present |
| Docker **daemon** | — | **NOT RUNNING**, no `/var/run/docker.sock` |
| npm registry / PyPI | — | reachable |

**Consequence, stated up front:** `docker compose up` **could not be executed here**. The
compose file and Dockerfile exist and were written carefully, and they are labelled
`REQUIRES VALIDATION` in the README, in the compose file itself, and in §7 below. Every
other path in this document was run.

**Design decision that follows:** the default demo path uses **SQLite, an in-process event
bus, seeded synthetic market data, an offline LLM mock, and a static frontend served by
the API**. It needs no daemon, no external service and no credential. Postgres and Redis
are supported and were exercised, but they are opt-in.

---

## 2. Component matrix

State at audit start → state now.

| Component | Was | Now | Tests | Notes |
|---|---|---|---|---|
| `core` | WORKING | **WORKING** | unit + property | clock discipline now split into a strict and an exempt list, both asserted |
| `domain` | WORKING | **WORKING** | unit | — |
| `events` | WORKING | **WORKING** | unit | DB-level dedup added on top of the in-memory store |
| `data` (synthetic, CSV) | WORKING | **WORKING** | unit | — |
| `data` (Binance) | PARTIALLY_WORKING | **PARTIALLY_WORKING** | offline shape only | host blocked by the egress proxy; never executed against the live API |
| `data/quality` | WORKING | **WORKING** | unit + scenario | now demonstrably refuses a broken feed (D6) |
| `quant` | WORKING | **WORKING** | unit + property | indicators recompute per bar; bounded by the lookback window |
| `regime` | WORKING | **WORKING** | unit + causality test | classification *quality* still unmeasured — see §8 |
| `strategy` | WORKING | **WORKING** | unit + property | — |
| `risk` | WORKING | **WORKING** | unit | absolute veto verified through the API and the UI |
| `execution` | WORKING | **WORKING** | unit + property | — |
| `backtest` | WORKING | **WORKING** | unit + property | two look-ahead detectors, not one |
| `llm` | **MISSING** | **WORKING** | unit + adversarial | mock default, Claude adapter, governance, validation |
| `persistence` | **MISSING** | **WORKING** | integration | SQLite + Postgres; no migrations (stated limitation) |
| `runtime` | **MISSING** | **WORKING** | e2e | nine seeded scenarios |
| `api` | **MISSING** | **WORKING** | unit + e2e | auth, SSE, hardening |
| Frontend | **MISSING** | **WORKING** | browser smoke | eleven views, live over SSE |
| Authentication | **MISSING** | **WORKING** | unit | PBKDF2, JWT cookie, rate limit |
| `agents/`, `memory/` | MISSING | **REMOVED** | — | empty directories promising work that did not exist |
| Docker | MISSING | **REQUIRES VALIDATION** | none | written, never run |
| `make verify` / `diagnose.sh` | MISSING | **WORKING** | self-testing | — |

---

## 3. Defects found, and what happened to them

Everything here was found by **running** the system, not by reading it.

### D1 — The runtime's clock never advanced · **CRITICAL** · fixed

`RuntimeEngine.start()` reassigned `self._clock`, but every component had already been
constructed with the *original* clock object in `__init__`. Rebinding the attribute left
the strategy engine, the risk engine, the execution simulator and the LLM governor all
holding a clock that never moved.

Two unrelated-looking symptoms, one cause:

* Every signal failed the `signal_ttl` risk check immediately, so the system **never
  traded at all** — 152 actionable signals, 0 approvals, across a full 500-bar run.
* The LLM rate-limit window never slid, so 365 of 371 assessments were refused with
  `rate_limit` and the context layer was effectively off.

**Fix:** the clock is constructed once and never replaced; the engine is single-use and
raises if started twice rather than rewinding time. **Evidence:** the same run now
produces 70 approvals and a complete round trip.

### D2 — Positions opened and never closed · **HIGH** · fixed

The runtime had no exit mechanism. It opened one position and then suppressed the next 69
approvals behind it, so a 500-bar run produced exactly one fill and no realised P&L.

**Fix:** protective-stop maintenance (placed on fill, resized on partial fill, cancelled
when flat) plus reversal exits when an approved signal opposes the open position.
**Evidence:** buy at 50,274.66 → sell at 51,494.85, realised +45.52, position closed, cash
returned.

### D3 — Risk-rejection counters were useless · **MEDIUM** · fixed

Rejections were bucketed by free-text reason. The reasons embed the actual numbers
(`"confidence 0.182 below minimum 0.550"`), so the result was one bucket per bar and
nothing was identifiable.

**Fix:** bucketed by failed check name. **Evidence:** the binding gates are now legible —
`signal_actionable: 1102, min_confidence: 472, max_volatility_percentile: 41,
trade_cooldown: 5`.

### D4 — A provider exception could kill the trading loop · **HIGH** · fixed

`ContextService.assess` documented itself as never raising, and caught
`LLMUnavailableError`, `LLMSchemaError` and `LLMError`. A pydantic `ValidationError` from
inside a provider matched none of them, escaped, and halted the runtime.

**Fix:** a last-resort `except Exception` that logs and degrades to a neutral assessment.
A promise that holds only for anticipated exceptions is not a promise.

### D5 — The mock provider could emit a value its own schema rejected · **MEDIUM** · fixed

`MockLLMProvider` copied `regime_view` straight from the prompt payload, which carries the
*domain* regime. `MarketRegime.ANOMALOUS` was not in the response schema's literal, so a
perfectly ordinary market condition produced a validation error (this is what triggered
D4 in the e2e run).

**Fix:** the schema's regime vocabulary is now **generated from the enum**, so the two
cannot disagree; and the mock coerces anything unrecognised to `unknown`.

### D6 — The data-failure scenario did not exercise the data gate · **MEDIUM** · fixed

The scenario corrupted 35% of bars and the quality gate skipped **zero** of them. The
corruption was applied to isolated bars, and one frozen bar in a moving market is
correctly not evidence of a broken feed. The scenario claimed to demonstrate the gate
while demonstrating nothing.

**Fix:** faults are now injected as **runs**, which is the shape they actually take — a
stuck feed repeating for 20+ bars, a volume blackout for 8–18 bars, a spike far outside
the recent distribution. The gate's thresholds were **not** touched; loosening a quality
check so a demo looks livelier is the wrong direction. **Evidence:** 97 of 500 bars now
refused, each logged with its flag.

### D7 — `pyproject.toml` declared a console script that did not exist · **HIGH** · fixed

`[project.scripts] tia = "tia.cli:app"` pointed at a missing module, so installing the
package produced a `tia` command that raised `ModuleNotFoundError`.

**Fix:** the entry point now points at the API server, which exists and starts.

### D8 — Seven empty package directories · **MEDIUM** · fixed

`llm/`, `agents/`, `memory/`, `observability/`, `persistence/`, `runtime/`, `api/routers/`
were empty — the structure promised more than the repository contained.

**Fix:** `llm`, `persistence`, `runtime` and `api` were built. `agents/` and `memory/`
were **deleted**: an empty directory named for a feature is a claim, and deleting it is
more honest than leaving it.

### Found earlier in the build, recorded for completeness

* `BinancePublicProvider` called `datetime.now()` directly, contradicting the no-wall-clock
  rule its own module docstring relies on. Now takes an injected clock.
* `tests/unit/test_scope_boundary.py` was referenced by two docstrings without existing.
  It now exists and walks the entire package.
* The look-ahead prefix detector has a **blind spot** for one-bar-ahead leaks, because such
  a leak is stable under truncation. A second detector (future perturbation against the
  decision log) was added, and the test file demonstrates the first missing what the
  second catches.

### Defects that were in the tests, not the code

Recorded because a test that fails for its own reasons is a defect too.

* The browser smoke test compared label text case-sensitively while the stylesheet
  uppercases labels through `text-transform`; `inner_text()` returns rendered text.
* The same test asserted decisions existed before the runtime's warm-up had finished.
* The path-traversal test assumed a JSON response. Some traversal attempts normalise into
  a path no API route matches and correctly fall through to the single-page app, which
  answers with `index.html`. Asserting on the status code flagged safe behaviour as a
  leak; the assertion is now on the response *content* — never the contents of a host file.

---

## 4. What was executed

| Area | How | Result |
|---|---|---|
| Environment | `scripts/diagnose.sh` | READY, 3 optional components absent |
| Lint | `ruff check packages tests scripts` | clean |
| Unit + property | `pytest tests/unit tests/property` | pass |
| End-to-end pipeline | `pytest tests/e2e` | pass |
| Database, SQLite | schema creation, upsert, FK cascade, query | pass |
| Database, PostgreSQL | server started, same schema | pass |
| Redis | server started, `PING` | pass |
| API, unauthenticated | every data and control endpoint | 401 |
| API, authenticated | full run lifecycle via HTTP | pass |
| SSE | `curl -N /api/stream` and a browser | events streaming |
| Backtest via API | `POST /api/backtests` | verdict + 5 baselines |
| Dashboard | headless Chromium, 11 views | pass, no console errors |
| Failure injection | `pytest tests/failure` | 12 cases pass |
| Smoke | `make smoke` | PASS |
| Full verification | `make verify` | **8 of 8 areas PASS** |
| Docker | — | **NOT RUN — no daemon** |

### The end-to-end flow, observed

```
login → start run (simulated capital 25,000) → 660 bars ingested
  → 531 signals (405 NO_TRADE) → risk approved 3, rejected 123
  → 3 orders → 3 fills → position opened and closed → P&L realised
  → every step visible in the dashboard and in the audit log
```

Reproducible: the same scenario and seed produce identical fills, asserted by
`test_the_run_is_reproducible`.

---

## 5. Security testing

| Test | Result |
|---|---|
| Unauthenticated access to every data endpoint | refused (401) |
| Unauthenticated access to every control endpoint | refused (401) |
| Wrong password / nonexistent user | identical response — not a username oracle |
| Password storage | PBKDF2-HMAC-SHA256, per-password salt, constant-time compare |
| Malformed stored hash | fails closed |
| JWT signed with another secret | rejected |
| Tampered JWT | rejected |
| `alg: none` forgery | rejected |
| Expired JWT | rejected |
| Session cookie | `HttpOnly`, `SameSite=Strict`, `Secure` under HTTPS |
| Brute-forced login | rate limited (429) |
| SQL injection through path and query parameters | no effect; database intact |
| Path traversal (5 encodings) | no host file contents returned |
| Oversized request body | refused (413) |
| Internal error | no traceback, path or driver name in the response |
| CSP, `X-Frame-Options`, `nosniff`, `Referrer-Policy` | present on every response |
| Secrets in `/api/settings` | none; reports only *whether* a key is configured |
| Database password in logs and API | masked |
| Routes for deposit/withdraw/transfer/bank/card/broker/custody | **none exist** |
| Risk-limit mutation through the API | **no route exists** |

---

## 6. The safety properties, verified

| Rule | How it is enforced | How it is checked |
|---|---|---|
| §1 The LLM cannot create risk | `context_modifier` clamped to `[-1, 0]` in the type, re-clamped at conversion, re-asserted in the service | property test over 300 adversarial assessments; schema test proving no execution field exists |
| §1 No real-money execution | `ExecutionProvider.__init__` raises on `is_simulated=False` | scope-boundary test walks every subclass in the package |
| §1 No financial secret in a prompt | prompt builder receives only market state | test asserts no credential marker appears in a built prompt |
| §13/§15 No free-form output becomes an order | forced tool call; text-only replies raise | provider test |
| §14 Claude does no arithmetic that matters | sizing, limits and exposure are computed by the deterministic engine | risk-engine tests |
| §19 The risk engine has absolute veto | it is a pure function of state, never consults a model | e2e kill-switch test; UI shows the binding gate |
| §15/§64 Expired signals never execute | TTL checked at evaluation | risk-engine test; D1 was the reverse failure |
| §48 The system cannot rewrite its own limits | `RiskLimits` raises on mutation; no API route | test asserts the OpenAPI spec has no such route |
| §63 No claim of profitability | verdict vocabulary contains nothing meaning "good" | test asserts the four values; UI footnote on every page |

---

## 7. What is NOT verified

Stated plainly, because an audit that only lists successes is not an audit.

1. **Docker.** Never executed. No daemon in this environment.
2. **Binance and TradingView.** Both hosts blocked by the egress proxy; zero requests made.
   Opt-in, refused by the demo environment, labelled `REQUIRES VALIDATION`.
3. **The real Claude API.** No key was available. The `AnthropicProvider` is written
   against the documented Messages API with a forced tool call, and its *failure* paths are
   tested with a scripted provider, but no live call was ever made.
4. **Load and concurrency beyond one operator.** The SSE fan-out, the in-process rate
   limiter and the SQLite writer are sized for one process serving one dashboard.
5. **Regime-classification quality.** The classifier is exercised and its causality is
   asserted, but its *accuracy* against labelled regimes is not measured. Listed in §8.
6. **Database migrations.** A clean install works; upgrading an existing database does not
   have an automated path.
7. **Long-horizon behaviour.** The longest continuous run observed is 660 bars.

---

## 8. Known gaps, not defects

* No parameter-sensitivity sweep in the backtester.
* No labelled-regime accuracy measurement.
* Two rows of the failure-mode table remain untested — Redis failover and provider
  reconnection with backfill — because both need a live external service. The other
  twelve are covered by `tests/failure/`.
* Indicators recompute over the whole rolling buffer each bar. Bounded and linear, but the
  main cost of a backtest.
* Money is stored as `float`. Correct for a simulation, wrong for anything that settles,
  and stated in the schema's own docstring.

---

## 9. Honest summary

The pipeline works end to end and can be demonstrated in a browser, driven by tests, and
reproduced from a seed. Six defects were found by running it — one of which meant the
system had **never traded at all** — and all six are fixed with evidence recorded above.

The parts that are unverified are unverified because of the environment, not because they
were skipped, and each one is labelled in the code as well as here.

**On the trading results themselves:** the current configuration, on the committed
fixtures, produces a small loss and a verdict of *insufficient evidence* against five
baselines. That number has not been tuned, and improving it was not the goal of this work.
