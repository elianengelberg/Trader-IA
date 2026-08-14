# System Status

Generated after a full `make verify` run on 2026-08-14. Every PASS below corresponds to
something that was executed, not reviewed. Every NOT VERIFIED and every PENDING says why.

The platform's scope changed on 2026-08-13: from simulation-only to **paper by default,
live through an activation gate**. Part II of `AUDIT_REPORT.md` records that change and
the defects found while making it.

---

## Verdict by area

| Area | Status | Evidence |
|---|---|---|
| **BACKEND** | **PASS** | 752 tests; the runtime processes bars, decides, budgets, prices, and executes end to end |
| **FRONTEND** | **PASS** | 14 views rendered in headless Chromium, zero console errors |
| **DATABASE** | **PASS** | schema creates from scratch on SQLite and PostgreSQL; FK cascade, upsert dedup and queries exercised |
| **EVENT BUS** | **PASS** | in-process bus under test; duplicate events rejected by a unique index |
| **MARKET DATA (synthetic/CSV)** | **PASS** | seeded and reproducible byte-for-byte |
| **MARKET DATA (Binance)** | **NOT VERIFIED** | every Binance host blocked by the egress proxy; zero requests ever made |
| **QUANT** | **PASS** | indicators, features and statistics against known values and property tests |
| **STRATEGY** | **PASS** | library, fusion, regime gating; the asymmetry rule property-tested |
| **ECONOMICS (costs + EV)** | **PASS** | round-trip pricing itemised; edge from realised outcomes only; refuses below 30 samples; observing in paper, enforcing in live |
| **RISK ENGINE** | **PASS** | absolute veto verified through the library, the API and the browser |
| **RISK BUDGET** | **PASS** | drawdown states, volatility scaling, streak dampener; no-martingale asserted over randomised inputs — and it caught a real defect (D9) |
| **RUIN ANALYTICS** | **PASS** | seeded Monte Carlo + analytic cross-check; refuses below 2 trades, warns below 30 |
| **CAPITAL LEDGER** | **PASS (library)** · **PENDING (wiring)** | tested in isolation; not yet driven by the runtime — see Pending |
| **LIVE ACTIVATION GATE** | **PASS** | 14 checks, unforgeable expiring token bound to a config fingerprint; refuses correctly in this environment (11 of 14 checks fail, each naming its remedy) |
| **BINANCE EXECUTION** | **NOT VERIFIED** | adapter logic tested against mock transport (26 tests); no request has ever reached Binance; `scripts/validate_binance.py` closes the gap |
| **CLAUDE / AI LAYER** | **PASS (mock)** · **NOT VERIFIED (live)** | full pipeline on the offline mock and adversarial inputs; no API key available |
| **EXECUTION SIMULATOR** | **PASS** | order state machine, matching, slippage, fees, partial fills, reconciliation |
| **BACKTESTING** | **PASS** | engine, five baselines, walk-forward, two independent look-ahead detectors |
| **MONITORING** | **PASS** | health endpoint, Prometheus metrics, live log stream, per-component status |
| **FAILURE HANDLING** | **PASS** | injected failures incl. LLM outage, corrupted feed, phantom position, safe mode, restart, redelivery |
| **SECURITY** | **PASS** | see the table below; secret-leak tests scan whole response bodies including error paths |
| **END-TO-END** | **PASS** | full flow asserted by automated test and reproduced in a browser |
| **DOCKER** | **NOT VERIFIED** | no daemon in the build environment; compose never run |

---

## What `make verify` reports

```
PASS  Lint (ruff)
PASS  Unit tests
PASS  Integration tests
PASS  Property tests
PASS  Failure injection
PASS  End-to-end pipeline
PASS  Frontend type check
PASS  Frontend build
PASS  Smoke test            RESULT: PASS — every view rendered, no console errors

ALL CHECKS PASSED           → recorded in data/runtime/verify_passed.json,
                              which is what the gate's tests_pass check reads
```

Totals: **752 Python tests**, ruff clean, TypeScript clean, browser smoke over 14 views.

---

## The decision pipeline, as it now runs

```
bar → data quality → features → regime → strategies → fusion
    → AI context (advisory, clamped to [-1, 0])
    → risk engine        "is this survivable?"      → absolute veto
    → risk budget        "how much, right now?"     → may answer: nothing
    → cost model         "what will it cost?"       → round trip, itemised
    → expected value     "is what's left worth it?" → refuses without evidence
    → order → fill → position → P&L → round-trip scored → evidence recorded
```

The decisive number from the first execution of the economics layer: a measured 23.37 bps
gross edge minus 22.92 bps of round-trip costs = **0.45 bps net → NO_TRADE**. At 10 bps
taker per side, a BTC strategy needs >25 bps gross per trade to break even. This is the
arithmetic that decides viability, and the prior platform never computed it.

---

## Scope guarantees, mechanically enforced

| Guarantee | Mechanism |
|---|---|
| No custody, ever | no wallet, no deposit route, no balance the system owns; asserted by API tests |
| No fund movement, ever | no source file names a withdrawal/transfer endpoint — boundary grep with **no allowance list**; the API key must lack the permission, checked against the venue; unknown permissions with fund-movement names are refused |
| No live execution from a flag | a non-simulated provider cannot be constructed without a `LiveActivationToken`; the token cannot be forged, expires, is re-validated per order, and is bound to a fingerprint of the risk limits |
| The LLM cannot create or enlarge risk | modifier clamped to `[-1, 0]` in the type, re-clamped at conversion, re-asserted in the service |
| No Martingale / revenge trading | risk never rises with drawdown or losses — property-tested over randomised inputs across all profiles |
| No trade without measured evidence (live) | EV engine refuses below 30 closed trades per bucket; edge never derived from confidence |
| Secrets never leave | one signing module may touch the secret (boundary-tested); responses scanned whole-body, including error paths; no endpoint accepts a credential |
| The system cannot rewrite its own limits | `RiskLimits` and `CapitalPolicy` raise on mutation; no API route; config change voids any active token |
| No claim of profitability | verdict vocabulary contains nothing meaning "good"; the gate's own pass message says it is not evidence of profit |

---

## Security

Unchanged from the Part I audit (all rechecked green in this run), plus:

| Check | Result |
|---|---|
| Venue secret in any response body, error paths included | **absent** — scanned, not field-asserted |
| `POST /api/live/arm` accepts key/secret/capital | **no** — confirmation phrase only; extra fields ignored, ceiling unmoved |
| Arming without operator role / exact phrase / passing checks | **refused** (401 / 409 / 409 with full report) |
| Settings reveal | only *whether* a credential is configured, never which |

---

## Not verified, and why

1. **Everything Binance.** All hosts blocked here — including the testnet and the public
   data mirror. Endpoints, field names, kline array order, fee-tier encoding, and
   duplicate-order rejection are documented assumptions, not facts.
   Run `scripts/validate_binance.py` from a machine with egress; the gate refuses to arm
   until its output exists.
2. **Docker** — no daemon. Written, never run.
3. **Live Claude API** — no key available.
4. **Load beyond one operator** — sized for one process serving one dashboard.
5. **Regime-classification accuracy** — exercised, causality asserted, accuracy unmeasured.
6. **Database migrations** — clean install only.
7. **Long-horizon behaviour** — longest continuous run observed: 660 bars.

---

## Pending — built but not yet wired, or known-incomplete

Stated here so nobody discovers them in production. Full detail in `AUDIT_REPORT.md`
Part II §12.

1. **No real-time live runtime loop.** `RuntimeEngine` is scenario-driven (simulated
   clock, generated data). The Binance adapters, the gate and the economics all exist and
   are tested, but no orchestrator yet runs them together against real prices in real time.
2. **The activation token is minted and dropped.** `arm_live` verifies everything and
   returns the token; nothing stores it or constructs a live provider from it yet.
3. **`CapitalLedger` is a tested library, not yet the runtime's ledger.** `/api/capital`
   synthesizes from the paper portfolio; `classify_external_change` (the deposit/withdrawal
   classifier and the unexplained-balance halt) is never called in production.
4. **Edge evidence is in-memory only.** Closed trades, bucket coverage and the loss streak
   die with the process; the paper track record the gate checks resets on restart.
5. **`enforce_expected_value` is never switched on automatically** — live mode should set
   it; today only a caller who passes it explicitly gets enforcement.
6. **`min_paper_days` is configured but unread** — the track-record probe counts trades
   only.
7. **Latency is configured, not measured** — the cost model prices the simulator's
   configured delays; a live deployment must measure decision-to-fill.
8. **Multi-fill exits are scored at the last fill's price**, not exit VWAP.
9. **No request-weight limiter on the Binance adapter** — it reacts to 429 but does not
   pace itself.
10. **No frontend Capital view** — the endpoint and types exist; no page consumes them.
