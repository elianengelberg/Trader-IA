# System Status

Generated after a full `make verify` run on 2026-08-13. Every PASS below corresponds to
something that was executed, not reviewed. Every NOT VERIFIED says why.

---

## Verdict by area

| Area | Status | Evidence |
|---|---|---|
| **BACKEND** | **PASS** | 571 tests; the runtime processes bars, decides, sizes and executes end to end |
| **FRONTEND** | **PASS** | 11 views rendered in headless Chromium, zero console errors |
| **DATABASE** | **PASS** | schema creates from scratch on SQLite and PostgreSQL; FK cascade, upsert dedup and queries exercised |
| **EVENT BUS** | **PASS** | in-process bus under test; duplicate events rejected by a unique index, not just in memory |
| **MARKET DATA** | **PASS** | seeded synthetic generator and CSV replay, both reproducible byte-for-byte |
| **QUANT** | **PASS** | indicators, features and statistics against known values and property tests |
| **STRATEGY** | **PASS** | library, fusion and regime gating; the asymmetry rule property-tested |
| **CLAUDE / AI LAYER** | **PASS (mock)** · **NOT VERIFIED (live)** | full pipeline on the offline mock and adversarial inputs; no API key was available, so no live call was ever made |
| **RISK** | **PASS** | absolute veto verified through the library, the API and the browser |
| **EXECUTION SIMULATOR** | **PASS** | order state machine, matching engine, slippage, fees, partial fills, reconciliation |
| **BACKTESTING** | **PASS** | engine, five mandatory baselines, walk-forward, two independent look-ahead detectors |
| **MONITORING** | **PASS** | health endpoint, Prometheus metrics, live log stream, per-component status |
| **FAILURE HANDLING** | **PASS** | 12 injected failures: LLM outage, unknown provider exception, corrupted feed, phantom position, safe mode, database loss, schema mismatch, restart, event redelivery |
| **SECURITY** | **PASS** | see the table below |
| **END-TO-END** | **PASS** | the full flow, asserted by an automated test and reproduced in a browser |
| **DOCKER** | **NOT VERIFIED** | no Docker daemon in the build environment; the compose file has never been run |

---

## What `make verify` reports

```
PASS  Lint (ruff)
PASS  Unit tests
PASS  Property tests
PASS  Failure injection
PASS  End-to-end pipeline
PASS  Frontend type check
PASS  Frontend build
PASS  Smoke test            RESULT: PASS — every view rendered, no console errors

ALL CHECKS PASSED
```

Totals: **571 Python tests**, ruff clean, TypeScript clean, browser smoke PASS.

---

## The end-to-end flow, as observed

```
USER → WEB (login)
     → START PAPER TRADING (simulated capital 25,000)
     → MARKET DATA          660 bars ingested
     → ANALYSIS             features, regime, strategies
     → AI                   531 context assessments, every modifier ≤ 0
     → VALIDATION           schema + business rules; failures degrade to neutral
     → RISK                 3 approved, 123 rejected, each attributed to a named check
     → PAPER ORDER          3 order intents
     → FILL                 3 fills with modelled slippage and fees
     → POSITION             opened and closed
     → P&L                  realised and shown
     → DASHBOARD            live over SSE
     → AUDIT LOG            every step recorded and queryable
```

Asserted by `tests/e2e/test_end_to_end.py::test_the_complete_paper_trading_pipeline`, and
reproducible: the same scenario and seed produce identical fills.

---

## Security

| Check | Result |
|---|---|
| Unauthenticated access to any data or control endpoint | **refused** |
| Login is not a username oracle | **verified** — identical response either way |
| Password storage | **PBKDF2-HMAC-SHA256**, per-password salt, constant-time compare |
| JWT: wrong secret, tampered payload, `alg:none`, expired | **all rejected** |
| Session cookie | **HttpOnly, SameSite=Strict, Secure under HTTPS** |
| Login brute force | **rate limited** |
| SQL injection (path + query, 8 payloads) | **no effect** |
| Path traversal (5 encodings) | **no host file returned** |
| Oversized body | **refused** |
| Error responses | **no traceback, path or driver name** |
| CSP / X-Frame-Options / nosniff / Referrer-Policy | **present on every response** |
| Secrets in API responses | **none**; only *whether* a key is configured |
| Database password in logs | **masked** |
| Routes for deposit / withdraw / transfer / bank / card / broker / custody | **none exist** |
| Risk-limit mutation from the UI or API | **no route exists** |

---

## Scope guarantees, mechanically enforced

| Guarantee | Mechanism |
|---|---|
| No real-money execution | `ExecutionProvider.__init__` raises on `is_simulated=False`; asserted across every subclass |
| The LLM cannot create or enlarge risk | modifier clamped to `[-1, 0]` in the type, re-clamped at conversion, re-asserted in the service |
| The LLM cannot express a trade | its response schema has no quantity, price, side, type or leverage field |
| Free-form model output never becomes an order | forced tool call; a text-only reply raises rather than being parsed |
| Expired signals never execute | TTL checked by the risk engine at evaluation |
| The risk engine cannot be overridden | deterministic; consults no model; may only shrink a requested size |
| The system cannot rewrite its own limits | `RiskLimits` raises on mutation; no API route changes it |
| No claim of profitability | verdict vocabulary contains nothing meaning "good"; a disclaimer on every page |

---

## Not verified, and why

1. **Docker** — no daemon in this environment. Written, reviewed, never executed.
2. **Live Claude API** — no key available. Failure paths tested with a scripted provider;
   no live call made.
3. **Binance / TradingView** — both hosts blocked by the egress proxy. Zero requests ever
   made. Opt-in, refused by the demo environment, labelled `REQUIRES VALIDATION`.
4. **Load beyond one operator** — the SSE fan-out, the in-process rate limiter and the
   SQLite writer are sized for one process serving one dashboard.
5. **Regime-classification accuracy** — the classifier is exercised and its causality is
   asserted; its accuracy against labelled regimes is not measured.
6. **Database migrations** — clean install works; there is no automated upgrade path.
7. **Long-horizon behaviour** — the longest continuous run observed is 660 bars.

---

## On the trading results

The current configuration, on the committed fixtures, produces a **small loss** and a
verdict of **insufficient evidence** against five baselines. It has not been tuned, and
tuning it was not the goal of this work.

That is the honest output, and the reporting layer is built so it stays honest: a return
is never shown without its baselines, the strongest available verdict is "beat all
baselines on this dataset", and there is no code path anywhere in the repository that
produces the sentence "this strategy wins".
