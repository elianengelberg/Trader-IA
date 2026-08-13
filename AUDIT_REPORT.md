# Audit Report

**Date:** 2026-08-13 · **Branch:** `claude/algo-trading-simulation-platform-ngf7xo`
**Baseline commit at audit start:** `4e47c3b`

This is the entry audit: what the repository actually contained, verified by running
things rather than by reading them. It is updated at the end of the work with what was
fixed and what remains. Nothing in this document is a claim about profitability.

---

## 1. Environment (measured, not assumed)

Probed on the build host. `MISSING` and `DOWN` are stated plainly — a demo that only
works on one machine is not a demo.

| Tool | Version | State |
|---|---|---|
| Python | 3.11.15 | OK |
| Node | 22.22.2 | OK |
| npm / pnpm | 10.9.7 / 10.33.0 | OK |
| PostgreSQL | 16.13 | server installed, **was down** → started for testing |
| Redis | 7.0.15 | server installed, **was down** → started for testing |
| Docker CLI | 29.3.1 | present |
| Docker **daemon** | — | **NOT RUNNING**, no `/var/run/docker.sock` |
| make, git, curl | — | OK |
| npm registry / PyPI | — | reachable (HTTP 200) |

**Consequence, stated up front:** `docker compose up` **cannot be executed in this
sandbox**. A compose file is provided and written carefully, but it is labelled
`REQUIRES VALIDATION` — it has never been run here, and per the project's own §3 research
rule I will not claim otherwise. Every other path in this document was executed.

**Design decision that follows:** the default demo path uses **SQLite + an in-process
event bus + a static frontend served by the API**, so it needs no daemon, no external
service and no credential. Postgres and Redis are supported and were tested, but they are
opt-in rather than required.

---

## 2. Component matrix (entry state)

| Component | State | Test coverage at audit | Problems found | Priority | Action |
|---|---|---|---|---|---|
| `core` (clock, config, ids, errors, logging, rng) | **WORKING** | unit + property | none | — | keep |
| `domain` (enums, instruments, market, orders, portfolio, risk, signals) | **WORKING** | unit | none | — | keep |
| `events` (envelope, bus, idempotency, registry, payloads) | **WORKING** | unit | payload set does not yet cover AI/system events | P2 | extend |
| `data` providers (synthetic, CSV replay) | **WORKING** | unit | none | — | keep |
| `data` provider (Binance public) | **PARTIALLY_WORKING** | unit (offline shape only) | host blocked by egress proxy; never executed against the live API | P3 | keep opt-in, keep the `REQUIRES VALIDATION` label |
| `data/quality` | **WORKING** | unit | none | — | keep |
| `quant` (indicators, features, statistics) | **WORKING** | unit + property | indicators recompute the whole buffer per bar — the main cost of a backtest | P3 | documented; not optimised (would change numeric results) |
| `regime` classifier | **WORKING** | unit | classification quality never *measured*, only exercised | P2 | add a labelled-scenario accuracy test |
| `strategy` (library, fusion, engine) | **WORKING** | unit + property | none | — | keep |
| `risk` engine + sizing | **WORKING** | unit | none | — | keep |
| `execution` (state machine, paper, reconciliation) | **WORKING** | unit + property | none | — | keep |
| `backtest` (engine, baselines, walk-forward, experiment) | **WORKING** | unit + property | no parameter-sensitivity sweep | P3 | documented as pending |
| `llm/` | **MISSING** | none | empty directory | **P0** | build |
| `agents/` | **MISSING** | none | empty directory | P2 | build minimal, honest set |
| `persistence/` | **MISSING** | none | empty directory | **P0** | build |
| `runtime/` | **MISSING** | none | empty directory | **P0** | build |
| `api/` | **MISSING** | none | empty directory (only `routers/`) | **P0** | build |
| `observability/` | **MISSING** | none | empty directory | P1 | build |
| `memory/` | **MISSING** | none | empty directory | P3 | defer, remove if unused |
| Frontend | **MISSING** | none | does not exist | **P0** | build |
| Database | **MISSING** | none | no schema, no migrations | **P0** | build |
| Authentication | **MISSING** | none | none | P1 | build |
| Docker / compose | **MISSING** | none | none | P1 | write; cannot verify here |
| `make verify` / `diagnose.sh` | **MISSING** | none | none | P1 | build |
| CI | **MISSING** | none | none | P2 | build |

### Defects found by inspection, before any change

| # | Defect | Severity | Evidence |
|---|---|---|---|
| D1 | `pyproject.toml` declares `[project.scripts] tia = "tia.cli:app"` but `tia/cli.py` **does not exist** — installing the package produces a console script that raises `ModuleNotFoundError` | **HIGH** | `ls packages/tia/src/tia/cli.py` → no such file |
| D2 | Seven package directories are empty (`llm`, `agents`, `memory`, `observability`, `persistence`, `runtime`, `api/routers`) — the repository's structure promises more than it contains | MEDIUM | `find` on the package tree |
| D3 | `docs/ARCHITECTURE.md` §11 referenced `tests/failure/` for every failure-mode row; the directory is empty | MEDIUM | already annotated as *not yet written* during Phase 7 |
| D4 | No runnable entry point of any kind: the package cannot be started, only imported | **HIGH** | no `__main__`, no server, no CLI |

Two further defects had already been found and fixed earlier in the build and are
recorded here for completeness: `BinancePublicProvider` called `datetime.now()` directly,
contradicting the no-wall-clock rule stated in `core/clock.py`; and
`tests/unit/test_scope_boundary.py` was referenced by two docstrings without existing.

### Test baseline at audit start

```
437 passed in 43.99s      ruff: All checks passed
```

Coverage is real but narrow in one specific way: **everything tested so far is a library
call.** Nothing had ever been started as a process, connected to a database, served over
HTTP, or driven from a browser. That is the gap this round of work closes.

---

*Sections 3 onward — execution results, defects found while testing, and the final
status — are appended as the work proceeds.*
