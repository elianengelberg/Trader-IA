"""Wiring the activation gate's checks to things that are actually true.

:mod:`tia.live.gate` defines *what* must hold before real money is at risk and refuses to
arm unless every check reports pass. This module is where each check gets connected to a
real signal — a database ping, a reconciliation counter, a fee schedule's provenance.

The wiring is the part that is easy to fake and therefore worth reading carefully. A probe
that returns ``passing()`` unconditionally would satisfy the gate while checking nothing,
and it would look exactly like a probe that works. So every probe here derives its verdict
from a value it did not choose, and the ones that cannot yet be derived from anything —
because this environment has no egress to the venue — report **failure with a remedy**,
never a pass and never silence.

The expected result of running this today is that the gate refuses. That is the correct
output for a system whose Binance adapter has never made a request.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tia.live.gate import CheckName, GateCheck, failing, passing

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tia.api.state import AppState

#: Where ``make verify`` records a passing run, and where
#: ``scripts/validate_binance.py --json-out`` records what it confirmed against the venue.
#: Files rather than in-process state on purpose: both are produced by a separate process,
#: and a check that the API could satisfy from its own memory is a check the API could
#: satisfy by being wrong.
VERIFY_MARKER = Path("data/runtime/verify_passed.json")
BINANCE_FACTS = Path("data/runtime/binance_validation.json")

#: The placeholder in ``config.py``. A deployment still carrying it has no session
#: security worth the name.
_DEFAULT_JWT_SECRET = "change-me-in-any-real-deployment"  # noqa: S105 - the value to reject


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_probes(state: AppState, *, database_ok: bool) -> dict[CheckName, GateCheck]:
    """Report on every activation check from the system's current state.

    ``database_ok`` is passed in rather than pinged here because the ping is async and
    this is not — and because a probe set assembled from one awaited value and thirteen
    synchronous ones would invite someone to make the whole thing async and then forget
    which parts can block the trading loop.
    """
    return {
        CheckName.TESTS_PASS: _tests(),
        CheckName.MARKET_DATA_HEALTHY: _market_data(state),
        CheckName.VENUE_CONNECTED: _venue(state),
        CheckName.DATABASE_HEALTHY: _database(database_ok),
        CheckName.EXECUTION_HEALTHY: _execution(state),
        CheckName.RISK_ENGINE_HEALTHY: _risk(state),
        CheckName.RECONCILIATION_HEALTHY: _reconciliation(state),
        CheckName.SECURITY_REVIEW: _security(state),
        CheckName.FEES_VERIFIED_AT_SOURCE: _fees(),
        CheckName.CAPITAL_POLICY_SET: _capital(state),
        CheckName.KILL_SWITCH_CLEAR: _kill_switch(state),
        CheckName.CREDENTIALS_SCOPED: _credentials(),
        CheckName.EDGE_EVIDENCE: _edge(state),
        CheckName.PAPER_TRACK_RECORD: _track_record(state),
    }


def _tests() -> GateCheck:
    marker = _read_json(VERIFY_MARKER)
    if marker is None:
        return failing(
            CheckName.TESTS_PASS,
            "no record of a passing verification run",
            f"run `make verify`, which writes {VERIFY_MARKER}",
        )
    if not marker.get("passed"):
        return failing(
            CheckName.TESTS_PASS,
            f"the last verification run failed ({marker.get('failed', '?')} areas)",
            "fix what failed and run `make verify` again",
        )
    return passing(
        CheckName.TESTS_PASS,
        f"verified at {marker.get('at', 'unknown time')} on commit "
        f"{str(marker.get('commit', ''))[:8] or 'unknown'}",
    )


def _market_data(state: AppState) -> GateCheck:
    runtime = state.runtime
    if runtime is None or not runtime.is_running:
        return failing(
            CheckName.MARKET_DATA_HEALTHY,
            "no run is active, so there is no feed to judge",
            "start a run and let it warm up before arming",
        )
    counters = runtime.counters
    if counters.bars <= runtime.config.warmup_bars:
        return failing(
            CheckName.MARKET_DATA_HEALTHY,
            f"only {counters.bars} bars seen; still warming up",
            f"wait for at least {runtime.config.warmup_bars} bars",
        )
    skipped_ratio = counters.quality_skipped / max(1, counters.bars)
    if skipped_ratio > 0.05:
        return failing(
            CheckName.MARKET_DATA_HEALTHY,
            f"{skipped_ratio:.1%} of bars were rejected by the data quality gate",
            "investigate the feed; trading on a gapped feed is trading on a market that "
            "no longer exists",
        )
    return passing(
        CheckName.MARKET_DATA_HEALTHY,
        f"{counters.bars} bars, {counters.quality_skipped} rejected on quality",
    )


def _venue(state: AppState) -> GateCheck:
    """Whether the venue has ever answered.

    Reported from ``scripts/validate_binance.py`` rather than by pinging here, because a
    ping from the API process proves the API process can reach it — and the check that
    matters is whether the *adapter's* documented assumptions held, which only that script
    tests.
    """
    if not state.settings.live.enabled:
        return failing(
            CheckName.VENUE_CONNECTED,
            "the live path is disabled in configuration",
            "set TIA_LIVE__ENABLED=true once everything else here passes",
        )
    facts = _read_json(BINANCE_FACTS)
    if facts is None:
        return failing(
            CheckName.VENUE_CONNECTED,
            "the Binance adapter has never successfully reached the venue",
            "run `python scripts/validate_binance.py --account --json-out "
            f"{BINANCE_FACTS}` from a machine with internet access",
        )
    skew = facts.get("clock_skew_ms")
    if skew is not None and skew > 1000:
        return failing(
            CheckName.VENUE_CONNECTED,
            f"{skew} ms of clock skew against the venue",
            "fix NTP; signed requests are rejected outside recvWindow and the error does "
            "not mention the clock",
        )
    return passing(
        CheckName.VENUE_CONNECTED,
        f"validated; {skew} ms clock skew, spread {facts.get('observed_spread_bps')} bps",
    )


def _database(database_ok: bool) -> GateCheck:
    if not database_ok:
        return failing(
            CheckName.DATABASE_HEALTHY,
            "the database did not answer its last ping",
            "without the order journal, a restart cannot tell a sent order from an "
            "unsent one",
        )
    return passing(CheckName.DATABASE_HEALTHY, "responding")


def _execution(state: AppState) -> GateCheck:
    runtime = state.runtime
    if runtime is None:
        return failing(
            CheckName.EXECUTION_HEALTHY, "no execution provider is running", "start a run"
        )
    counters = runtime.counters
    if counters.intents and counters.orders_rejected / counters.intents > 0.1:
        return failing(
            CheckName.EXECUTION_HEALTHY,
            f"{counters.orders_rejected} of {counters.intents} orders were rejected",
            "a degraded execution path can open a position it cannot close",
        )
    return passing(
        CheckName.EXECUTION_HEALTHY,
        f"{counters.intents} orders submitted, {counters.orders_rejected} rejected",
    )


def _risk(state: AppState) -> GateCheck:
    runtime = state.runtime
    if runtime is None:
        return failing(CheckName.RISK_ENGINE_HEALTHY, "no risk engine is running", "start a run")
    if runtime.risk.state.is_halted:
        return failing(
            CheckName.RISK_ENGINE_HEALTHY,
            f"the risk engine is halted: {runtime.risk.state.kill_switch_reason}",
            "resolve the cause and release the halt deliberately",
        )
    if not runtime.counters.approved and not runtime.counters.risk_rejected:
        return failing(
            CheckName.RISK_ENGINE_HEALTHY,
            "the risk engine has evaluated nothing",
            "if it is not evaluating, nothing is stopping a bad trade",
        )
    return passing(
        CheckName.RISK_ENGINE_HEALTHY,
        f"{runtime.counters.approved} approved, {runtime.counters.risk_rejected} vetoed",
    )


def _reconciliation(state: AppState) -> GateCheck:
    runtime = state.runtime
    if runtime is None or not runtime.counters.reconciliations:
        return failing(
            CheckName.RECONCILIATION_HEALTHY,
            "reconciliation has never run",
            "let a run proceed far enough to reconcile at least once",
        )
    if runtime.counters.reconciliation_breaks:
        return failing(
            CheckName.RECONCILIATION_HEALTHY,
            f"{runtime.counters.reconciliation_breaks} divergences between our books and "
            "the provider's",
            "one of the two is wrong about what we own, and sizing runs off the wrong one",
        )
    return passing(
        CheckName.RECONCILIATION_HEALTHY,
        f"{runtime.counters.reconciliations} clean reconciliations",
    )


def _security(state: AppState) -> GateCheck:
    problems: list[str] = []
    if state.settings.security.jwt_secret.get_secret_value() == _DEFAULT_JWT_SECRET:
        problems.append("the JWT secret is still the placeholder from config.py")
    if state.settings.live.enabled and not state.settings.live.has_credentials:
        problems.append("live is enabled but no venue credentials are configured")
    if problems:
        return failing(
            CheckName.SECURITY_REVIEW,
            "; ".join(problems),
            "a leaked or absent secret is a total loss, not a degraded service",
        )
    return passing(
        CheckName.SECURITY_REVIEW,
        "session secret set; credentials present and never exposed through the API",
    )


def _fees() -> GateCheck:
    facts = _read_json(BINANCE_FACTS) or {}
    taker = facts.get("taker_bps")
    if taker is None:
        return failing(
            CheckName.FEES_VERIFIED_AT_SOURCE,
            "the fee schedule is a configured default, not a value read from the account",
            "run `python scripts/validate_binance.py --account`; a fee tier guessed 5 bps "
            "low turns a losing strategy into a winning-looking one",
        )
    return passing(
        CheckName.FEES_VERIFIED_AT_SOURCE,
        f"read from the account: taker {taker} bps, round trip {float(taker) * 2} bps",
    )


def _capital(state: AppState) -> GateCheck:
    ceiling = state.settings.live.max_live_capital
    if ceiling <= 0:
        return failing(
            CheckName.CAPITAL_POLICY_SET,
            "max_live_capital is zero",
            "set TIA_LIVE__MAX_LIVE_CAPITAL deliberately; without a ceiling the amount at "
            "risk is whatever happens to be in the account",
        )
    return passing(CheckName.CAPITAL_POLICY_SET, f"ceiling {ceiling:,.2f}")


def _kill_switch(state: AppState) -> GateCheck:
    runtime = state.runtime
    if runtime is not None and runtime.risk.state.is_halted:
        return failing(
            CheckName.KILL_SWITCH_CLEAR,
            f"engaged: {runtime.risk.state.kill_switch_reason}",
            "arming now would discard the reason something halted it",
        )
    return passing(CheckName.KILL_SWITCH_CLEAR, "clear")


def _credentials() -> GateCheck:
    facts = _read_json(BINANCE_FACTS) or {}
    permissions = facts.get("permissions")
    if not permissions:
        return failing(
            CheckName.CREDENTIALS_SCOPED,
            "the key's permissions have never been read from the venue",
            "run `python scripts/validate_binance.py --account`; until then the system "
            "treats the key as potentially able to withdraw and refuses to trade",
        )
    if not permissions.get("acceptable"):
        return failing(
            CheckName.CREDENTIALS_SCOPED,
            permissions.get("explanation", "the key's permissions are not acceptable"),
            "disable withdrawal, transfer, futures and margin on the key, then re-validate",
        )
    return passing(
        CheckName.CREDENTIALS_SCOPED,
        "can trade, cannot move funds"
        + ("; IP-restricted" if permissions.get("ip_restricted") else "; NOT IP-restricted"),
    )


def _edge(state: AppState) -> GateCheck:
    runtime = state.runtime
    if runtime is None:
        return failing(CheckName.EDGE_EVIDENCE, "no run is active", "run paper trading first")
    economics = runtime.economics_snapshot()["expected_value"]
    coverage: dict[str, int] = economics["coverage"]
    minimum = economics["min_samples"]
    filled = {bucket: count for bucket, count in coverage.items() if count >= minimum}
    if not filled:
        best = max(coverage.values(), default=0)
        return failing(
            CheckName.EDGE_EVIDENCE,
            f"no bucket has reached {minimum} closed trades (best is {best})",
            "keep paper trading; going live with no measured edge is not trading",
        )
    return passing(
        CheckName.EDGE_EVIDENCE,
        f"{len(filled)} of {len(coverage)} buckets have a usable sample",
    )


def _track_record(state: AppState) -> GateCheck:
    runtime = state.runtime
    required = state.settings.live.min_paper_trades
    if runtime is None:
        return failing(
            CheckName.PAPER_TRACK_RECORD, "no run is active", "run paper trading first"
        )
    closed = len(runtime.closed_trades)
    if closed < required:
        return failing(
            CheckName.PAPER_TRACK_RECORD,
            f"{closed} closed paper round trips; {required} required",
            "live is not the place to discover the first reconnect",
        )
    return passing(CheckName.PAPER_TRACK_RECORD, f"{closed} closed paper round trips")


def validation_facts() -> dict[str, Any] | None:
    """What ``scripts/validate_binance.py`` last confirmed, or ``None`` if it never ran.

    Shown on the live page so "why is the gate refusing?" has an answer that names the
    command to run rather than a boolean.
    """
    return _read_json(BINANCE_FACTS)


__all__ = ["BINANCE_FACTS", "VERIFY_MARKER", "build_probes", "validation_facts"]
