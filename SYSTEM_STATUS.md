# System Status

Generated after the 24/7 deployment pass and a full `make verify` run on 2026-08-14.
Every PASS below corresponds to something that was executed, not reviewed. Every NOT
VERIFIED and every PENDING says why.

The platform's scope changed on 2026-08-13 (Part II of `AUDIT_REPORT.md`); the hardening
pass (Part III) closed the built-vs-wired distance; and the 24/7 pass added the
paper-realtime session (real data shape, simulated fills, no token), the watchdog/
heartbeat layer, crash-resume-with-sticky-operator-intent restart semantics, the alert
webhook seam, the production compose stack, and the operational scripts. See
`docs/DEPLOYMENT.md` for the deployment path.

---

## Verdict by area

| Area | Status | Evidence |
|---|---|---|
| **BACKEND** | **PASS** | 833 tests; the runtime processes bars, decides, budgets, prices, and executes end to end |
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
| **CAPITAL LEDGER** | **PASS** | Decimal internals; wired into the LiveRuntime: funded at start, drift classified, unexplained moves halt entries |
| **LIVE ACTIVATION GATE** | **PASS** | 27 checks, unforgeable expiring token bound to a config fingerprint; arming persists the attempt and starts the runtime — LIVE is reported only on RUNNING |
| **LIVE RUNTIME** | **PASS (against fakes)** · **NOT VERIFIED (venue)** | 13-state machine, kill switch, emergency flatten, unknown-order resolution, scheduled reconciliation, clock-skew monitor, measured latency; 27 tests |
| **PAPER-REALTIME 24/7** | **PASS (against fakes)** · **NOT VERIFIED (venue)** | same LiveRuntime over simulated execution, no token by design; heartbeat, market-data staleness watchdog, provider-failure escalation to SAFE_MODE; crash-interrupted sessions resume on boot, operator stops and kill switches stay down — all asserted by API-level restart tests |
| **ALERTS** | **PASS (seam)** · webhook delivery NOT VERIFIED | incidents persist, broadcast over SSE, and POST to `TIA_ALERT_WEBHOOK_URL` (payload scanned for secrets by test); no real webhook was reachable here |
| **REGIME ACCURACY (synthetic)** | **MEASURED** | `make regime-accuracy`: settled primary accuracy 16–51% by scenario vs generator ground truth (weakest on high-volatility); confusion matrices in `data/runtime/regime_accuracy.json`. Real-market accuracy remains UNVALIDATED — no trusted labels exist here |
| **MIGRATIONS** | **PASS** | Alembic 0001/0002; empty→head and v1→v2 in place, rows preserved |
| **ENDURANCE** | **PASS** | 1,660 simulated bars, 6/6 checks; found and led to the fix of D12 |
| **BINANCE EXECUTION** | **NOT VERIFIED** | adapter logic tested against mock transport (26 tests); no request has ever reached Binance; `scripts/validate_binance.py` closes the gap |
| **CLAUDE / AI LAYER** | **PASS (mock)** · **NOT VERIFIED (live)** | full pipeline on the offline mock and adversarial inputs; no API key available |
| **EXECUTION SIMULATOR** | **PASS** | order state machine, matching, slippage, fees, partial fills, reconciliation |
| **BACKTESTING** | **PASS** | engine, five baselines, walk-forward, two independent look-ahead detectors |
| **MONITORING** | **PASS** | health endpoint, Prometheus metrics, live log stream, per-component status |
| **FAILURE HANDLING** | **PASS** | injected failures incl. LLM outage, corrupted feed, phantom position, safe mode, restart, redelivery |
| **SECURITY** | **PASS** | see the table below; secret-leak tests scan whole response bodies including error paths |
| **END-TO-END** | **PASS** | full flow asserted by automated test and reproduced in a browser |
| **DOCKER (demo + prod)** | **NOT VERIFIED** | no daemon in the build environment; `docker-compose.prod.yml` (Caddy HTTPS proxy, internal-only Postgres, daily backups, restart unless-stopped) authored but never run — `make production-readiness` proves it on a real machine or honestly exits 3 |
| **CI WORKFLOW** | **NOT VERIFIED** | `.github/workflows/ci.yml` mirrors `make verify`; it has never executed because this environment cannot reach GitHub Actions |
| **OPS SCRIPTS** | **PASS (local paths)** · Docker paths NOT VERIFIED | `backup.sh` exercised against SQLite (dump verified restorable); `daily_report.py` verified against a populated journal; `deploy.sh`/`production_readiness.sh` exit 3 without a daemon, as designed |

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

Totals: **833 Python tests**, ruff clean, TypeScript clean, browser smoke over 14 views.

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
   until its output exists — and now refuses a record whose key fingerprint does not
   match the configured credential.
2. **Docker (demo and production stacks) and CI** — no daemon here, no Actions runner.
   Written, syntax-checked where possible, never run. `make production-readiness` is the
   proof procedure and exits 3 rather than pretending.
3. **Live Claude API** — no key available.
4. **Load beyond one operator** — sized for one process serving one dashboard.
5. **Regime-classification accuracy on real markets** — now *measured against synthetic
   ground truth* (`make regime-accuracy`: settled 16–51% by scenario, weakest on
   high-volatility — a known, quantified weakness); real-market accuracy still has no
   trusted labels and remains unvalidated.
6. **Database migrations against a populated Postgres** — SQLite empty→head and v1→v2
   are tested; Postgres migration tested from empty only.
7. **Long-horizon behaviour** — longest continuous run observed: 1,660 simulated bars.
8. **Webhook alert delivery** — the POST is tested against a fake transport; no real
   Discord/Slack/ntfy endpoint was reachable from here.

---

## Remaining, honestly

1. **Everything Binance-facing needs external validation** — run
   `scripts/validate_binance.py` (now a fingerprinted v2 record the gate schema-checks,
   freshness-bounds and refuses if tampered). The gate cannot arm without it. B1/B2/B3.
2. **WebSockets are deliberately not implemented** until the listenKey path is validated;
   polling is the stated mechanism (adequate for 1m bars). C8.
3. **Fire-and-forget persistence can drop a row** under a rare FK ordering race (1 fill
   row in ~2,100 endurance bars); accepted and documented — persistence never blocks
   trading, and the endurance coherence check watches the evidence store.
4. **Regime accuracy is now measured on synthetic data** (F3): settled primary accuracy
   16–51% depending on scenario — a real number with a real caveat (generator parameters
   as ground truth). Real-market accuracy remains UNVALIDATED; no metrics were invented.
5. Inherited: single-operator sizing; simulation layers stay float by design (Decimal
   governs settlement paths); the paper simulator has no order book.
