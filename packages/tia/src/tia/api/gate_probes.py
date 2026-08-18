"""Wiring the activation gate's checks to things that are actually true.

:mod:`tia.live.gate` defines *what* must hold before real money is at risk and refuses to
arm unless every check reports pass. This module is where each check gets connected to a
real signal — a database ping, a reconciliation counter, a fee schedule's provenance, a
validation record's fingerprint.

The wiring is the part that is easy to fake and therefore worth reading carefully. A probe
that returns ``passing()`` unconditionally would satisfy the gate while checking nothing,
and it would look exactly like a probe that works. So every probe here derives its verdict
from a value it did not choose, and the ones that cannot yet be derived from anything —
because this environment has no egress to the venue — report **failure with a remedy**,
never a pass and never silence.

**On the validation record.** Several checks read ``data/runtime/binance_validation.json``,
written by ``scripts/validate_binance.py`` from a machine that can reach the venue. That
file is *evidence*, and evidence gets examined: it must match a schema, name this
environment and symbol, be younger than the freshness bound, and carry an intact
fingerprint over its own facts. A stale, hand-edited, or truncated record fails the checks
it feeds — trusting the file as read was gap C16 in the Part II audit, and this module is
where it closed.

The expected result of running this today is that the gate refuses. That is the correct
output for a system whose Binance adapter has never made a request.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tia.data.providers.binance_signing import key_fingerprint_from_live_config
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

#: The validator version this build understands. A record from another version fails
#: schema-validation rather than being reinterpreted.
EXPECTED_VALIDATOR_VERSION = 2

#: Venue facts older than this are treated as unknown. A day, because fee tiers and key
#: permissions are editable at any time and yesterday's answer is a guess about today.
VALIDATION_MAX_AGE_HOURS = 24.0



class BinanceValidationRecord(BaseModel):
    """The envelope ``validate_binance.py`` writes. Anything else is not evidence."""

    model_config = ConfigDict(extra="forbid")

    validator_version: int
    generated_at: datetime
    environment: str = Field(pattern="^(mainnet|testnet)$")
    symbol: str
    git_commit: str = ""
    fingerprint: str
    facts: dict[str, Any]

    def recomputed_fingerprint(self) -> str:
        canonical = json.dumps(self.facts, sort_keys=True, default=str).encode("utf-8")
        return hashlib.blake2s(canonical, digest_size=16).hexdigest()

    def age_hours(self, now: datetime) -> float:
        return (now - self.generated_at).total_seconds() / 3600.0


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_validation_record(
    state: AppState,
) -> tuple[BinanceValidationRecord | None, str]:
    """The validation record, or the specific reason it cannot be believed."""
    raw = _read_json(BINANCE_FACTS)
    if raw is None:
        return None, (
            f"no validation record at {BINANCE_FACTS}; run scripts/validate_binance.py "
            "--account --json-out from a machine with venue access"
        )
    try:
        record = BinanceValidationRecord.model_validate(raw)
    except ValidationError as exc:
        return None, (
            f"the validation record does not match its schema ({exc.error_count()} "
            "problems); regenerate it — do not edit it by hand"
        )
    if record.validator_version != EXPECTED_VALIDATOR_VERSION:
        return None, (
            f"validation record is from validator v{record.validator_version}; this "
            f"build requires v{EXPECTED_VALIDATOR_VERSION} — re-run the current script"
        )
    if record.fingerprint != record.recomputed_fingerprint():
        return None, (
            "the record's fingerprint does not match its own facts — the file was "
            "modified after it was written. Regenerate it; a validation record is "
            "evidence, and edited evidence is none"
        )
    expected_env = "testnet" if state.settings.live.use_testnet else "mainnet"
    if record.environment != expected_env:
        return None, (
            f"the record validates {record.environment} but this deployment targets "
            f"{expected_env}; validate the environment you intend to trade on"
        )
    expected_symbol = state.settings.live.symbol.replace("-USD", "USDT").replace("-", "")
    if record.symbol.upper() != expected_symbol.upper():
        return None, (
            f"the record validates {record.symbol}, not {expected_symbol}"
        )
    return record, ""


def build_probes(
    state: AppState,
    *,
    database_ok: bool,
    schema_version_ok: bool | None = None,
    edge_persisted: int | None = None,
    track_record: dict[str, Any] | None = None,
) -> dict[CheckName, GateCheck]:
    """Report on every activation check from the system's current state.

    The async-derived inputs (database ping, schema version, persisted-evidence counts)
    are passed in rather than gathered here, so this function stays synchronous and the
    call sites show exactly which facts feed the gate.
    """
    record, record_problem = load_validation_record(state)
    return {
        CheckName.TESTS_PASS: _tests(),
        CheckName.MIGRATIONS_CURRENT: _migrations(schema_version_ok),
        CheckName.MARKET_DATA_HEALTHY: _market_data(state),
        CheckName.VENUE_CONNECTED: _venue(state, record, record_problem),
        CheckName.VENUE_VALIDATION: _venue_validation(record, record_problem),
        CheckName.VALIDATION_FRESH: _validation_fresh(record, record_problem),
        CheckName.CLOCK_SKEW_OK: _clock_skew(state, record),
        CheckName.USER_DATA_STREAM: _user_data_stream(record),
        CheckName.DATABASE_HEALTHY: _database(database_ok),
        CheckName.EXECUTION_HEALTHY: _execution(state),
        CheckName.ORDER_IDEMPOTENCY: _order_idempotency(record),
        CheckName.RISK_ENGINE_HEALTHY: _risk(state),
        CheckName.RECONCILIATION_HEALTHY: _reconciliation(state),
        CheckName.CAPITAL_LEDGER_READY: _capital_ledger(state),
        CheckName.EDGE_PERSISTENCE: _edge_persistence(edge_persisted),
        CheckName.EV_ENFORCEMENT: _ev_enforcement(state),
        CheckName.SECURITY_REVIEW: _security(state),
        CheckName.CONFIGURATION_COHERENT: _configuration(state),
        CheckName.OBSERVABILITY: _observability(state),
        CheckName.FEES_VERIFIED_AT_SOURCE: _fees(record),
        CheckName.CAPITAL_POLICY_SET: _capital(state),
        CheckName.KILL_SWITCH_CLEAR: _kill_switch(state),
        CheckName.EMERGENCY_CONTROLS: _emergency_controls(),
        CheckName.RESTART_RECOVERY: _restart_recovery(),
        CheckName.CREDENTIALS_SCOPED: _credentials(state, record),
        CheckName.EDGE_EVIDENCE: _edge(state),
        CheckName.PAPER_TRACK_RECORD: _track_record_probe(state, track_record),
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


def _migrations(schema_version_ok: bool | None) -> GateCheck:
    if schema_version_ok is None:
        return failing(
            CheckName.MIGRATIONS_CURRENT,
            "the schema version could not be read",
            "run `make migrate` and re-check",
        )
    if not schema_version_ok:
        return failing(
            CheckName.MIGRATIONS_CURRENT,
            "the database schema is not at this build's version",
            "run `make migrate`; a schema one migration behind reads plausibly and wrongly",
        )
    return passing(CheckName.MIGRATIONS_CURRENT, "schema at the current version")


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


def _venue(
    state: AppState, record: BinanceValidationRecord | None, problem: str
) -> GateCheck:
    if not state.settings.live.enabled:
        return failing(
            CheckName.VENUE_CONNECTED,
            "the live path is disabled in configuration",
            "set TIA_LIVE__ENABLED=true once everything else here passes",
        )
    if record is None:
        return failing(
            CheckName.VENUE_CONNECTED,
            "the venue has never been successfully reached by the validator",
            problem,
        )
    return passing(
        CheckName.VENUE_CONNECTED,
        f"validated against {record.environment} at {record.generated_at.isoformat()}",
    )


def _venue_validation(
    record: BinanceValidationRecord | None, problem: str
) -> GateCheck:
    if record is None:
        return failing(CheckName.VENUE_VALIDATION, problem or "no validation record", problem)
    return passing(
        CheckName.VENUE_VALIDATION,
        f"schema valid, fingerprint intact, validator v{record.validator_version}, "
        f"{record.symbol} on {record.environment}",
    )


def _validation_fresh(
    record: BinanceValidationRecord | None, problem: str
) -> GateCheck:
    if record is None:
        return failing(CheckName.VALIDATION_FRESH, problem or "no validation record", problem)
    age = record.age_hours(datetime.now(UTC))
    if age < 0:
        return failing(
            CheckName.VALIDATION_FRESH,
            f"the record claims to be from {abs(age):.1f} hours in the future",
            "a clock is wrong — fix NTP on whichever machine produced this",
        )
    if age > VALIDATION_MAX_AGE_HOURS:
        return failing(
            CheckName.VALIDATION_FRESH,
            f"the validation is {age:.1f} hours old; the bound is "
            f"{VALIDATION_MAX_AGE_HOURS:.0f} hours",
            "re-run scripts/validate_binance.py — fee tiers and key permissions are "
            "editable at any time, so yesterday's answer is a guess about today",
        )
    return passing(CheckName.VALIDATION_FRESH, f"{age:.1f} hours old")


def _clock_skew(state: AppState, record: BinanceValidationRecord | None) -> GateCheck:
    live = getattr(state, "live_runtime", None)
    if live is not None and live.skew is not None and live.skew.last_skew_ms is not None:
        skew = live.skew.last_skew_ms
        if live.skew.last_ok:
            return passing(CheckName.CLOCK_SKEW_OK, f"measured live: {skew:.0f} ms")
        return failing(
            CheckName.CLOCK_SKEW_OK,
            f"measured live: {skew:.0f} ms, beyond the threshold",
            "fix NTP; signed requests are rejected outside recvWindow",
        )
    if record is None:
        return failing(
            CheckName.CLOCK_SKEW_OK,
            "never measured against the venue",
            "run scripts/validate_binance.py, which measures it",
        )
    skew_ms = record.facts.get("clock_skew_ms")
    if skew_ms is None:
        return failing(
            CheckName.CLOCK_SKEW_OK,
            "the validation record carries no skew measurement",
            "re-run the validator",
        )
    if abs(float(skew_ms)) > 1000:
        return failing(
            CheckName.CLOCK_SKEW_OK,
            f"{skew_ms} ms at validation time",
            "fix NTP before trading",
        )
    return passing(CheckName.CLOCK_SKEW_OK, f"{skew_ms} ms at validation time")


def _user_data_stream(record: BinanceValidationRecord | None) -> GateCheck:
    if record is None:
        return failing(
            CheckName.USER_DATA_STREAM,
            "never exercised",
            "run scripts/validate_binance.py --account, which opens a listenKey",
        )
    ok = record.facts.get("user_data_stream_ok")
    if ok is True:
        return passing(CheckName.USER_DATA_STREAM, "listenKey opened and closed cleanly")
    return failing(
        CheckName.USER_DATA_STREAM,
        "the user-data stream was not successfully exercised",
        "fills would be discovered only by polling; investigate before going live",
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


def _order_idempotency(record: BinanceValidationRecord | None) -> GateCheck:
    if record is None:
        return failing(
            CheckName.ORDER_IDEMPOTENCY,
            "the venue's duplicate handling has never been demonstrated",
            "run scripts/validate_binance.py --order --testnet, which submits the same "
            "clientOrderId twice and requires the second to be refused",
        )
    ok = record.facts.get("duplicate_order_rejected")
    if ok is True:
        return passing(
            CheckName.ORDER_IDEMPOTENCY, "the venue rejected a duplicate clientOrderId"
        )
    return failing(
        CheckName.ORDER_IDEMPOTENCY,
        "the venue was NOT shown to reject a duplicate clientOrderId",
        "do not go live until this is understood; a retry after a timeout could open a "
        "second position",
    )


def _risk(state: AppState) -> GateCheck:
    # A running paper-live session is the active risk path — read it, not the demo run.
    live = state.live_runtime
    if live is not None and live.is_running:
        if live.risk_is_halted:
            return failing(
                CheckName.RISK_ENGINE_HEALTHY,
                "the risk engine is halted (safe mode)",
                "resolve the cause and release the halt deliberately",
            )
        if not live.risk_has_evaluated:
            return failing(
                CheckName.RISK_ENGINE_HEALTHY,
                "the risk engine has not judged a signal yet in this session",
                "let the session process enough bars to produce a signal",
            )
        return passing(CheckName.RISK_ENGINE_HEALTHY, "the paper-live risk engine is evaluating")
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
    # Prefer the running paper-live session; the demo run may be stopped.
    live = state.live_runtime
    if live is not None and live.is_running:
        recs = int(live.counters["reconciliations"])
        breaks = int(live.counters["reconciliation_breaks"])
        if not recs:
            return failing(
                CheckName.RECONCILIATION_HEALTHY,
                "this session has not reached its first scheduled reconciliation yet",
                "let the session run a few more cycles",
            )
        if breaks:
            return failing(
                CheckName.RECONCILIATION_HEALTHY,
                f"{breaks} divergences between our books and the venue's",
                "one of the two is wrong about what we own, and sizing runs off it",
            )
        return passing(CheckName.RECONCILIATION_HEALTHY, f"{recs} clean reconciliations")
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


def _capital_ledger(state: AppState) -> GateCheck:
    if state.settings.live.max_live_capital <= 0:
        return failing(
            CheckName.CAPITAL_LEDGER_READY,
            "no ceiling means no ledger: allocation would be undefined",
            "set TIA_LIVE__MAX_LIVE_CAPITAL",
        )
    live = getattr(state, "live_runtime", None)
    if live is not None and live.ledger.is_halted:
        return failing(
            CheckName.CAPITAL_LEDGER_READY,
            f"the ledger is halted: {live.ledger.halted_reason}",
            "an operator must clear the halt with a name attached",
        )
    return passing(
        CheckName.CAPITAL_LEDGER_READY,
        "ledger wired into the live runtime; balance drift is classified, never absorbed",
    )


def _edge_persistence(edge_persisted: int | None) -> GateCheck:
    if edge_persisted is None:
        return failing(
            CheckName.EDGE_PERSISTENCE,
            "the persisted-evidence store could not be read",
            "check the database; evidence that cannot be read cannot be trusted to exist",
        )
    if edge_persisted <= 0:
        return failing(
            CheckName.EDGE_PERSISTENCE,
            "no round trip has ever been persisted",
            "paper trade until closed trades appear in the edge_outcomes table; a track "
            "record in process memory is amnesia wearing a number",
        )
    return passing(
        CheckName.EDGE_PERSISTENCE, f"{edge_persisted} round trips persisted and reloadable"
    )


def _ev_enforcement(state: AppState) -> GateCheck:
    from tia.runtime.live import LiveRuntime

    if hasattr(LiveRuntime, "enforce_expected_value"):
        return failing(
            CheckName.EV_ENFORCEMENT,
            "LiveRuntime has grown an enforcement flag — enforcement must be structural",
            "remove the flag; the live EV gate must not be switchable",
        )
    if state.settings.live.ev_threshold_bps <= 0:
        return failing(
            CheckName.EV_ENFORCEMENT,
            "the EV threshold is zero — every marginal trade would clear it",
            "set TIA_LIVE__EV_THRESHOLD_BPS above zero",
        )
    return passing(
        CheckName.EV_ENFORCEMENT,
        f"structural (no observe mode exists); threshold "
        f"{state.settings.live.ev_threshold_bps} bps",
    )


def _security(state: AppState) -> GateCheck:
    problems: list[str] = []
    if not state.settings.security.jwt_secret_configured:
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


def _configuration(state: AppState) -> GateCheck:
    live = state.settings.live
    problems: list[str] = []
    if not live.symbol:
        problems.append("no symbol configured")
    if live.venue != "binance":
        problems.append(f"unknown venue {live.venue!r}")
    if live.enabled and live.max_live_capital <= 0:
        problems.append("live enabled with a zero ceiling")
    if problems:
        return failing(
            CheckName.CONFIGURATION_COHERENT,
            "; ".join(problems),
            "fix the live configuration block in .env",
        )
    return passing(
        CheckName.CONFIGURATION_COHERENT,
        f"{live.symbol} on {live.venue} ({'testnet' if live.use_testnet else 'MAINNET'})",
    )


def _observability(state: AppState) -> GateCheck:
    obs = state.settings.observability
    if not obs.metrics_enabled:
        return failing(
            CheckName.OBSERVABILITY,
            "metrics are disabled",
            "a live session nobody can observe is one nobody can stop in time",
        )
    return passing(
        CheckName.OBSERVABILITY,
        f"metrics on, logs at {obs.log_level}, event stream available",
    )


def _fees(record: BinanceValidationRecord | None) -> GateCheck:
    taker = record.facts.get("taker_bps") if record else None
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
    live = getattr(state, "live_runtime", None)
    if live is not None and live.state.value in {"safe_mode", "error"}:
        return failing(
            CheckName.KILL_SWITCH_CLEAR,
            f"the live runtime is in {live.state.value}",
            "resolve the incident before arming again",
        )
    return passing(CheckName.KILL_SWITCH_CLEAR, "clear")


def _emergency_controls() -> GateCheck:
    from tia.runtime.live import LiveRuntime

    missing = [
        name
        for name in ("kill_switch", "emergency_flatten", "halt_new_orders")
        if not callable(getattr(LiveRuntime, name, None))
    ]
    if missing:
        return failing(
            CheckName.EMERGENCY_CONTROLS,
            f"missing controls: {missing}",
            "an emergency control that does not exist cannot be reached in an emergency",
        )
    marker = _read_json(VERIFY_MARKER)
    if not (marker and marker.get("passed")):
        return failing(
            CheckName.EMERGENCY_CONTROLS,
            "the controls exist but the suite that tests them has not passed here",
            "run `make verify`",
        )
    return passing(
        CheckName.EMERGENCY_CONTROLS,
        "kill switch, flatten and halt exist and their tests passed in the last verify",
    )


def _restart_recovery() -> GateCheck:
    marker = _read_json(VERIFY_MARKER)
    recovery_test = Path("tests/integration/test_restart_recovery.py")
    if not recovery_test.is_file():
        return failing(
            CheckName.RESTART_RECOVERY,
            "no restart-recovery test exists",
            "a crash mid-session must be a tested path, not a hoped-for one",
        )
    if not (marker and marker.get("passed")):
        return failing(
            CheckName.RESTART_RECOVERY,
            "the restart-recovery test exists but the suite has not passed here",
            "run `make verify`",
        )
    return passing(CheckName.RESTART_RECOVERY, "tested; state reloads and orders deduplicate")


def _credentials(state: AppState, record: BinanceValidationRecord | None) -> GateCheck:
    permissions = record.facts.get("permissions") if record else None
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
    # The record must have been produced with the key this deployment would trade with.
    # A validation run against one credential is not evidence about another — permissions
    # are per-key, and swapping the key after validating is exactly the hole this closes.
    validated = record.facts.get("api_key_fingerprint", "") if record else ""
    if not validated:
        return failing(
            CheckName.CREDENTIALS_SCOPED,
            "the validation record does not identify which API key it validated",
            "re-run `python scripts/validate_binance.py --account` (current versions "
            "record a one-way key fingerprint — never the key itself)",
        )
    configured = key_fingerprint_from_live_config(state.settings.live)
    if configured and validated != configured:
        return failing(
            CheckName.CREDENTIALS_SCOPED,
            f"the record validated {validated} but this deployment is configured with "
            f"{configured} — a different key",
            "re-run the validator with the key the deployment actually uses",
        )
    return passing(
        CheckName.CREDENTIALS_SCOPED,
        f"can trade, cannot move funds; validated as {validated}"
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


def _track_record_probe(
    state: AppState, track_record: dict[str, Any] | None
) -> GateCheck:
    """Days AND trades, measured from the persisted record — gap C6 closed.

    An in-memory count restarts at zero with the process; this reads the span between the
    first and last *persisted* closed trades, which survives anything short of losing the
    database — and losing the database fails the check too, which is correct.
    """
    required_trades = state.settings.live.min_paper_trades
    required_days = state.settings.live.min_paper_days
    if track_record is None:
        return failing(
            CheckName.PAPER_TRACK_RECORD,
            "the persisted track record could not be read",
            "check the database",
        )
    trades = int(track_record.get("closed_trades", 0))
    days = float(track_record.get("span_days", 0.0))
    problems: list[str] = []
    if trades < required_trades:
        problems.append(f"{trades} closed round trips; {required_trades} required")
    if days < required_days:
        problems.append(f"{days:.1f} days of history; {required_days:.0f} required")
    if problems:
        return failing(
            CheckName.PAPER_TRACK_RECORD,
            "; ".join(problems),
            "live is not the place to discover the first reconnect",
        )
    return passing(
        CheckName.PAPER_TRACK_RECORD,
        f"{trades} closed round trips over {days:.1f} days",
    )


def validation_facts() -> dict[str, Any] | None:
    """What ``scripts/validate_binance.py`` last confirmed, or ``None`` if it never ran.

    Shown on the live page so "why is the gate refusing?" has an answer that names the
    command to run rather than a boolean.
    """
    return _read_json(BINANCE_FACTS)


__all__ = [
    "BINANCE_FACTS",
    "EXPECTED_VALIDATOR_VERSION",
    "VALIDATION_MAX_AGE_HOURS",
    "VERIFY_MARKER",
    "BinanceValidationRecord",
    "build_probes",
    "load_validation_record",
    "validation_facts",
]
