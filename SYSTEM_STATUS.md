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
| **MARKET DATA (Binance public)** | **PASS (verified against mainnet)** | 2026-08-18 from a Frankfurt VPS: `validate_binance.py` 5/5 — reachable, clock skew 131 ms, kline array order confirmed (BTC live), bookTicker fields, and the spot filters (step 0.00001, tick 0.01, minNotional 5 USDT). Facts written to `binance_validation.json`; the gate's binance_validated check reads it |
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
| **DOCKER (prod stack)** | **PASS (executed on a real VPS)** | 2026-08-18, DigitalOcean 2 vCPU/2 GB: full stack healthy behind Caddy HTTPS, migrations applied against Postgres, postgres unpublished, and the readiness drill's in-container SIGKILL recovered on its own — PRODUCTION READINESS: PASS. Three first-boot defects found and fixed by running (folded-scalar newline in the backend command; uvicorn's `--log-config /dev/null` crashing on Python 3.11; the drill itself using `docker kill`, which restart policies rightly ignore) |
| **DOCKER (demo + local stacks)** | **NOT VERIFIED** | share the now-validated Dockerfile and entry point, but have not themselves been executed — `make local-readiness` proves the local stack on a real PC or honestly exits 3 |
| **CI WORKFLOW** | **PASS (executed)** | run #1 failed honestly (phantom test dependency `asgi-lifespan`, hidden by the local venv — fixed by declaring it); run #2 on `afdf52b` green end to end on GitHub Actions: lint, 835 tests, migrations from empty, frontend typecheck + build |
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

1. **Binance public data: VERIFIED** (2026-08-18, Frankfurt) — reachability, clock skew,
   kline array order, bookTicker fields and spot filters confirmed against mainnet by
   `validate_binance.py` (5/5). **Still assumptions:** the signed/account path (fees,
   permissions, listenKey) and order lifecycle/duplicate-rejection — these need testnet
   keys and `--account --order`, which is a separate, later step and NOT needed for the
   24/7 paper session. Note the US geo-block: `api.binance.com` answers US datacenter IPs
   with HTTP 451, so the deployment region must be outside the US.
2. **Docker (demo and production stacks)** — no daemon here. Written, syntax-checked
   where possible, never run. `make production-readiness` is the proof procedure and
   exits 3 rather than pretending. (CI is no longer on this list: it executed green on
   GitHub Actions, run 31815272053.)
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

---

## Addendum, 2026-10-03 — what changed since the table above was written

The table and the lists above are the 2026-08-14 state and are kept as written. The rows
below supersede them where they differ. Each entry names the run that moved it.

| Area | Status now | Evidence |
|---|---|---|
| **MARKET DATA (WebSocket)** | **PASS (verified against the venue)** | directional session: kline + bookTicker stream with REST fallback (commit `de315fc`); market maker: depth@100ms + trade + bookTicker with the official snapshot/sequence procedure, recorder and replay — Phase 2 declared PASS by the operator on the VPS, 2026-09-18 (`docs/MARKET_MAKING_PHASE2_REPORT.md`) |
| **MIGRATIONS** | **PASS** | Alembic 0001–0006; empty→head in CI on every push |
| **BINANCE EXECUTION** | **PASS (Spot Testnet, building blocks) · NOT VERIFIED (fills; the full live service against a venue; Mainnet)** | 2026-10-03, commit `1ebc584`, `scripts/validate_mm_testnet.py` from the VPS: REST + venue time, signed WebSocket API account-stream subscription, account and balances, exchange filters, one LIMIT_MAKER placed and acknowledged (REST and `executionReport` NEW), clientOrderId↔orderId correlation, cancel confirmed by `executionReport` CANCELED and by REST (by orderId), no phantom fill, deduplication, stream cut → safe state → REST reconciliation → reconnect, latency legs, Testnet-only rails, no activation token, cleanup with zero open orders. NOT TESTED: partial fill, report+myTrades single booking, fill→ledger latency (no fill was produced by design). Evidence file: `docs/evidence/README.md` index |
| **USER DATA STREAM** | **PASS (Testnet)** | the listen-key stream was retired by the venue on 2026-02-20 (HTTP 410); replaced by `userDataStream.subscribe.signature` on the WebSocket API (commit `a2d050e`), confirmed on Testnet the same day |
| **MARKET MAKER, paper (Phase 3)** | **IMPLEMENTED · running only when the operator enables it on the VPS** | `docs/MARKET_MAKING_PHASE3_AUDIT.md` §21–22: the verdict is NO EDGE DETECTED until TRAIN/VALIDATION/OOS history exists; PROFITABLE is not a state |
| **MARKET MAKER, live architecture (Phase 4)** | **IMPLEMENTED, NOT ACTIVATED · Testnet-validated as above** | `docs/MARKET_MAKING_PHASE4_LIVE_ARCHITECTURE.md`; no token, no `.env` change, `TIA_MM__REAL_MONEY` has no readers |

Of the "Remaining, honestly" list: item 1 is closed for the public and Testnet paths and
open for Mainnet account facts (`make binance-account` with real keys has not been run);
item 2 is closed (WebSockets are implemented and validated); items 3–5 stand.

## Addendum, 2026-10-04 — market maker, live path: validation matrix

Levels, in order of strength: IMPLEMENTED → UNIT TESTED (fake venue, fake stream) →
INTEGRATION TESTED (API and service wired together, still fake venue) → TESTNET VALIDATED
(observed against Binance Spot Testnet; evidence in `docs/evidence/`) → PRODUCTION VALIDATED
(never, by rule: no Mainnet, no real money).

| Component | Unit | Integration | Testnet | Production | State |
|---|---|---|---|---|---|
| Binance REST adapter: signing, account, filters, LIMIT_MAKER place/cancel/query by orderId | yes | yes | **yes** (2026-10-03, two runs) | no | VALIDATED on Testnet |
| Account stream: signed WebSocket API subscription, NEW and CANCELED reports, reconnect | yes | yes | **yes** | no | VALIDATED on Testnet |
| Account stream: TRADE report fields (`t`, `m`, `l`, `L`, `n`, `N`), `outboundAccountPosition` after a fill | yes | yes | **no** (no print in 300 s at the best bid) | no | NOT TESTED on the venue |
| Execution state machine: NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED, UNKNOWN; idempotent cancel; -2013; duplicate reports; REST and stream coexisting | yes (+ synthetic adversarial suite) | yes | partly (NEW, CANCELED, duplicate reports, stream cut and reconnect) | no | PARTIALLY VALIDATED |
| Fills: report → correlation → single booking (report + myTrades) → LiveLedger → P&L → balances | yes (+ adversarial) | yes | **no** | no | NOT TESTED on the venue |
| LiveLedger: seed from venue balances, fees in quote/base/third asset, reconciliation with adoption | yes | yes | seed and no-fill reconciliation only | no | PARTIALLY VALIDATED |
| LiveMarketMakerService: start_live → reconcile → quote → stop, periodic reconciliation, heartbeat, kill switch | yes | yes | **yes, 3 min on 2026-10-04** (33 quotes placed, acknowledged and cancelled through the venue; 13 reconciliations; stream 65 reports; clean shutdown) — with one FAIL: a sticky kill from a reconciliation false positive, root-caused and fixed (`docs/MARKET_MAKING_PHASE4_LIVE_ARCHITECTURE.md` §10.4); the fixed code has not been re-run on the venue yet | no | PARTIALLY VALIDATED |
| `/api/mm/live/*`: status, start, stop, kill-switch, reconcile | yes | yes | no | no | INTEGRATION TESTED |
| Market data (Phase 2): depth, trade, bookTicker, book integrity, recorder, replay | yes | yes | Mainnet public streams, 2026-09-18 | no | VALIDATED (public data) |
| Safety rails: Testnet-only hosts, no token, no MARKET or plain LIMIT path, `TIA_MM__REAL_MONEY` unread | yes (boundary tests) | yes | **yes** (both runs) | no | VALIDATED |

Defects found and fixed in this pass (2026-10-04, see the commit): the final reconciliation at
`stop()` did not book a fill known only to the trade history (ledger short by the fill, mismatch
deferred to a reconciliation that never comes); a TRADE report arriving before any
acknowledgement left the order filled but never acknowledged. Observability gap closed: a
sticky engagement of the maker's kill switch is now an incident (alert webhook), not only a
journal row.

What the market maker does **not** do, by the operator's decision of 2026-09-18 (Phase 3 §17 D1):
it does not call `RiskEngine.evaluate` nor `ExpectedValueEngine.evaluate` with an invented
directional signal. It reads the session risk engine's *state* through the global safety gate
(halted, safe mode, degraded → no quoting), has its own risk controller and economics
authorizer, and nothing in `tia/learning` is consulted on the quoting path.

Addendum 2026-10-04, later the same day: the service run on Testnet exposed a reconciliation
false positive (the venue's open-orders snapshot compared against a local picture read later,
with the maker's own cancels in between classified as orders nobody manages) that engaged the
sticky kill switch; fixed with the snapshot's age told apart from real findings, a two-strike
rule for orders the venue keeps listing open, and a resolve-by-id path that reopens and cancels a
genuine zombie. The safety state model is now written down (§11 of the Phase 4 document).

Addendum 2026-10-04, second service run (180 s, commit `8608db6`): the reconciliation fix held
(0 unknown orders, 13 clean reconciliations, 62 quotes placed and cancelled through the venue,
transient stale-data blocks that recovered on their own). One FAIL remained, S10b: the stop was
recorded as a sticky kill and a stale-data transient engaged in the last heartbeat survived the
stop. Resolved as a state-model decision: a deliberate shutdown is its own state, clears what
nothing can observe any more, and leaves any real safety engagement visible (Phase 4 §10.5, §11).

Addendum 2026-10-04, third service run attempt (commit `7b748d2`): stopped at S0, latency profile
not found. The profile lives in the production data volume and was measured against Mainnet public
data; a Testnet run now measures its own profile against Testnet into a separate directory
(`mm_market_data_check.py --rest-url/--stream-url`, `scripts/run_mm_service_testnet_validation.sh`).
Phase 4 §10.7. The run itself is still pending.

Addendum 2026-10-04, recovery and fills (code after `7e44954`): a run that died with quotes resting
left them at the venue unmanaged (the sticky kill cancels local orders only). start_live() now
sweeps the previous run's orders by id before placing anything, journals and raises an incident;
the venue's refusal still ends in a sticky kill. The block validator's fill probe rests both sides
at the best and re-pegs, maker-only; the service validator gained a recovery drill. Both Testnet
runs are still pending: nothing after `8608db6` has run on Testnet. Phase 4 §10.8 to §10.11.

Addendum 2026-10-04 16:27Z, full runbook on `f85b3ef` (Phase 4 §10.12): latency profile measured
against Testnet; service run 180 s with 183 orders, 0 unknown, 12 clean reconciliations; S10b PASS
with the shutdown state; recovery drill R1 FAIL caused by the drill counting an order with a cancel
in flight as left behind (harness defect, fixed next; R2/R4/R7 had nothing to sweep and are now
NOT TESTED in that case); the first real Testnet fill through the block harness: maker, booked once,
reconciled with zero delta, unwound flat. S8 at the service level and the orphan sweep against the
venue remain NOT TESTED. Nothing here is a claim about production readiness or profitability.

Addendum 2026-10-05 04:16Z, runbook with the recovery drill on `daef8e6` (Phase 4 §10.13): 27 PASS,
0 FAIL, S8 NOT TESTED. Recovery after a death with an order resting is now demonstrated against
Testnet: the second run swept the orphan by id before quoting, reconciled clean, adopted and resent
nothing. Still NOT TESTED: a fill of the service's own quotes, non-zero fees, runs longer than 3 min.
A ~1 s event-loop stall per run remains unexplained. No claim about production or profitability.

Addendum 2026-10-05, S8 experiment (Phase 4 §10.14): the engine cancels every one of its Testnet
orders because its quotes rest 10 bps off the mid (cost floor assuming 10 bps of fee), live one
second and are replaced on a 0.5 bps move. The service validator gained three EXPERIMENTAL,
harness-only overrides (--fee-scenario testnet_zero, --quote-ttl-ms, --requote-threshold-bps),
recorded in the evidence, with production defaults unchanged and every safety rail untouched; and
it now records per-order lifecycles, fill correlation and event-loop stalls. Not a strategy, not a
fee assumption for Mainnet, not a profitability claim. The 30-minute run has not been executed.

Addendum 2026-10-05 05:39Z, the S8 experiment run on `e5b5625` and its control (Phase 4 §10.15):
30 minutes under the EXPERIMENTAL harness overrides: 27 PASS, 0 FAIL, 0 NOT TESTED. Twenty-four real
maker fills of the engine's own quotes reached the ledger through the account stream, 24/24
correlated, booked once, including one real partial fill; 17 would-cross orders were refused by
the post-only rail; 1301 of 1309 cancels confirmed, 0 unknown, 239 transient stale-data kills and
none sticky, 116 clean reconciliations, final delta zero, 0 event-loop stalls over 200 ms. The
control run one hour earlier with the production defaults (30 minutes, `0ea5286`) placed 874 orders
and filled none. The harness classifier did not know the engine's two no-quote cancel reasons
(654 rows recorded as `other`) and the S10 note counted engagements from the bounded history;
both corrected in the harness only, evidence unchanged. S8 is VERIFIED TESTNET only under the
experimental parameters: not a strategy, not a fee assumption for Mainnet, not a profitability
claim, nothing about production or real money. Still NOT TESTED: a fill with the production
defaults, non-zero fees, `/api/mm/live/*` against Testnet, runs longer than 30 minutes.

Addendum 2026-10-05, markout instrumentation (Phase 4 §10.16): the economic audit of the e5b5625
run could only infer the 1 s adverse selection, clipped, from the toxicity EWMA. The engine now keeps,
as evidence only, every mid it shows the markout tracker, one context record per fill (inventory
before and after, both quotes, fair value and confidence at the quote, toxicity and data age at the
quote and at the fill, resting time) and the tracker's raw per-horizon markouts (target, mark time,
delay, mid at mark, bps, usd, measured or not, with the resolution rule stated verbatim); the service
validator exports them and checks their consistency (item S8e). No decision, estimator, limit or rail
changed: the synthetic tape's decision/fill/markout journal keeps its pre-change SHA-256, pinned in
tests. The next Testnet run has not been executed.
