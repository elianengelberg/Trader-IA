# Trader-IA — Architecture (Stage 1, definitive)

> **Scope guard.** This platform runs **only** in backtesting, simulation, paper trading,
> shadow trading and research. It never transfers, custodies or risks real money. No
> component can place an order at a real venue: there is no live execution adapter, and the
> `ExecutionProvider` implementations shipped here are simulators. See
> [SECURITY.md](SECURITY.md) §1 and [PAPER_TRADING.md](PAPER_TRADING.md) for the boundary and
> its enforcement tests.
>
> **No performance claim is made.** Backtest and paper results describe *what an experiment
> produced under stated conditions*. They are not evidence of future returns.

---

## 1. The problem, stated precisely

Build a system that can answer, with reproducible evidence, a single question:

> *Does a given decision process produce a statistically detectable edge, out of sample,
> after realistic costs — and can we tell why it did or didn't?*

Everything in the design follows from that. The platform is a **measurement instrument**
first and a trading system second. Ordering of concerns:

```
ROBUSTNESS   > COMPLEXITY
CORRECTNESS  > SPEED
REPRODUCIBILITY > ATTRACTIVE RESULTS
RISK CONTROL > TRADE FREQUENCY
DATA QUALITY > SIGNAL QUANTITY
NO_TRADE     > BAD TRADE
```

---

## 2. Architectural spine

### 2.1 Two speeds, one code path

```
┌──────────────────────────── FAST LOOP (deterministic, µs–ms) ────────────────────────────┐
│  ingest → normalize → validate → data-quality → features → regime → strategies →         │
│  signal candidate → RISK ENGINE (veto) → order intent → execution simulator → fills      │
│  No LLM. No network calls. Pure functions over immutable snapshots. Seeded RNG only.     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                       ▲                                             │
             context annotations                            events (append-only)
             (bounded, advisory)                                     │
┌──────────────────────────── SLOW LOOP (LLM, seconds) ────────────────────────────────────┐
│  news / macro / international events / regime narrative / strategy review / explanation   │
│  Claude → strict tool-use structured output → schema validator → business-rule validator  │
│  Emits ContextAssessment with a bounded confidence modifier ∈ [-1, 0] … see §7            │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**Claude is never on the critical path.** The fast loop reads the *most recent valid, not
expired* `ContextAssessment` from a cache. If none exists, the fast loop proceeds with a
neutral context and records `context_available=false` in the decision lineage. The slow loop
being down degrades explanation quality, never correctness.

### 2.2 The asymmetry rule (the single most important safety decision)

> **The LLM may only reduce risk-taking. It can never increase it.**

Concretely, the LLM's output is clamped to a *veto/dampen* channel:

* `context_modifier ∈ [-1.0, 0.0]` — multiplied into the deterministic confidence.
* `veto: bool` — forces `NO_TRADE`.
* It **cannot** raise confidence, change direction, set size, alter stops, or modify any
  risk limit.

This makes the worst case of a hallucination, a prompt injection through a news article, or
an API outage *fewer trades*, never a larger or unintended one. It is enforced in
`tia.strategy.fusion` and covered by `tests/unit/test_llm_cannot_increase_risk.py`.

### 2.3 Event-driven, not a polling loop

There is no `while True: ask_claude(); trade()`. Components are pure handlers over an
append-only event log. Any handler can be replayed, and replaying the log rebuilds state.

```
TickReceived ─┐
CandleClosed ─┼→ FeatureEngine → FeaturesComputed ─┐
              │                                     ├→ RegimeClassifier → MarketRegimeChanged
NewsReceived ─┼→ (slow loop) → ContextAssessed ─────┤
MacroEvent   ─┘                                     ├→ StrategyEngine → SignalCandidateCreated
                                                    │
DataQualityFailure ────────────────────────────────┤ (hard gate)
                                                    ▼
                                            RiskEngine → RiskDecisionCreated
                                                    ▼ (APPROVED | REDUCED_SIZE)
                                            OrderIntentCreated → ExecutionSimulator
                                                    ▼
                          OrderStateChanged → FillSimulated → PositionChanged → PnLUpdated
```

---

## 3. Components

| # | Component | Kind | Responsibility | Can it decide to trade? |
|---|---|---|---|---|
| 1 | `data.providers` | I/O | Fetch quotes/trades/candles, normalize to internal schema | no |
| 2 | `data.quality` | deterministic | Freshness, gaps, ordering, sanity, spread; emits scores | **can force NO_TRADE** |
| 3 | `quant.indicators` / `quant.features` | deterministic | Indicator + feature computation, point-in-time correct | no |
| 4 | `regime` | deterministic | Classify market regime from features | no |
| 5 | `agents.*` (deterministic) | deterministic | Market-data, technical, quant agents → `AgentFinding` | no (advisory scores) |
| 6 | `agents.*` (LLM) | probabilistic | News, macro, international, regime narrative | **veto/dampen only** |
| 7 | `strategy.*` | deterministic | Strategies + fusion → `SignalCandidate` | proposes only |
| 8 | `risk` | deterministic | Sizing + all limits + circuit breakers | **absolute veto** |
| 9 | `execution` | deterministic (seeded) | Order state machine + paper matching engine | executes approved intents only |
| 10 | `execution.reconciliation` | deterministic | Internal vs provider state; safe mode | can halt the system |
| 11 | `backtest` | deterministic | Historical replay through the *same* handlers | no |
| 12 | `llm` | probabilistic | Claude client, prompts, tools, budget, evaluation | no |
| 13 | `memory` | storage | Decision journal, lineage, experiment records | no |
| 14 | `persistence` | storage | Durable state, single source of truth | no |
| 15 | `observability` | cross-cutting | Logs, metrics, health, tracing | no |
| 16 | `runtime` | orchestration | Wires fast/slow loops, demo/shadow/backtest modes | no |
| 17 | `api` | interface | REST + WS for the dashboard | no |

### 3.1 Agent roster

Deterministic agents (code, not prompts) produce numeric scores with evidence:

* **MarketDataAgent** — price action, volume profile, volatility state, spread and liquidity.
* **TechnicalAgent** — trend, momentum, S/R, breakout/pullback, VWAP, RSI, MACD, ATR, MAs.
  Never decides on a single indicator: it requires ≥ 2 independent confirmations.
* **QuantAgent** — returns, volatility, correlation, expectancy, Sharpe, Sortino, drawdown,
  profit factor, win rate, distribution moments. **Claude never produces these numbers.**
* **RegimeAgent** — deterministic classification (trending/ranging × low/high vol, plus
  anomalous/crisis on extreme z-scores).

LLM agents (prompted, schema-constrained) produce `AgentFinding` objects with the same shape
but marked `source=llm` and restricted to the veto/dampen channel:

* **NewsAgent** — relevance, sentiment, credibility, contradiction detection, propagation.
* **MacroAgent** — inflation, rates, employment, GDP, central banks, bonds, FX, liquidity.
* **InternationalEventAgent** — crises, sanctions, conflicts, elections, trade.
* **StrategyContextAgent** — narrative synthesis, scenario comparison, invalidation
  conditions, human-readable explanation.

---

## 4. Data contracts

Every event is a `pydantic` model wrapped in a versioned envelope.

```python
class EventEnvelope(BaseModel, Generic[P]):
    event_id: str            # ULID-like, monotonic, deterministic under a seeded clock
    event_type: str          # "market.candle_closed"
    schema_version: int      # bumped on breaking payload change
    source: str              # "provider:synthetic", "engine:risk"
    occurred_at: datetime    # UTC — when the fact happened at the source
    ingestion_at: datetime   # UTC — when we received it
    recorded_at: datetime    # UTC — when we persisted it
    correlation_id: str      # groups everything caused by one root stimulus
    causation_id: str | None # the event that directly caused this one
    sequence: int            # per-stream monotonic
    idempotency_key: str     # dedup key; equal keys ⇒ same logical event
    payload: P
```

Rules enforced in code and tests:

1. All timestamps are timezone-aware UTC. Naive datetimes are rejected at the boundary
   (`ruff` DTZ rules + a runtime validator).
2. `event_type` → payload model mapping lives in a single registry
   (`tia.events.registry`). Unknown types are quarantined, never silently dropped.
3. Payloads are frozen (`model_config = ConfigDict(frozen=True)`); mutation is impossible.
4. Schema evolution is additive; a breaking change requires a new `schema_version` and an
   upcaster function registered alongside it.

### 4.1 Event catalogue

| Event type | Payload highlights |
|---|---|
| `market.tick_received` | symbol, bid, ask, last, size, venue |
| `market.candle_closed` | symbol, timeframe, OHLCV, trade count |
| `market.regime_changed` | symbol, from_regime, to_regime, evidence |
| `market.volatility_changed` | symbol, realized_vol, percentile, direction |
| `data.quality_failure` | symbol, failed_checks[], scores, action_taken |
| `data.provider_disconnected` | provider, reason, last_message_at |
| `news.received` | headline, body_hash, source, published_at, symbols[] |
| `macro.event_detected` | indicator, actual, consensus, previous, surprise_z |
| `ai.context_assessed` | assessment_id, modifier, veto, thesis, evidence, expires_at |
| `strategy.signal_candidate_created` | signal_id, direction, confidence, ttl, snapshot_id |
| `risk.decision_created` | decision_id, verdict, approved_qty, checks[] |
| `order.intent_created` | intent_id, client_order_id, symbol, side, qty, type |
| `order.state_changed` | order_id, from_state, to_state, reason |
| `order.fill_simulated` | order_id, qty, price, fee, slippage_bps, latency_ms |
| `portfolio.position_changed` | symbol, qty, avg_price, realized, unrealized |
| `system.failure` | component, severity, error_code, recoverable |
| `system.safe_mode_entered` | reason, discrepancies[] |

---

## 5. Idempotency

The system assumes **at-least-once** delivery everywhere.

| Layer | Mechanism |
|---|---|
| Event ingestion | `idempotency_key` in a bounded LRU + Redis `SET NX` (TTL 24h) |
| Candle dedup | key = `(provider, symbol, timeframe, open_time)` |
| Webhook (TradingView) | key = HMAC of raw body + `X-TIA-Nonce`; replay window 5 min |
| Order submission | `client_order_id` = `blake2s(signal_id ‖ intent_hash)[:24]` — deterministic |
| Reconnect | last-processed `sequence` per stream is persisted; re-delivery is filtered |

A second delivery of the same intent is a **no-op returning the original order**, not a new
order. Property test: `tests/property/test_idempotency.py` replays a random event stream with
duplicates/reordering and asserts identical terminal state.

---

## 6. Data-quality engine (the first gate)

Before any feature is computed from a bar, the bar passes:

| Check | Failure → |
|---|---|
| Freshness (age vs timeframe × tolerance) | score↓, hard fail past cutoff |
| Timestamp sanity (future-dated, epoch-zero, non-UTC) | hard fail |
| Monotonic sequence / out-of-order | hard fail |
| Duplicate bar | dedup, score↓ |
| Gap detection (missing bars in the series) | score↓, hard fail past threshold |
| OHLC invariants (`low ≤ min(open,close) ≤ max(open,close) ≤ high`) | hard fail |
| Non-positive price, non-finite values | hard fail |
| Negative / absurd volume | hard fail |
| Spread anomaly (bps z-score vs rolling) | score↓, hard fail past threshold |
| Feed liveness | hard fail |

Two scores in `[0,1]` are produced — `DATA_QUALITY_SCORE` and `DATA_FRESHNESS_SCORE` — plus
a hard-fail flag. Any hard fail, or a composite below `min_data_quality` (default `0.75`),
yields `NO_TRADE` with reason `DATA_QUALITY`. This is checked **twice**: at feature time and
again inside the Risk Engine, so a stale path cannot slip through.

---

## 7. Decision pipeline and the LLM contract

```
FeatureSet + Regime
   ├─ Strategy A → StrategyOpinion(direction, strength ∈ [0,1], evidence[])
   ├─ Strategy B → ...
   └─ Strategy C → ...
            │  deterministic weighted fusion (weights are config, not learned at runtime)
            ▼
   base_confidence ∈ [0,1], direction ∈ {LONG, SHORT, HOLD, NO_TRADE}
            │
            ├─ × data_quality_factor          (≤ 1)
            ├─ × (1 + context_modifier)       (context_modifier ∈ [-1,0]  ⇒ factor ≤ 1)
            └─ if llm.veto or ttl expired ⇒ NO_TRADE
            ▼
   SignalCandidate{signal_id, expires_at, snapshot_id, strategy_version, model_version,
                   prompt_version, data_quality, evidence, invalidation_conditions}
            ▼
   RiskEngine (deterministic, may only shrink) → APPROVED | REDUCED_SIZE | REJECTED | NO_TRADE
            ▼
   OrderIntent → PaperExecutionProvider
```

### 7.1 Claude output schema

Claude is called with **strict tool use** (`strict: true`, forced `tool_choice`) so the
output is schema-validated by the API, then re-validated locally by Pydantic, then passed
through a business-rule validator. Free-form text is never parsed as an instruction.

```jsonc
{
  "decision": "LONG|SHORT|HOLD|NO_TRADE",     // advisory only
  "confidence": 0.0,                          // NOT a win probability — calibrated separately
  "context_modifier": -0.35,                  // clamped to [-1, 0] before use
  "veto": false,
  "thesis": "…",
  "supporting_evidence":   [{"claim": "...", "source_ref": "...", "observed_at": "..."}],
  "contradicting_evidence":[{"claim": "...", "source_ref": "...", "observed_at": "..."}],
  "market_regime": "TRENDING_UP|…",
  "relevant_events": ["..."],
  "invalidation_conditions": ["..."],
  "source_timestamps": ["..."],
  "data_quality": {"score": 0.0, "freshness": 0.0, "notes": "..."},
  "expiration": "2026-01-01T00:00:00Z",
  "strategy_id": "...", "model_id": "...", "prompt_version": "..."
}
```

`confidence` is **not** treated as P(win). A calibration layer
(`tia.llm.calibration`) bins historical confidences against realized shadow outcomes and
reports reliability curves and Brier score. Until calibrated, confidence only gates
thresholds, never sizing.

### 7.2 What Claude must never do

Multiplication, position sizing, limit evaluation, risk arithmetic, state arbitration, or
direct execution. Those live in `quant/` and `risk/` as tested pure functions.

### 7.3 Cost governance

Claude is not called per tick. `tia.llm.trigger_policy` fires only on:
relevant news, regime change, macro surprise beyond a z-threshold, anomaly detection,
a high-importance signal, or a periodic review interval. A `BudgetGovernor` enforces
calls/min, tokens/day and an estimated-cost ceiling, with a circuit breaker that degrades to
"no context" rather than blocking the fast loop.

---

## 8. Signal TTL and market snapshot

Every signal carries `created_at`, `expires_at`, `market_snapshot_id`, `strategy_version`,
`model_version`, `prompt_version`. On expiry → `NO_TRADE`. A snapshot stores exactly what the
system saw: prices, indicators, volatility, regime, news refs, macro refs, positions,
exposure, simulated capital, and all timestamps — so *"what did the system see?"* is always
answerable, and any decision can be replayed bit-for-bit.

---

## 9. Risk engine

Deterministic, pure, independently testable, with **absolute veto**. Checks, in order:

1. Kill switch / safe mode
2. Data quality + freshness gate
3. Signal TTL
4. Instrument tradability + liquidity floor (min volume/ADV)
5. Max spread (bps)
6. Volatility band (reject on vol beyond configured percentile)
7. Risk-per-trade budget → ATR-based position size
8. Max position notional, max units
9. Max gross / net exposure
10. Max concurrent positions
11. Correlated-exposure cap (per correlation cluster)
12. Concentration cap (per symbol / per cluster)
13. Daily loss limit
14. Max drawdown circuit breaker
15. Trade frequency / cooldown per symbol
16. Available simulated capital

Verdicts: `APPROVED`, `REDUCED_SIZE`, `REJECTED`, `NO_TRADE`. Every check emits an audit row
(`name, passed, observed, limit, action`) persisted with the decision. **No component can
override it — including Claude.** Enforced by `tests/unit/test_risk_veto_is_absolute.py`.

---

## 10. Order state machine

```
                  ┌──────────────┐
                  │   CREATED    │
                  └──────┬───────┘
                         ▼
                  ┌──────────────┐        ┌──────────┐
                  │  VALIDATED   │───────▶│ REJECTED │◀── (terminal)
                  └──────┬───────┘        └──────────┘
                         ▼
                  ┌──────────────┐
                  │RISK_APPROVED │
                  └──────┬───────┘
                         ▼
        ┌────────▶┌──────────────┐──────▶┌────────┐
        │         │  SUBMITTING  │       │ FAILED │ (terminal)
        │         └──────┬───────┘       └────────┘
        │                ▼
        │         ┌──────────────┐
        │         │  SUBMITTED   │
        │         └──────┬───────┘
        │                ▼
        │         ┌──────────────┐
        │         │ ACKNOWLEDGED │
        │         └──┬────────┬──┘
        │            ▼        ▼
        │  ┌────────────────┐ ┌────────┐
        │  │PARTIALLY_FILLED│▶│ FILLED │ (terminal)
        │  └───┬────────────┘ └────────┘
        │      ▼
        │  ┌──────────────────┐    ┌───────────┐   ┌─────────┐
        └──│ CANCEL_REQUESTED │───▶│ CANCELLED │   │ EXPIRED │ (terminal)
           └──────────────────┘    └───────────┘   └─────────┘
```

Transitions are declared in one table (`tia/execution/state_machine.py`); anything else
raises `InvalidStateTransitionError`. `transition()` is the only sanctioned way to change
an order's state — direct assignment is what lets an order reach `FILLED` without a fill.

Two structural properties of the table are asserted by tests rather than by convention:

* **`SUBMITTING` is reachable only from `RISK_APPROVED`.** This is the Risk Engine's veto
  expressed as reachability: there is no path to a venue that skips evaluation.
* **Every non-terminal state can reach a terminal one**, so no edit can produce an order
  that never finishes.

The table is property-tested over random transition sequences
(`tests/property/test_order_lifecycle_properties.py`): a random walk may only ever occupy
states the table permits, a rejected step must leave the order untouched, and no order
may escape a terminal state.

---

## 11. Reconciliation & failure modes

After any restart or provider reconnect:
read external state → read internal state → diff (orders, positions, balance, fill count)
→ classify → **enter SAFE MODE** on any critical divergence (no new intents; only
cancel/flatten and observation allowed).

**Reconciliation never repairs state.** It compares, classifies and escalates, and that
is a deliberate limit rather than an unfinished feature. Automatic repair is how a
reconciliation bug becomes a position: a component that "corrects" the ledger to match a
snapshot it misread will invent or erase exposure, and it will do so with more confidence
than the divergence that triggered it. When the two pictures disagree about anything that
implies risk, the correct action is to stop trading and involve a human. Leaving SAFE MODE
requires `RiskEngine.resume(approved_by=...)` — a named person, not a subsequent clean run,
which may only mean the divergence moved.

The taxonomy, and why each severity is what it is:

| Discrepancy | Severity | Why |
|---|---|---|
| `phantom_position` — venue holds what we do not | CRITICAL | No stop, size limit or exit logic is watching it; every risk check believes it does not exist |
| `orphaned_position` — we hold what the venue does not | CRITICAL | The risk the strategy thinks is on is not on |
| `position_quantity_mismatch` | CRITICAL | Sizing and exits are computed from the wrong exposure; a sign flip is called out separately |
| `unrecorded_fill` — venue filled, we did not record it | CRITICAL | Exposure exists that no risk check has seen |
| `order_state_mismatch` where we say terminal and the venue says open | CRITICAL | We have stopped watching something that can still trade |
| `order_state_mismatch`, benign lag (e.g. `submitted` vs `acknowledged`) | WARNING | Normal propagation delay |
| `unknown_order` in a filled state | CRITICAL | Same as an unrecorded fill |
| `unknown_order` in a terminal, unfilled state | WARNING | No exposure implied |
| `missing_order`, ours open | CRITICAL | An open order the venue does not report can still trade or has already |
| `missing_order`, ours terminal | WARNING | Record-keeping drift |
| `balance_mismatch` beyond tolerance | CRITICAL | Sizing derives from the balance, so a wrong balance mis-sizes every subsequent trade in the same direction |
| `fill_count_mismatch` alone | WARNING | A lagging-feed symptom; the fills that matter surface as position or order divergence |

Tolerances are absolute-floor-plus-relative so that floating-point residue on a large
quantity is not reported as a break, while the same absolute difference on a small one is.

| Failure | Expected state | Recovery | Notification | Audit |
|---|---|---|---|---|
| Market data outage | NO_TRADE, feed marked stale | reconnect w/ backoff, backfill, reconcile | health degraded + alert | `data.provider_disconnected` |
| Stale data | NO_TRADE | wait for fresh bar | health degraded | `data.quality_failure` |
| Provider API timeout | request retried, then feed stale | exponential backoff + jitter | alert on N consecutive | `system.failure` |
| LLM timeout / 429 | context unavailable, neutral modifier | circuit breaker, cached last valid assessment | metric + alert | `system.failure` |
| LLM schema violation | assessment discarded | no retry loop; counts to eval metrics | metric | `system.failure` |
| DB failure | writes buffered; SAFE MODE on persistent failure | retry, then halt intents | critical alert | `system.failure` |
| Redis failure | fall back to in-memory dedup, degraded | reconnect | warn | `system.failure` |
| Duplicate event | ignored | dedup store | none | counter |
| Malformed event | quarantined | dead-letter stream | warn | `system.failure` |
| Rejected order | order → `REJECTED` | no auto-retry | info | `order.state_changed` |
| Partial fill | position updated to filled qty | remainder tracked / expired | info | `order.fill_simulated` |
| Restart | reconcile then resume | see above | info | `system.safe_mode_entered` if diff |
| Network interruption | as outage | as outage | as outage | as outage |

**Which of these rows are actually tested**, stated precisely because the honest answer is
"most, not all":

* **Covered by `tests/failure/test_failure_modes.py`** — LLM timeout and schema violation,
  a provider raising something the service has never seen, a sustained outage opening the
  breaker, stale and corrupted market data, reconciliation divergence entering safe mode,
  safe mode refusing every subsequent signal, a database failure not stopping the trading
  loop, a schema-version mismatch being refused, state surviving a restart, and a
  redelivered event being rejected by the database.
* **Covered elsewhere** — duplicate order submission (`tests/unit/test_paper_execution.py`),
  rejected orders and partial fills (same), reconciliation discrepancy classification
  (`tests/unit/test_reconciliation.py`).
* **Not tested** — Redis failover and provider reconnection with backfill. Both need a
  live external service, which this environment does not have. They describe intended
  behaviour that has not been demonstrated, and are listed as such in `AUDIT_REPORT.md` §7.

---

## 12. Backtesting

The backtester **is** the runtime: it feeds historical events through the identical
handlers, with a `SimulatedClock` and the same `PaperExecutionProvider`. There is no separate
"backtest strategy code" that could drift from live behaviour.

The bar loop, in the order that makes look-ahead structurally impossible:

1. Advance the clock to bar *t*'s close. Nothing has seen bar *t* yet.
2. Match resting orders against bar *t*. An order created at bar *t-1*'s close fills at
   bar *t*'s **open**.
3. Build features from a backward-looking slice ending at bar *t* — the same bounded
   rolling buffer a live runtime holds, not the whole history.
4. Quality gate, regime, strategies, fusion.
5. Risk Engine. Only it may authorise size.
6. Submit an intent that cannot be matched until bar *t+1*.

Bias controls:

* **Look-ahead** — enforced by construction (the loop slices its input) and checked by two
  *different* detectors, because neither alone is sufficient. See §12.2.
* **Leakage** — walk-forward splits are purged, with an embargo between test windows. See
  §12.3 for the precise semantics, which are easy to get subtly wrong.
* **Survivorship** — the instrument universe is snapshot-dated; delisted symbols remain in
  the dataset with their delist date.
* **Unrealistic fills** — participation-rate cap per bar, spread cost, slippage model, fees,
  latency, and rejection modelling. §12.1.
* **Overfitting** — anchored and rolling walk-forward; parameter-sensitivity sweeps are
  planned and **not yet implemented**.

Every evaluated bar produces a `DecisionRecord` — direction, confidence, regime, feature
hash, risk verdict, approved size — including the bars that declined to trade. That log is
what makes "why didn't it act here?" answerable, and it is what the look-ahead test in
§12.2 compares; an equity curve cannot distinguish a decision that changed from a price
that changed.

### 12.1 What the paper simulator is not

Stating this plainly matters more than the cost model itself, because a reader who does
not know the limits will read a backtest number as a forecast.

1. **There is no order book.** Fills are matched against bar OHLCV, so queue position,
   iceberg orders and book-depletion dynamics do not exist.
2. **Our own orders have no effect on the market.** A strategy whose size would move the
   price is modelled as though it would not, which flatters large sizes. The
   participation cap and the sqrt-scaled impact term are an approximation of that cost,
   not a measurement of it.
3. **There is no venue behaviour** — no halts, no auctions, no exchange-specific reject
   reasons, no funding, borrow or margin costs.

Where a modelling choice was available, the engine takes the worse one: market orders
fill at the *next* bar's open plus adverse slippage and never at the signal bar's close;
limit orders require the price to trade *through* the limit rather than merely touch it;
a triggered stop fills at the worse of the stop level and the bar's open, so a gap costs
what a gap costs; a bar can only absorb `max_participation_rate` of its own volume; and
slippage is always adverse to the order and clamped inside the bar's actual range,
because a price that never traded is not a fill. Each of these is a named test in
`tests/unit/test_paper_execution.py`.

### 12.2 Two look-ahead detectors, because one is not enough

This was found while writing the tests, and it is worth stating because the obvious test
has a blind spot that looks like a pass.

* **Prefix comparison.** Run the pipeline over `bars[:n]` and over `bars[:m]` for `m > n`,
  and require the shorter run's equity curve and trades to be an exact prefix of the
  longer one's. This catches every leak that reaches *backwards* from the end of the
  sample: a z-score computed over full-sample statistics, a percentile rank, a
  forward-filled value, a normalisation constant fitted on everything.

* **Future perturbation.** Replace every bar after index *k* with a wildly different one
  and require every `DecisionRecord` at or before bar *k* to be byte-identical.

The second exists because the first **cannot detect a one-bar-ahead leak**. A rule that
reads bar *t+1* while deciding at bar *t* is stable under truncation — the value it steals
is the same in the short series and the long one — so both curves agree and the prefix
test passes while the strategy cheats. `tests/property/test_no_lookahead.py` demonstrates
this on a deliberately clairvoyant rule: it asserts that the prefix detector misses it and
that the perturbation detector catches it.

### 12.3 Purge and embargo, stated precisely

Each training window ends `max(purge_bars, embargo_bars)` bars before its test window
begins.

* The **purge** accounts for feature lookback straddling the boundary.
* Taking the **maximum** additionally guarantees that the preceding fold's embargo zone
  never lands inside the next fold's training set — which is exactly what happens in a
  rolling schedule whenever the purge is shorter than the embargo. Fold 0 has no preceding
  embargo zone, so the same cut is slightly conservative there, deliberately: folds with
  unequal training lengths are not comparable to each other.

**What is not a leak.** Earlier *test* windows do appear in later *training* windows. That
is what walk-forward is — as time passes, an evaluated period becomes history, and a real
system would refit on it. The protection is against a model seeing its *own* evaluation
period, not an earlier one.

`assert_no_leakage()` checks all of this against any plan, including one assembled by hand,
and `tests/unit/test_walkforward.py` proves the checker can actually fail.

### 12.4 Baselines

**Baselines are mandatory.** Five of them, each answering a different way of being fooled,
all evaluated on the same bars with the same fee and slippage assumptions — a baseline
computed on gross returns against a strategy computed on net returns is not a comparison.

| Baseline | The question it answers |
|---|---|
| buy and hold | Did the strategy add anything over simply owning the asset? |
| SMA cross | Did it beat the most obvious technical rule in existence? |
| volatility-targeted | Did it beat exposure sizing alone, with no view on direction? |
| random entry | Did it beat coin flips **matched on trade count and holding period**, so they pay the same costs? |
| always flat | The zero line, which a strategy paying real costs can genuinely fail to beat. |

The matching on the random baseline is the point: an unmatched random control trades a
different number of times, pays different costs and holds for a different duration, so
beating it proves nothing. Matched, it isolates whether the *timing and direction* carried
information. It is seeded, so the comparison cannot be re-rolled until it flatters.

### 12.5 Verdicts

`ExperimentVerdict` has four values and none of them means "good":
`INSUFFICIENT_EVIDENCE`, `NO_EDGE_DEMONSTRATED`, `MIXED`, `BEAT_ALL_BASELINES`. There is no
`PROFITABLE`, no `DEPLOY`, no `RECOMMENDED`, and no method anywhere in the package that
turns a result into a recommendation.

The sample-size question is asked **first**: below 30 closed trades the verdict is
`INSUFFICIENT_EVIDENCE` regardless of how good the comparison looks, because asking "did it
beat the baselines?" before "could this sample answer anything?" is how eleven trades
become a deployment decision. A strategy is also only counted as "ahead" of a baseline if
it is ahead on return *and* not materially worse on drawdown — one point more return for
twice the risk is leverage, not skill.

`scripts/run_backtest.py` runs the whole thing against the committed fixtures with no
network and no credentials, and prints the statement, the five comparisons, the
walk-forward schedule and the caveats.

---

## 13. Technology decisions

| Layer | Choice | Why this and not the alternative |
|---|---|---|
| Language | Python 3.11+ | Ecosystem for quant/ML; typing is now good enough with strict mypy. A Rust/C++ fast path is unnecessary — this is not HFT and pretending otherwise would be dishonest. |
| Contracts | Pydantic v2 | Rust-core validation, JSON-Schema export shared with the frontend and with Claude's tool schema. One definition, three consumers. |
| API | FastAPI + uvicorn | Native Pydantic integration, automatic OpenAPI, async. |
| Numerics | NumPy + pandas | Indicators are vectorized and unit-tested against hand-computed fixtures. |
| DB | SQLAlchemy 2.0 async; SQLite (demo) / PostgreSQL + TimescaleDB (real) | One ORM, two backends: the zero-config demo needs no server; Timescale hypertables + compression are the right fit for `candles`/`ticks` at scale. Timescale-specific DDL is applied conditionally so SQLite stays valid. |
| Migrations | Alembic | Standard, reviewable, reversible. |
| Cache | Redis | Also used for dedup and the LLM assessment cache. |
| Event bus | **Redis Streams** now; `EventBus` interface allows Kafka/Redpanda later | Consumer groups, acks, `XAUTOCLAIM` for stuck messages, and at-least-once semantics — sufficient for this throughput, one fewer system to operate than Kafka. The interface is the hedge: `KafkaEventBus` is a drop-in when partitions/retention actually matter. |
| Frontend | Next.js 15 (App Router) + React + TypeScript + Tailwind | SSR for first paint, one language for the whole UI, mature ecosystem. |
| Charts | `lightweight-charts` (Apache-2.0) | Purpose-built financial charting, tiny, and its licence permits use with attribution. |
| Containers | Docker + Compose | `docker compose up` is the demo contract. |
| Tests | pytest + pytest-asyncio + Hypothesis | Property tests are essential for the state machine and idempotency. |
| Types | mypy | `disallow_untyped_defs` on the package. |
| Lint | ruff (incl. `DTZ`, `S`, `ASYNC`) | `DTZ` mechanically prevents naive-datetime bugs — the classic trading-system defect. |
| Docs | Markdown + generated OpenAPI | Kept beside the code and checked by tests where possible. |

### 13.1 Integration status (rule §3)

| Integration | Status | Evidence / caveat |
|---|---|---|
| Anthropic Claude Messages API — strict tool use, structured outputs, model IDs, pricing | **CONFIRMED** | Verified against the bundled `claude-api` reference this session. Default model `claude-opus-5`; adaptive thinking; `strict: true` tool schema. |
| Synthetic market data provider | **CONFIRMED** | Ships in-repo; deterministic, seeded, no network. |
| CSV / fixture replay provider | **CONFIRMED** | Ships in-repo with committed fixtures. |
| `lightweight-charts` (Apache-2.0, npm) | **CONFIRMED** | Licence and package verified via search this session; attribution logo enabled in the UI. |
| TradingView webhooks | **REQUIRES VALIDATION** | Public sources indicate: paid plan required, POST to ports 80/443 only, JSON or text body, no custom auth headers, senders `52.89.214.238 / 34.212.75.30 / 54.218.53.128 / 52.32.178.7`. **tradingview.com is blocked by this environment's egress proxy, so I could not read the primary source.** The gateway is implemented defensively (shared-secret in body + HMAC + nonce + IP allowlist + replay window) and is **disabled by default**. |
| TradingView as a broker | **NOT SUPPORTED (by design)** | Broker integration requires a signed partner agreement and a private spec. Out of scope; TradingView is auxiliary signal input only. |
| Binance public REST market data | **REQUIRES VALIDATION** | Implemented against the documented public endpoint shape (`GET /api/v3/klines`, no API key for market data). **`api.binance.com` and `developers.binance.com` are both blocked by this environment's proxy — I could not execute a single request to verify.** Opt-in only; the demo never uses it. |
| Alpaca / Polygon / other vendors | **NOT IMPLEMENTED** | Would need credentials the user has not provided and network access this environment does not have. The `MarketDataProvider` interface is the extension point. |
| Real-money execution venue | **NOT SUPPORTED — deliberately** | No adapter exists and none may be added under this scope rule. |

---

## 14. Repository structure

```
Trader-IA/
├─ packages/tia/src/tia/         # the single Python package
│  ├─ core/          config, clock, ids, errors, logging, rng, types
│  ├─ events/        envelope, registry, bus (memory/redis), idempotency, dead-letter
│  ├─ domain/        instruments, orders, positions, portfolio, signals, enums
│  ├─ data/          providers/{synthetic,csv,binance}, normalize, quality, snapshot
│  ├─ quant/         indicators, features, statistics, metrics, correlation
│  ├─ regime/        classifier
│  ├─ agents/        base, market_data, technical, quant, macro, news, international, regime
│  ├─ strategy/      base, trend, mean_reversion, breakout, fusion, engine
│  ├─ risk/          engine, limits, sizing, circuit_breakers, models
│  ├─ execution/     state_machine, provider (protocol), paper, models, reconciliation
│  ├─ backtest/      engine, splitters, baselines, report, experiments
│  ├─ llm/           client, anthropic_client, stub, schemas, prompts/, tools, budget,
│  │                 trigger_policy, redaction, calibration, evaluation
│  ├─ memory/        journal, lineage
│  ├─ persistence/   models, session, repositories, migrations/
│  ├─ observability/ logging, metrics, health, tracing
│  ├─ api/           app, routers/, deps, security, schemas, ws
│  ├─ runtime/       orchestrator, fast_loop, slow_loop, shadow, demo
│  └─ cli.py
├─ apps/web/                     # Next.js dashboard
├─ infra/                        # Dockerfiles, compose, SQL init, prometheus
├─ tests/                        # unit, property, integration, e2e, failure, adversarial
├─ docs/                         # this file + the full doc set
├─ data/fixtures/                # committed deterministic datasets
└─ scripts/                      # dev helpers
```

*Deviation from the suggested layout (§37): a single installable package `tia` replaces
`/services` + many top-level dirs. Reason: identical module boundaries, one dependency graph,
no cross-package import gymnastics, and it keeps `pytest`/`mypy` honest. The suggested
directories map 1:1 onto `tia.*` subpackages.*

---

## 15. Data model

Core tables (see [DATABASE.md](DATABASE.md) for columns, types and indexes):

```
users                assets              candles(hypertable)   ticks(hypertable)
news                 macro_events        market_snapshots
strategies           strategy_versions   models                prompts
signals              risk_decisions      order_intents         orders
fills                positions           portfolio_snapshots
experiments          backtests           backtest_trades
decisions            decision_lineage    events(append-only)
system_errors        audit_logs          llm_calls             data_quality_reports
```

Key relationships & indexes:

* `candles(asset_id, timeframe, open_time)` unique + BRIN/hypertable partition on `open_time`.
* `signals(asset_id, created_at)`, `signals(strategy_version_id)`, `signals(expires_at)`.
* `orders(client_order_id)` **unique** — the idempotency anchor.
* `fills(order_id, sequence)` unique.
* `decisions(correlation_id)` — joins the whole journey.
* `events(correlation_id, sequence)`, `events(idempotency_key)` unique.
* `audit_logs(actor, action, occurred_at)` append-only, no UPDATE/DELETE grant.

---

## 16. Data lineage

```
decision_id
  ├─ market_snapshot_id ─→ candles / ticks / news / macro refs (by id + hash)
  ├─ feature_set_hash + feature_version
  ├─ data_quality_report_id
  ├─ strategy_version_id
  ├─ llm_call_id ─→ model_id + prompt_version + assessment_id
  ├─ risk_decision_id ─→ every check with observed vs limit
  ├─ order_intent_id ─→ order_id ─→ fill_ids
  └─ position_id ─→ realized / unrealized P&L
```

Rendered as the **Decision Journey** view in the dashboard.

---

## 17. Security model

* No financial credentials anywhere in the system; none are required to run it.
* Secrets only via environment / secret manager. Never in Git, prompts, logs, or the frontend.
  A `SecretGuard` scans every outbound LLM payload and every log record against secret
  patterns and refuses/redacts.
* Prompts receive an explicit **allowlist** of fields — no object is serialized wholesale.
* API: JWT bearer auth, per-route scopes, rate limiting, strict request validation,
  no stack traces to clients, security headers, CORS allowlist.
* Webhooks: HMAC-SHA256 over the raw body, nonce + replay window, IP allowlist, size cap,
  disabled by default.
* Audit log is append-only and records actor, action, target, before/after hash.
* Least privilege: the app DB role has no DDL rights at runtime; migrations run separately.

---

## 18. Environments

`development` · `testing` · `demo` · `paper` · `shadow` · `backtest` — never mixed. Each has
its own config file under `config/`, its own DB URL, and its own feature flags. Switching
environment is explicit (`TIA_ENV`), and the API reports the active environment on `/health`
so a screenshot can never be mistaken for another environment.

**Demo ≠ paper ≠ real.** Demo uses synthetic data and a stub LLM. Paper uses real market data
where available but simulated fills. Neither is the real market: no queue position, no market
impact from our own orders, no venue-specific rejects, no funding/borrow.

---

## 19. Testing strategy

| Layer | What it proves |
|---|---|
| Unit | Indicators vs hand-computed fixtures; risk limits; sizing; state machine |
| Property (Hypothesis) | State-machine invariants; idempotency under duplication/reordering; risk never grows size |
| Data quality | Each check fires on crafted bad data |
| LLM schema | Malformed/adversarial model outputs are rejected, never executed |
| Reconciliation | Injected divergence → detected → safe mode |
| Backtest validation | Look-ahead detector; determinism (same seed ⇒ identical results) |
| Integration | Bus + engines + persistence wired together |
| E2E | Event → decision → risk → paper fill → position → P&L → API → lineage |
| Failure injection | Every row of §11 |
| Adversarial | Fake/contradictory news, absurd prices, inconsistent timestamps, corrupt feeds ⇒ `NO_TRADE` |
| Load | Sustained event throughput with latency percentiles per stage |

---

## 20. Observability

Structured JSON logs with `correlation_id` on every record. Prometheus metrics:
`tia_events_total`, `tia_stage_latency_seconds{stage}`, `tia_signals_total{decision}`,
`tia_risk_rejections_total{reason}`, `tia_orders_total{state}`, `tia_fills_total`,
`tia_paper_equity`, `tia_paper_drawdown`, `tia_llm_calls_total`, `tia_llm_tokens_total`,
`tia_llm_cost_usd_total`, `tia_data_quality_score`, `tia_errors_total{component}`.
Latency is measured **per stage** (data, feature, strategy, LLM, risk, execution, DB) so no
one can call this system "HFT" — the numbers say what it is.

---

## 21. Scalability path

1 asset → 100+ without redesign: per-symbol handler state is isolated and keyed; the bus
partitions by symbol; feature computation is incremental where possible; providers are
multiplexed. The step change beyond ~100 symbols is Redis Streams → Kafka/Redpanda plus
horizontal fast-loop workers — an implementation swap behind `EventBus`, not a rewrite.

---

## 22. Self-improvement guardrails

The system may *propose* parameter changes. It may never apply them. The path is:
`proposal → backtest → out-of-sample validation → shadow test → human approval → versioned
config change`. Risk limits are marked immutable-at-runtime; an attempt to mutate them raises.

---

## 23. Roadmap and Definition of Done

Phases 0–14 as tracked in the task list. **Done** means all of:

backend starts · frontend starts · DB migrates · ingestion works with the bundled test source ·
data-quality validation works · events flow · signals generate · Claude integration works when
configured and degrades safely when not · structured output is validated · risk engine works ·
paper execution works · order states work · reconciliation works · backtesting works ·
experiments reproduce bit-for-bit from a seed · dashboard works · logs and metrics work ·
tests pass · failure scenarios tested · docs exist · clean-environment setup works.

### MVP 1 (the first vertical slice, end to end)

Synthetic BTC-USD 1m feed → data quality → features → regime → trend strategy →
fusion (stub LLM) → risk engine → paper execution → position + P&L → REST API → dashboard
overview + decision journey, with a backtest of the same strategy against all baselines and a
reproducible experiment record. No external credentials. `docker compose up`.
