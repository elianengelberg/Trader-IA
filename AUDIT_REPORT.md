# Audit Report

**Branch:** `claude/algo-trading-simulation-platform-ngf7xo`

Two parts, kept in order because the second changes the ground the first stood on:

* **Part I (2026-08-13)** — the audit of the simulation-only platform. Preserved as the
  record of what was found and fixed; the two statements it makes that are **no longer
  true** are annotated inline rather than rewritten, because an audit that edits its own
  history stops being evidence.
* **Part II (2026-08-14)** — the expansion to a gated live-trading platform: what was
  built, what running it broke, and the full list of what is wired, pending and unverified.

Nothing in either part is a claim about profitability. Where something could not be
verified, that is stated rather than implied.

---
---

# Part I — Simulation-only audit (2026-08-13)

**Baseline at audit start:** `4e47c3b`

This is what was inspected, what was executed, what broke, and what was done about it.

> **Superseded by Part II:** this part describes a platform whose scope rule was
> "simulation only, forever". That rule changed the next day. Where a Part I statement is
> now false, a `⚠ superseded` note points at the replacement.

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
| Routes for deposit/withdraw/transfer/bank/card/broker/custody | **none exist** — still true in Part II; the live path adds order placement, never fund movement |
| Risk-limit mutation through the API | **no route exists** |

---

## 6. The safety properties, verified

| Rule | How it is enforced | How it is checked |
|---|---|---|
| §1 The LLM cannot create risk | `context_modifier` clamped to `[-1, 0]` in the type, re-clamped at conversion, re-asserted in the service | property test over 300 adversarial assessments; schema test proving no execution field exists |
| §1 No real-money execution — **⚠ superseded** | *was:* `ExecutionProvider.__init__` raises on `is_simulated=False` | *now:* construction requires an unforgeable, expiring `LiveActivationToken` from the gate — Part II §10; the property that no provider goes live by accident is preserved |
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

---
---

# Part II — Expansion to gated live trading (2026-08-14)

**Baseline at Part II start:** `1e5b32c` · **At Part II end:** see `git log`

The brief changed: from "simulation only, forever" to an autonomous BTC/USDT platform on
Binance where the user connects their own account and authorises a bounded amount of real
capital. The structural guarantee of Part I — *no code path produces a live provider* —
was not discarded; it was replaced by a narrower one with the same shape: *no code path
produces a live provider **by accident***. Everything else in this part exists to make
that word "accident" carry weight.

---

## 10. What was built

| Piece | Where | Tested by |
|---|---|---|
| Cost Engine — round trip, itemised (fees/spread/slippage/latency/impact) | `economics/costs.py` | 21 unit tests |
| Expected Value Engine — edge from realised outcomes only; refuses < 30 samples/bucket | `economics/expected_value.py` | same file |
| Risk Budget — drawdown states, volatility cap, streak dampener, 3 ordered profiles | `risk/budget.py` | 20 unit incl. 500 property examples |
| Probability of ruin — seeded bootstrap + analytic cross-check, ruin = 50% equity | `risk/ruin.py` | 14 unit tests |
| Capital ledger — contributions vs P&L; unexplained-balance halt | `portfolio/capital.py` | 17 unit tests |
| Live Activation Gate — 14 checks; unforgeable, expiring, config-fingerprinted token | `live/gate.py` | 45 unit tests |
| API-key permission checker — refuses fund movement, incl. unknown flags by name shape | `live/permissions.py` | in gate + adapter suites |
| Binance signing — the only module that touches a secret | `data/providers/binance_signing.py` | 26 adapter tests |
| Binance spot execution — idempotent, unknown-state-refusing | `data/providers/binance_live.py` | same, mock transport |
| Gate probe wiring — every check fed by a value it did not choose | `api/gate_probes.py` | 16 integration tests |
| Runtime wiring — approval → budget → cost → EV → order; round trips scored into evidence | `runtime/engine.py` | 12 integration tests |
| Venue validation script — turns every documented assumption into a checked fact | `scripts/validate_binance.py` | run here (fails on egress, exit 1, as designed) |
| API: `/api/economics`, `/api/analytics`, `/api/capital`, `/api/live/gate`, `/api/live/arm` | `api/app.py`, `api/state.py` | integration + security tests |
| Frontend: Strategy & Costs, Ruin Analytics, Live Trading | `frontend/src/views/` | browser smoke, 14 views |
| Docs: `LIVE_TRADING`, `RISK_ENGINE`, `SECURITY`, `BINANCE_INTEGRATION`, `.env.example` | `docs/`, repo root | — |

Suite: **571 → 752 tests**, `make verify` 8 → **9 areas** (integration added), all PASS.

---

## 11. Defects found in Part II — again by running, not reading

### D9 — The aggressive profile's risk budget ROSE as drawdown crossed 8% · **CRITICAL** · fixed

The drawdown taper's NORMAL segment ended at a hardcoded 0.5 while the DEFENSIVE segment
began at the profile's own `defensive_multiplier`. For `balanced` (0.5) the segments met;
for `aggressive` (0.6) the budget **increased by 6%** on crossing the defensive threshold
— martingale behaviour produced by arithmetic rather than intent, which is exactly the
kind that survives review, because every hand-written test used the one profile where the
constants happened to coincide.

**Found by:** the no-martingale property test (Hypothesis, ~300 examples).
**Fix:** both segments anchored to the profile, making the discontinuity unrepresentable;
the continuity test is now parametrised across all three profiles; profiles with
out-of-order thresholds are rejected at construction.

### D10 — The EV engine's counters could not distinguish "refusing everything" from "not running" · **MEDIUM** · fixed

Only evaluations that reached an edge estimate were recorded. A fresh system — which
correctly refuses every signal for lack of evidence — reported `evaluations: 0`,
indistinguishable from an engine that was never called.

**Found by:** the first end-to-end run of the wired pipeline (75 refusals, counter read 0).
**Fix:** every path records, including refusals.

### D11 — Enforcing the EV gate in paper mode is a deadlock · **DESIGN** · resolved

No trades → no closed trades → no evidence → no trades, permanently. Not a bug in any one
function; a circularity in the design as briefed.

**Resolution:** paper **observes** (prices every decision, counts `ev_would_reject`, lets
the trade proceed so its outcome becomes a sample); live **enforces**. Both behaviours are
tested, including that enforcement genuinely stops the trades observation only counted.

---

## 12. Wiring status — built vs. connected

An honest audit distinguishes "the library passes its tests" from "the system uses it".

| Piece | Built | Wired into the running system |
|---|---|---|
| Cost + EV engines | ✔ | ✔ every approved would-be entry is priced; refusals counted |
| Risk budget | ✔ | ✔ computed per bar from live drawdown/vol/streak |
| Round-trip scoring → edge evidence | ✔ | ✔ in-memory (see gap 4 below) |
| Activation gate + probes | ✔ | ✔ `/api/live/gate` reports; `verify_passed.json` and `binance_validation.json` feed it |
| Capital ledger | ✔ | ✘ `/api/capital` synthesizes from the paper portfolio; `classify_external_change` never called in production |
| Binance execution adapter | ✔ | ✘ nothing constructs it outside tests |
| Activation token consumption | ✔ | ✘ `arm_live` mints, returns, and drops it |
| Live real-time runtime loop | ✘ | ✘ `RuntimeEngine` is scenario-only: simulated clock, generated data |

The unwired rows are the remaining distance between "a live-capable codebase" and "a live
system". They are listed as gaps 1–4 below and none of them is hidden behind a flag.

---

## 13. Known gaps at Part II close

Numbered for reference from the fix brief.

1. **No real-time live runtime.** No orchestrator runs SystemClock + Binance market data +
   Binance execution as a continuous loop. The scenario runtime proves the pipeline; the
   live loop does not exist yet.
2. **The activation token is not consumed.** Arming verifies everything, then the token is
   returned to the API caller and dropped. No stored activation, no transition to live
   execution, no audit-trail row in the database.
3. **Capital ledger unwired** (see §12). The deposit/withdrawal classifier and the
   unexplained-balance halt run only in tests.
4. **Edge evidence is process-memory.** Closed trades, bucket coverage and the consecutive
   -loss streak are lost on restart; the gate's paper-track-record check resets with them.
5. **`enforce_expected_value` has no automatic trigger.** Live mode should force it on;
   today only an explicit constructor argument does.
6. **`min_paper_days` configured but unread** — the track-record probe counts trades only.
7. **Latency is configured, not measured.** The cost model prices the simulator's
   configured submit+ack delays; a live deployment must measure decision-to-fill and feed
   the measurement back.
8. **Multi-fill exits scored at the last fill's price**, not exit VWAP. Entry is VWAPed;
   exit is not.
9. **No request-weight pacing on the Binance adapter.** It reacts to 429/418 but does not
   track Binance's request-weight budget to avoid hitting them.
10. **No live reconciliation scheduler.** The reconciliation engine exists; nothing
    periodically compares the local order mirror against the venue in a live session.
11. **No continuous clock-skew monitoring.** Checked once by the validation script; a live
    session that drifts past `recvWindow` mid-run discovers it as opaque rejections.
12. **No WebSocket streams** — market data would be polled; order updates would be polled.
    Adequate for 1-minute bars, stated as such.
13. **No frontend Capital view** — `/api/capital` and its types exist; no page consumes
    them.
14. **`economics_snapshot`'s headline budget** is computed with volatility 0 and exposure
    0 (the per-bar decision path uses the real values); the two can disagree slightly.
15. **Gate reports and arming attempts are not persisted** — the audit trail of who tried
    to arm, when, and what refused them lives only in responses and logs.
16. **`binance_validation.json` is trusted as read** — the fees/credentials probes accept
    the file without schema validation or a freshness bound; a stale or hand-edited file
    would satisfy them.
17. **Position cost basis from the venue is 0.0** — spot balances carry no cost basis;
    the fill journal must supply it, and in a fresh process it cannot.
18. **No automatic flatten on EMERGENCY.** The budget stops new positions; open ones are
    closed only by their protective stops or reversals.
19. Inherited from Part I, still true: no Docker execution, no live Claude call, no DB
    migrations, money as `float`, regime accuracy unmeasured, single-operator sizing,
    longest observed run 660 bars.

---

## 14. Honest summary, Part II

The economics, risk-budget, capital, gate and adapter layers exist, are tested (752
passing), and the paper pipeline runs them end to end — including the number the whole
expansion turns on: a measured 23.4 bps gross edge against 22.9 bps of round-trip costs
nets 0.45 bps, which is NO_TRADE, and no earlier version of this platform could have told
you that.

What does not exist yet is the last mile: a real-time loop that runs the same pipeline
against live Binance data, consumes an activation token, and books capital through the
ledger. Every piece of that mile is built and tested in isolation; §13 is the exact list
of what connecting them requires. Nothing on that list is disguised as done.

The Binance adapters remain **REQUIRES VALIDATION** end to end: this environment blocks
every Binance host including the testnet, so not one request was ever sent, and the
activation gate is wired to refuse until `scripts/validate_binance.py` has been run from a
machine that can reach the venue.

---
---

# Part III — Second audit: A1–F6 after the hardening pass (2026-08-14)

Verdicts use the brief's own vocabulary. "SOLVED" means implemented **and** integrated
**and** tested **and** restart-surviving where that applies — not "a class exists".

| Gap | Verdict | Evidence |
|---|---|---|
| A1 live runtime | **SOLVED** | `runtime/live.py` + 13-state machine (`runtime/states.py`); startup validation, graceful stop, halt/cancel-only/flatten, safe mode; 23 tests in `test_live_runtime.py`. RUNNING is set only by the state machine after validation passed. |
| A2 activation persisted + consumed | **SOLVED** | `arm_live` persists every attempt (report, failed checks, config + token fingerprints), then **starts** the runtime and reports LIVE only on RUNNING; `test_live_activation_persists/starts_runtime/audit_persisted`, `test_gate_report_persistence`. |
| A3 capital ledger wired | **SOLVED** | LiveRuntime funds the ledger at start, books fees/P&L per fill, and reconciliation classifies balance drift; unexplained >10% halts — `test_capital_ledger_live_reconciliation`, `test_unknown_balance_change_halts`. |
| A4 edge persistence | **SOLVED** | `edge_outcomes` table; paper and live persist every close (deterministic id = replay-safe upsert); estimator + streak + track record rebuilt at start — `test_restart_recovery`, `test_edge_persistence_survives_restart`. |
| A5 EV enforced in live | **SOLVED** | Structural: LiveRuntime has no observe flag to misconfigure (asserted absent by `test_live_requires_expected_value`); the gate's `ev_enforcement` check fails if one ever appears. |
| B1 Binance validation | **EXTERNAL VALIDATION REQUIRED** | Script upgraded: fingerprinted v2 envelope, user-data-stream (listenKey) exercise, duplicate-order demonstration, refuses to write a record of a failed run. Zero requests ever sent from here — every host blocked, verified again this session. |
| B2 Docker | **EXTERNAL VALIDATION REQUIRED** | `make docker-verify` validates what it can and exits 3 (a distinct code) without a daemon; executed here: exit 3, as designed. |
| B3 Claude API | **EXTERNAL VALIDATION REQUIRED (integration SOLVED)** | Real adapter behind `ANTHROPIC_API_KEY` with governance, budget, breaker, schema validation and failure-path tests; no key here, so no live call — and the readiness report says exactly that. |
| B4 TradingView | **SOLVED (as isolation)** | Webhook disabled by default, HMAC+timestamp+replay-window+allowlist, and not on the execution path; its failure cannot corrupt the Binance runtime. |
| C1 reconciliation scheduler | **SOLVED** | In-loop cadence; venue wins; divergence → SAFE_MODE; every run persisted — `test_reconciliation_scheduler`, `test_live_safe_mode_on_unknown_state`. |
| C2 clock skew | **SOLVED** | `ClockSkewMonitor`: startup refusal + periodic mid-session halt — `test_clock_skew_monitor`. |
| C3 request budget | **SOLVED (weights REQUIRE VALIDATION)** | `BinanceRequestBudget`: rolling-window weight tracking, adaptive pacing, 429/418 cooldowns wired into the adapter. The per-endpoint weights are documented values pending confirmation via exchangeInfo. |
| C4 latency | **SOLVED** | `LatencyTracker` stamps all eight stages, persists samples, and its EMA feeds the cost model's latency term — `test_latency_measurement`. |
| C5 halt/cancel/flatten | **SOLVED** | Three distinct states with an explicit transition table; kill switch ≠ flatten (software-in-doubt vs get-me-out); both operator-only, named-actor, persisted — `test_kill_switch`, `test_emergency_flatten`. |
| C6 min paper days | **SOLVED** | Track-record probe reads days AND trades from the persisted record — `test_min_paper_days_gate`. |
| C7 validation freshness | **SOLVED** | Pydantic schema, validator version, environment/symbol match, content fingerprint, 24 h bound, future-dated refused — `test_binance_validation_schema/freshness`. UNKNOWN = FAILED throughout. |
| C8 WebSockets | **NOT SOLVED (deliberate)** | Implementing a WS client that has never once connected would be inventing an API surface. The listenKey path is validated by the script; runtime remains polling (adequate for 1 m bars, stated); WS is the first post-validation task. |
| D1 exit VWAP | **SOLVED** | Both runtimes accumulate exit legs; `test_multi_fill_exit_vwap` (2-fill exit scored at 50,500, not the last fill's 50,800). |
| D2 snapshot consistency | **SOLVED** | Snapshot reuses the decision path's own `BudgetInputs`, provenance flagged — `test_economics_snapshot_matches_risk`. |
| D3 cost basis | **SOLVED (as honesty)** | Venue balances carry no basis; the live snapshot says UNKNOWN-until-replayed and no fabricated figure exists — `test_cost_basis_recovery`. |
| E1 capital view | **SOLVED** | `/capital` page: CAPITAL FLOW and TRADING PERFORMANCE as separate cards, live ceiling panel; renders in browser smoke. |
| E2 risk profile | **SOLVED** | `POST /api/risk/profile`: confirmed, operator-only, refused mid-live-session, applies to the next run, audited — `test_risk_profile_change_audit`. RiskLimits stay immutable; no route touches them. |
| E3 gate history | **SOLVED** | Every attempt persisted and shown on the Live page ("who tried, when, what stopped them"). |
| F1 migrations | **SOLVED** | Alembic 0001/0002; empty→head, v1→v2 in-place with rows preserved, pre-Alembic adoption — 2 migration tests. |
| F2 money types | **SOLVED (settlement scope)** | Decimal in the capital ledger internals and the live order builder (lot/tick quantization, venue formatting); simulation/analytics stay float **by stated design** — `test_money_uses_decimal`. Full-codebase Decimal was rejected as a stability risk the brief itself forbids. |
| F3 regime accuracy | **UNVALIDATED** | No trusted labels exist; no metrics invented. Stated in docs and readiness. |
| F4 single operator | **DOCUMENTED** | SQLite/SSE/rate-limit sizing documented; not overdesigned. |
| F5 endurance | **SOLVED** | `scripts/endurance.py` executed here: 1,660 simulated bars (>24 h), 6/6 checks green (dup-orders, RSS, latency, errors, evidence coherence, equity) — and it **found D12** (silent decision-persistence failure), now fixed with columns + guarded migration. |
| F6 paper order book | **SOLVED (existing, documented)** | Spread, slippage, sqrt impact, participation cap, partial fills already modelled; queue position and book depletion documented as absent. Not misrepresented as an HFT simulator. |

New defects found and fixed during this pass, all by running: **D12** (decisions silently
not persisting since the economics wiring — endurance caught it), the boundary suite
catching **the API layer touching the secret** and **the budget module naming order
endpoints** (first fixed by moving code, second allowed deliberately), and the fills FK
ordering race (documented as accepted, §7.3 of SECURITY_AUDIT.md).

---

# Part IV — 24/7 deployment pass (2026-08-14)

Scope: run the paper platform continuously on a server, unattended, with the live path
still gated. Everything below was implemented and tested in this pass; the verdict
column says what was *executed* here versus what needs a machine this environment is not.

| Item | Verdict | Evidence |
|---|---|---|
| Paper-realtime session (real data shape, simulated fills, **no token by design**) | **SOLVED** | The token requirement binds to `execution.is_live`; a paper session cannot spend and therefore needs none, while a live provider still cannot exist without one — `test_paper_realtime_runs_without_a_token_and_says_so`, `test_live_runtime_cannot_exist_without_a_token_over_live_execution`. |
| `POST /api/live/paper-start` | **SOLVED** | Operator-only, 409 on double-start, 503 when the data host is unreachable with nothing half-started; snapshot says `paper-live` / `simulated: true`. 5 API tests. |
| Heartbeat ≠ HTTP | **SOLVED** | Loop advances `last_heartbeat`; `/api/health` reports `trading_engine: degraded` past 120 s while HTTP still answers — `test_heartbeat_advances_with_the_loop_not_with_http`. |
| Market-data watchdog | **SOLVED** | No new bar for 300 s → entries halt; recovery only through clean reconciliation, and only for watchdog-caused halts — `test_stale_market_data_halts_and_recovery_is_earned`. |
| Provider-failure grace | **SOLVED** | Transient failure → halt; 10 consecutive → sticky SAFE_MODE — `test_transient_provider_failure_halts_then_escalates_only_if_persistent`. |
| Restart semantics | **SOLVED** | Crash/redeploy-interrupted paper sessions resume on boot as a new run over the same evidence store; operator stops stamp the run row and stay stopped; kill-switched sessions stay down — `test_paper_session_resumes_after_a_crash_but_not_after_an_operator_stop`, `test_a_kill_switched_paper_session_stays_down_across_restarts`. |
| Alert webhook seam | **SOLVED (seam)** | Incidents persist → SSE + POST to `TIA_ALERT_WEBHOOK_URL`; payload carries no secret (scanned); no-URL means no call. Real delivery NOT VERIFIED (no reachable endpoint here). |
| Validation record bound to the key | **SOLVED (tightening)** | The validator records a one-way key fingerprint; the gate refuses a record made with a different key than configured, and refuses records that never recorded one — `test_validation_record_is_bound_to_the_configured_api_key`. |
| Regime accuracy (F3) | **MEASURED (synthetic)** | `make regime-accuracy`: settled primary accuracy 16–51% by scenario; high-volatility weakest; confusion matrices persisted. Real-market accuracy remains UNVALIDATED — stated, not padded. |
| Production stack (Caddy HTTPS, internal-only Postgres, daily backups, unless-stopped) | **AUTHORED — REQUIRES VALIDATION** | `docker-compose.prod.yml`, `infra/Caddyfile`, `.env.production.example` (three secrets required, no defaults). No daemon here; `make production-readiness` proves it on target or exits 3. |
| Ops scripts | **PARTIALLY EXECUTED** | `backup.sh` ran against SQLite (dump gzip-verified); `daily_report.py` verified against a populated journal; `deploy.sh` / `production_readiness.sh` honest exit-3 paths executed, Docker paths not. |
| CI | **AUTHORED — REQUIRES VALIDATION** | `.github/workflows/ci.yml` mirrors `make verify` minus the browser smoke; never run from here. |
| Deployment guide | **WRITTEN** | `docs/DEPLOYMENT.md`, 15 sections, including the infrastructure comparison (recommendation: small Hetzner/DO VPS; prices flagged as unverified) and the reboot test no script can wrap. |

Defect found and fixed in this pass: the live ceiling's fail-closed default
(`max_live_capital=0`) also blocked the **paper** ledger at construction and start —
paper now funds from the simulated bankroll while any configured live ceiling still
binds, and the live path is unchanged (`CapitalPolicy` still rejects a zero ceiling for
real execution).

Verification after the pass: `make verify` 9/9, **833 tests**, ruff and TypeScript clean.
