# Live runbook

The operational procedures, in the order a deployment actually meets them. Every command
is real and none of them contains a secret. Companion documents: `LIVE_TRADING.md` (the
concepts), `SECURITY.md` (the rules), `BINANCE_INTEGRATION.md` (the unverified surface).

---

## 1. Setup

```bash
git clone <repo> && cd Trader-IA
make install          # venv, dependencies, dashboard build
make diagnose         # states what is present and what is missing
```

## 2. Configuration

```bash
cp .env.example .env
```

Then edit `.env`. The minimum for a live-capable deployment:

| Variable | What it is |
|---|---|
| `TIA_SECURITY__JWT_SECRET` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The gate refuses to arm on the placeholder. |
| `TIA_LIVE__MAX_LIVE_CAPITAL` | The ceiling. Start with an amount you would be entirely fine losing. |
| `TIA_LIVE__BINANCE_API_KEY` / `..._SECRET` | From Binance API Management: Reading + Spot Trading ONLY, withdrawals/transfers/futures/margin disabled, IP-restricted. Never in chat, never in the browser, never as CLI arguments. |
| `TIA_LIVE__USE_TESTNET` | Keep `true` until §8 is done. |

## 3. Migrations

```bash
make migrate          # alembic upgrade head; idempotent; adopts pre-Alembic databases
```

A database from an older build upgrades in place (tested: v1 → v2 preserves rows). The
runtime refuses a database *newer* than itself rather than misreading it.

## 4. Binance validation — from a machine with venue access

```bash
python scripts/validate_binance.py --account \
  --json-out data/runtime/binance_validation.json
```

Writes a fingerprinted, versioned record the gate demands. It expires after 24 hours
(fee tiers and key permissions are editable at any time), so re-run it the day you arm.
A failed validation refuses to write the record at all — a record of failure must never
satisfy a gate.

## 5. Paper trading

```bash
make demo             # http://127.0.0.1:8000 — start runs from the dashboard
```

Paper is where the edge evidence is produced: every closed round trip persists to
`edge_outcomes` and survives restarts. The EV engine **observes** here (prices every
decision, counts what it would refuse) and **enforces** in live.

## 6. Paper requirements

The gate requires, from the persisted record (not from process memory):

- ≥ `TIA_LIVE__MIN_PAPER_TRADES` closed round trips (default 30),
- spanning ≥ `TIA_LIVE__MIN_PAPER_DAYS` days (default 7),
- at least one edge bucket at the 30-sample floor,
- a passing endurance run: `make endurance` (24 simulated hours; `BARS=10080` for 7 days).

## 7. Readiness gate

```bash
make verify           # the whole suite; writes the record the gate's tests_pass check reads
make readiness        # scripts/validate_live_environment.py → data/runtime/live_readiness.json
```

`readiness` separates **VALIDATED** from **EXTERNAL_REQUIRED** and never blurs them.
The web gate (`/api/live/gate`, or the Live Trading page) evaluates all 27 checks with
remedies. UNKNOWN = FAILED, everywhere.

## 8. Testnet validation

```bash
python scripts/validate_binance.py --account --order --testnet
```

Places, duplicates and cancels one resting order on the **testnet** (`--order` refuses to
run without `--testnet`; not overridable). The duplicate step is the one that matters: it
proves the venue rejects a repeated `clientOrderId`. Run the app against the testnet
(`TIA_LIVE__USE_TESTNET=true`) long enough to see a disconnect and a restart.

## 9. Activation

On the **Live Trading** page: every check green → type the confirmation phrase exactly →
Arm. What happens, in order: gate evaluates → token minted → attempt persisted → live
runtime constructed and **started** → LIVE reported only if the state machine reached
RUNNING. A token whose runtime failed to start is recorded as exactly that and discarded.

Tokens expire (1h default, 6h max) and are re-validated **per order**, bound to a
fingerprint of the risk limits — change a limit and every subsequent order is refused
until re-armed.

## 10. Monitoring

- **Live Trading page** — state machine, capital, skew, latency, activation history.
- `GET /api/live` — the state machine's word; there is no code path that reports RUNNING
  while the loop is not.
- `GET /api/metrics` — Prometheus; `GET /api/stream` — SSE.
- Reconciliation runs on a schedule; every run is persisted to `reconciliations`.

## 11. Pause

`POST /api/live/stop` stops the session (STOPPING → STOPPED). Pausing risk-profile
changes: `POST /api/risk/profile` refuses while a live session runs — stop first, change
(audited, confirmed), re-arm. Re-arming re-runs the whole gate against the new
configuration fingerprint: that is the PAUSE + CONFIRM + REVALIDATE path.

## 12. Kill switch

```
POST /api/live/kill-switch   {"reason": "..."}     # operator only
```

Stops entries, cancels resting orders, reconciles, lands in **SAFE_MODE** — which has no
automatic exit and no path back to RUNNING. It does **not** close positions. No model can
reach this endpoint or override it; the runtime method requires a named human actor.

## 13. Emergency procedures

```
POST /api/live/flatten       {"reason": "..."}     # operator only
```

The full sequence: stop new orders → cancel resting → read real positions from the venue
→ submit reducing orders → verify fills → reconcile → persist the incident. Use it when
you want *out of the market*, not merely out of the software — those are different
emergencies and the two endpoints keep them separate.

**Unknown order state** (submission timeout): the runtime halts entries and resolves
against the venue by `clientOrderId` before anything may submit again. If you see
`HALT_NEW_ORDERS` with an unknown-order reason: do not restart blindly — check the
reconciliations table, confirm the venue's view, then `resume` with your name on it.

## 14. Reconciliation

Automatic on a cycle cadence; the venue wins every disagreement. Balance drift goes
through the capital ledger's classifier: a clean increase is a **deposit** (never
profit), a clean decrease a **withdrawal** (never a loss), and anything above 10% of the
ceiling with no fill behind it is **UNEXPLAINED** → entries halt until a named operator
clears it.

## 15. Restart recovery

Nothing special to do — that is the point. On start the system reloads persisted edge
evidence, rebuilds its track record, and deduplicates orders by deterministic
`clientOrderId`. Proven by `tests/integration/test_restart_recovery.py`, which the gate's
`restart_recovery` check requires to have passed.

## 16. Shutdown

```bash
POST /api/live/stop           # graceful: STOPPING → STOPPED
# then stop the server process (Ctrl-C / systemd stop)
```

The application holds no funds, so shutdown has no financial step: your money is at
Binance, where it always was.
